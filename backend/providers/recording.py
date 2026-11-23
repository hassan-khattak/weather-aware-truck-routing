"""Record the sample trips from the live services into fixture files (plan.md section 12.4).

Run `python manage.py record_fixtures` with a TomTom key. Routes are stored thinned (a point every
half mile keeps the shape); weather is stored on a 1 degree lattice along the routes, and the
fixture weather provider serves each request from the nearest recorded node.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.checkpoints import haversine_mi
from core.models import HourlySeries, Point
from core.rules import Rules
from providers.base import GridPoint, RawRoute, RoutingProvider, WeatherProvider, vehicle_for_load
from providers.fixture_io import save_trip, save_weather
from providers.sample_trips import SAMPLE_TRIPS

LATTICE_DEG = 1.0
THIN_MI = 0.5
RECORDING_LOAD_LB = 42_000
SERIES_DAYS = 7


def thin(points: tuple[Point, ...], min_gap_mi: float = THIN_MI) -> tuple[Point, ...]:
    """Drop points closer than `min_gap_mi` to the previous kept one; always keep both ends."""
    kept = [points[0]]
    for point in points[1:-1]:
        if haversine_mi(kept[-1], point) >= min_gap_mi:
            kept.append(point)
    kept.append(points[-1])
    return tuple(kept)


def lattice_nodes(routes: list[RawRoute]) -> set[GridPoint]:
    """Lattice points nearest to the routes' points."""
    return {
        GridPoint(round(lat / LATTICE_DEG) * LATTICE_DEG, round(lon / LATTICE_DEG) * LATTICE_DEG)
        for route in routes
        for lat, lon in route.points
    }


def record_fixtures(
    routing: RoutingProvider,
    weather: WeatherProvider,
    out_dir: Path,
    rules: Rules,
    now: datetime,
) -> dict[str, int]:
    """Write trips/<slug>.json for each sample trip and one weather.json. Returns a summary."""
    (out_dir / "trips").mkdir(parents=True, exist_ok=True)
    vehicle = vehicle_for_load(RECORDING_LOAD_LB, rules)
    all_routes: list[RawRoute] = []
    summary: dict[str, int] = {}

    for trip in SAMPLE_TRIPS:
        routes = routing.routes(
            (trip.origin.lat, trip.origin.lon),
            (trip.destination.lat, trip.destination.lon),
            now + timedelta(hours=3),
            vehicle,
        )
        slim = [
            RawRoute(
                points=thin(r.points),
                distance_mi=r.distance_mi,
                drive_s=r.drive_s,
                anchors=r.anchors,
                roads=r.roads,
            )
            for r in routes
        ]
        save_trip(out_dir / "trips" / f"{trip.slug}.json", trip, slim)
        all_routes.extend(slim)
        summary[trip.slug] = len(slim)

    nodes = sorted(lattice_nodes(all_routes))
    day = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    series: dict[GridPoint, HourlySeries] = weather.hourly(
        nodes, day, day + timedelta(days=SERIES_DAYS - 1)
    )
    save_weather(out_dir / "weather.json", now, series)
    summary["weather_nodes"] = len(series)
    return summary
