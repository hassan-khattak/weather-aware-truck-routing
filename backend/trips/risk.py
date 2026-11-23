"""Step 2 of a search: weather and risk at every checkpoint, mile attribution and the
recommendation (plan.md sections 3.5-3.7, 4.6-4.9, 5.2).

For each route: place checkpoints, compute each checkpoint's ETA, fetch weather for the cells
involved (one shared cache, only missing cells fetched), pick the right forecast hours for the
ETA, classify with the load rules, turn checkpoint levels into risk miles and rank the routes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from core.checkpoints import place_checkpoints
from core.forecast_hour import weather_at
from core.heatmap import snap_point
from core.models import Level, Weather
from core.risk import classify
from core.rules import Rules
from core.scoring import (
    Recommendation,
    RouteScore,
    RouteSummary,
    Segment,
    attribute_miles,
    recommend,
    summarize,
)
from places.nearest import NearestTown, lookup_town
from places.timezones import zone_for
from providers.base import GridPoint
from trips.planner import PlannedRoute, Trip
from weather_grid.service import GridResult, WeatherGridService

TownLookup = Callable[[float, float], NearestTown | None]

NO_FORECAST_REASON = "No forecast available for this time."


@dataclass(frozen=True)
class CheckpointRisk:
    idx: int
    mile: float
    lat: float
    lon: float
    eta_utc: datetime
    tz: str
    road: str | None
    town: NearestTown | None
    weather: Weather | None  # None = no forecast
    level: Level
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RouteRisk:
    route: PlannedRoute
    checkpoints: tuple[CheckpointRisk, ...]
    segments: tuple[Segment, ...]
    summary: RouteSummary
    score: RouteScore


@dataclass(frozen=True)
class Assessment:
    routes: tuple[RouteRisk, ...]
    recommendation: Recommendation
    weather: GridResult  # series per grid point, plus stale / as_of / missing


def road_at(route: PlannedRoute, mile: float) -> str | None:
    """Name of the road at `mile` (measured along our geometry). The provider's road marks use
    the provider's own distances, so the mile is converted first."""
    marks = route.raw.roads
    if not marks:
        return None
    scale = route.raw.distance_mi / route.length_mi if route.length_mi else 1.0
    provider_mile = mile * scale
    current = marks[0].road
    for mark in marks:
        if mark.mile > provider_mile:
            break
        current = mark.road
    return current


def _zone_or(default: str, lat: float, lon: float) -> str:
    try:
        return zone_for(lat, lon)
    except ValueError:
        return default


def grid_point(lat: float, lon: float, rules: Rules) -> GridPoint:
    lat_s, lon_s = snap_point(lat, lon, rules.weather_grid.checkpoint_deg)
    return GridPoint(lat_s, lon_s)


@dataclass(frozen=True)
class _Placed:
    """A checkpoint before weather is known."""

    idx: int
    mile: float
    lat: float
    lon: float
    eta_utc: datetime
    point: GridPoint


def _place(route: PlannedRoute, trip: Trip, rules: Rules) -> list[_Placed]:
    return [
        _Placed(
            idx=c.idx,
            mile=c.mile,
            lat=c.lat,
            lon=c.lon,
            eta_utc=route.plan.eta_at_mile(c.mile),
            point=grid_point(c.lat, c.lon, rules),
        )
        for c in place_checkpoints(route.raw.points, trip.interval_mi)
    ]


def assess(
    trip: Trip,
    weather_service: WeatherGridService,
    rules: Rules,
    town_lookup: TownLookup = lookup_town,
) -> Assessment:
    """Weather and risk for every route of a planned trip.

    Raises ProviderUnavailable only if no weather at all could be obtained (not even stale).
    """
    placed = {route.id: _place(route, trip, rules) for route in trip.routes}
    grid = weather_service.get_series([p.point for items in placed.values() for p in items])
    load_lb = trip.request.load_lb
    origin_zone = trip.request.departure.tz

    route_risks: list[RouteRisk] = []
    for route in trip.routes:
        checkpoints: list[CheckpointRisk] = []
        for item in placed[route.id]:
            series = grid.series.get(item.point)
            weather = weather_at(series, item.eta_utc) if series is not None else None
            level: Level
            reasons: tuple[str, ...]
            if weather is None:
                level, reasons = Level.NO_FORECAST, (NO_FORECAST_REASON,)
            else:
                result = classify(weather, load_lb, rules)
                level, reasons = result.level, result.reasons
            checkpoints.append(
                CheckpointRisk(
                    idx=item.idx,
                    mile=item.mile,
                    lat=item.lat,
                    lon=item.lon,
                    eta_utc=item.eta_utc,
                    tz=_zone_or(origin_zone, item.lat, item.lon),
                    road=road_at(route, item.mile),
                    town=town_lookup(item.lat, item.lon),
                    weather=weather,
                    level=level,
                    reasons=reasons,
                )
            )
        segments = attribute_miles(
            [c.mile for c in checkpoints], [c.level for c in checkpoints], route.length_mi
        )
        summary = summarize(segments, rules)
        score = RouteScore(
            id=route.id,
            order=route.order,
            distance_mi=route.length_mi,
            total_s=route.plan.total_s,
            summary=summary,
        )
        route_risks.append(
            RouteRisk(
                route=route,
                checkpoints=tuple(checkpoints),
                segments=tuple(segments),
                summary=summary,
                score=score,
            )
        )

    return Assessment(
        routes=tuple(route_risks),
        recommendation=recommend([r.score for r in route_risks], rules),
        weather=grid,
    )
