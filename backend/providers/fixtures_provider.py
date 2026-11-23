"""Test-only providers that replay recorded real responses (plan.md section 12.4).

Used by CI and the end-to-end tests so they never call live services. Weather times are
re-based so recorded hour 0 maps to the current hour; otherwise recorded data would drift into the
past and every checkpoint would become "No forecast".
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from math import cos, radians
from pathlib import Path

from core.checkpoints import haversine_mi
from core.models import HourlySeries, Point
from providers.base import GridPoint, NoRoute, Place, RawRoute, Vehicle
from providers.fixture_io import load_trip, load_weather
from providers.sample_trips import SampleTrip

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
# A request matches a recorded trip when both ends are within this many miles of the recording.
_TRIP_MATCH_MI = 15.0
# Weather requests further than this from every recorded node get no data.
_NODE_MATCH_DEG = 3.0


class FixtureRoutingProvider:
    def __init__(self, fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> None:
        self._trips: list[tuple[SampleTrip, list[RawRoute]]] = [
            load_trip(path) for path in sorted((fixture_dir / "trips").glob("*.json"))
        ]

    def routes(
        self,
        origin: Point,
        destination: Point,
        depart_at_utc: datetime,
        vehicle: Vehicle,
        via: Sequence[Point] = (),
    ) -> list[RawRoute]:
        if via:
            # Nothing is recorded for via-point requests, so generated alternatives are skipped.
            raise NoRoute("fixtures have no via-point routes")
        for trip, routes in self._trips:
            near_start = haversine_mi(origin, (trip.origin.lat, trip.origin.lon)) < _TRIP_MATCH_MI
            near_end = (
                haversine_mi(destination, (trip.destination.lat, trip.destination.lon))
                < _TRIP_MATCH_MI
            )
            if near_start and near_end:
                return list(routes)
        raise NoRoute("no recorded fixture for this trip")

    def search(self, query: str, limit: int) -> list[Place]:
        needle = " ".join(query.lower().split())
        places: dict[str, Place] = {}
        for trip, _ in self._trips:
            for place in (trip.origin, trip.destination):
                places.setdefault(place.label, place)
        matches = [
            p
            for p in places.values()
            if p.label.lower().startswith(needle)
            or any(word.startswith(needle) for word in p.label.lower().replace(",", "").split())
        ]
        return matches[:limit]


def _floor_hour(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


class FixtureWeatherProvider:
    def __init__(
        self,
        weather_file: Path = DEFAULT_FIXTURE_DIR / "weather.json",
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._nodes = load_weather(weather_file)
        self._now = now

    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        start = _floor_hour(self._now())
        result: dict[GridPoint, HourlySeries] = {}
        for point in points:
            nearest = self._nearest_node(point)
            if nearest is None:
                continue
            recorded = nearest
            # Recorded hour 0 becomes the current hour; the rest of the series shifts with it.
            result[point] = HourlySeries(
                start_utc=start,
                wind_mph=recorded.wind_mph,
                gust_mph=recorded.gust_mph,
                rain_in_hr=recorded.rain_in_hr,
                snow_in_hr=recorded.snow_in_hr,
            )
        return result

    def _nearest_node(self, point: GridPoint) -> HourlySeries | None:
        best: tuple[float, HourlySeries] | None = None
        for node_point, series in self._nodes:
            gap = _gap_deg(point, node_point)
            if best is None or gap < best[0]:
                best = (gap, series)
        return best[1] if best is not None and best[0] <= _NODE_MATCH_DEG else None


def _gap_deg(a: GridPoint, b: GridPoint) -> float:
    """Rough angular distance in degrees (longitude shrunk by latitude); fine for nearest-node."""
    d_lat = a.lat - b.lat
    d_lon = (a.lon - b.lon) * cos(radians((a.lat + b.lat) / 2))
    return float((d_lat * d_lat + d_lon * d_lon) ** 0.5)
