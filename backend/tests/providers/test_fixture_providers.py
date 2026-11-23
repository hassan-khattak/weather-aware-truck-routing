"""Fixture providers, PROVIDERS_MODE and fixture recording (all offline)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytest_django import Settings

from api.rules import get_rules
from core.models import HourlySeries, Point
from providers.base import (
    GridPoint,
    NoRoute,
    Place,
    RawRoute,
    RoadMark,
    Vehicle,
)
from providers.factory import routing_provider, weather_provider
from providers.fixture_io import load_trip, load_weather, save_trip, save_weather
from providers.fixtures_provider import FixtureRoutingProvider, FixtureWeatherProvider
from providers.mode import validate_providers_mode
from providers.recording import lattice_nodes, record_fixtures, thin
from providers.sample_trips import SAMPLE_TRIPS

VEHICLE = Vehicle(weight_kg=30_000, max_speed_kmh=105)
NOW = datetime(2026, 11, 24, 15, 40, tzinfo=UTC)
DENVER_CHEYENNE = SAMPLE_TRIPS[0]


def route(points: tuple[Point, ...] = ((39.74, -104.99), (41.14, -104.82))) -> RawRoute:
    return RawRoute(
        points=points,
        distance_mi=100.0,
        drive_s=6000.0,
        anchors=((0.0, 0.0), (100.0, 6000.0)),
        roads=(RoadMark(0.0, "I-25 N"),),
    )


def series(start: datetime, wind: float) -> HourlySeries:
    return HourlySeries(
        start_utc=start,
        wind_mph=(wind, wind + 1),
        gust_mph=(wind + 5, wind + 6),
        rain_in_hr=(0.0, 0.1),
        snow_in_hr=(0.0, None),
    )


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    (tmp_path / "trips").mkdir()
    save_trip(tmp_path / "trips" / "denver-cheyenne.json", DENVER_CHEYENNE, [route()])
    recorded = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)
    save_weather(
        tmp_path / "weather.json",
        recorded,
        {
            GridPoint(40.0, -105.0): series(recorded, 10),
            GridPoint(47.0, -122.0): series(recorded, 40),
        },
    )
    return tmp_path


# --- serialisation ---


def test_a_trip_round_trips_through_json(fixture_dir: Path) -> None:
    trip, routes = load_trip(fixture_dir / "trips" / "denver-cheyenne.json")
    assert trip == DENVER_CHEYENNE
    assert routes == [route()]


def test_weather_round_trips_through_json_including_missing_values(fixture_dir: Path) -> None:
    nodes = dict(load_weather(fixture_dir / "weather.json"))
    node = nodes[GridPoint(40.0, -105.0)]
    assert node.wind_mph == (10, 11)
    assert node.snow_in_hr == (0.0, None)
    assert node.start_utc == datetime(2026, 11, 20, tzinfo=UTC)


# --- routing fixtures ---


def test_a_recorded_trip_is_replayed(fixture_dir: Path) -> None:
    provider = FixtureRoutingProvider(fixture_dir)
    routes = provider.routes((39.7392, -104.9903), (41.14, -104.8202), NOW, VEHICLE)
    assert routes == [route()]


def test_a_slightly_different_coordinate_still_matches_the_recorded_trip(fixture_dir: Path) -> None:
    provider = FixtureRoutingProvider(fixture_dir)
    assert provider.routes((39.75, -104.98), (41.13, -104.83), NOW, VEHICLE)


def test_an_unrecorded_trip_is_no_route(fixture_dir: Path) -> None:
    provider = FixtureRoutingProvider(fixture_dir)
    with pytest.raises(NoRoute):
        provider.routes((32.78, -96.8), (35.22, -101.83), NOW, VEHICLE)


def test_search_matches_the_recorded_places_by_prefix_or_word(fixture_dir: Path) -> None:
    provider = FixtureRoutingProvider(fixture_dir)
    assert [p.label for p in provider.search("Den", 6)] == ["Denver, CO"]
    assert [p.label for p in provider.search("chey", 6)] == ["Cheyenne, WY"]
    assert provider.search("zzz", 6) == []


# --- weather fixtures ---


def test_recorded_hour_zero_is_re_based_to_the_current_hour(fixture_dir: Path) -> None:
    provider = FixtureWeatherProvider(fixture_dir / "weather.json", now=lambda: NOW)
    point = GridPoint(40.0, -105.0)
    result = provider.hourly([point], NOW, NOW + timedelta(days=6))
    assert result[point].start_utc == datetime(2026, 11, 24, 15, 0, tzinfo=UTC)
    assert result[point].wind_mph == (10, 11)


def test_each_point_gets_the_nearest_recorded_node(fixture_dir: Path) -> None:
    provider = FixtureWeatherProvider(fixture_dir / "weather.json", now=lambda: NOW)
    near_denver, near_seattle = GridPoint(40.3, -104.8), GridPoint(46.5, -121.5)
    result = provider.hourly([near_denver, near_seattle], NOW, NOW)
    assert result[near_denver].wind_mph[0] == 10
    assert result[near_seattle].wind_mph[0] == 40


def test_points_far_from_every_node_get_no_data(fixture_dir: Path) -> None:
    provider = FixtureWeatherProvider(fixture_dir / "weather.json", now=lambda: NOW)
    far = GridPoint(25.0, -80.0)  # Miami
    assert provider.hourly([far], NOW, NOW) == {}


# --- PROVIDERS_MODE ---


def test_live_mode_is_always_allowed() -> None:
    assert validate_providers_mode("live", debug=False) == "live"
    assert validate_providers_mode("live", debug=True) == "live"


def test_fixtures_mode_is_allowed_while_developing() -> None:
    assert validate_providers_mode("fixtures", debug=True) == "fixtures"


def test_fixtures_mode_is_refused_in_production() -> None:
    with pytest.raises(RuntimeError, match="DEBUG off"):
        validate_providers_mode("fixtures", debug=False)


def test_unknown_modes_are_refused() -> None:
    with pytest.raises(RuntimeError, match="PROVIDERS_MODE"):
        validate_providers_mode("mock", debug=True)


# --- factory ---


def test_the_factory_returns_fixture_providers_in_fixtures_mode(settings: Settings) -> None:
    settings.PROVIDERS_MODE = "fixtures"
    assert isinstance(routing_provider(), FixtureRoutingProvider)
    assert isinstance(weather_provider(), FixtureWeatherProvider)


def test_the_factory_returns_the_real_adapters_in_live_mode(settings: Settings) -> None:
    from providers.openmeteo import OpenMeteoWeatherProvider
    from providers.tomtom import TomTomRoutingProvider

    settings.PROVIDERS_MODE = "live"
    settings.TOMTOM_API_KEY = "test-key"
    assert isinstance(routing_provider(), TomTomRoutingProvider)
    assert isinstance(weather_provider(), OpenMeteoWeatherProvider)


# --- recording ---


def test_thinning_keeps_the_ends_and_drops_points_closer_than_the_gap() -> None:
    points = tuple((35.0 + i * 0.0001, -100.0) for i in range(1000))  # ~6.9 mi, a point per 36 ft
    thinned = thin(points, 0.5)
    assert thinned[0] == points[0]
    assert thinned[-1] == points[-1]
    assert 10 < len(thinned) < 20


def test_lattice_nodes_snap_route_points_to_whole_degrees() -> None:
    nodes = lattice_nodes([route(((39.74, -104.99), (41.14, -104.4)))])
    assert nodes == {GridPoint(40.0, -105.0), GridPoint(41.0, -104.0)}


class FakeRouting:
    def __init__(self) -> None:
        self.requests: list[tuple[Point, Point]] = []

    def routes(
        self,
        origin: Point,
        destination: Point,
        depart_at_utc: datetime,
        vehicle: Vehicle,
        via: Sequence[Point] = (),
    ) -> list[RawRoute]:
        self.requests.append((origin, destination))
        return [route((origin, destination))]

    def search(self, query: str, limit: int) -> list[Place]:  # pragma: no cover - unused
        return []


class FakeWeather:
    def __init__(self) -> None:
        self.requested: list[GridPoint] = []

    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        self.requested = list(points)
        return {p: series(start_utc, 10) for p in points}


@pytest.mark.django_db
def test_recording_writes_every_sample_trip_and_one_weather_file(tmp_path: Path) -> None:
    routing, weather = FakeRouting(), FakeWeather()
    summary = record_fixtures(routing, weather, tmp_path, get_rules(), NOW)

    assert sorted(p.name for p in (tmp_path / "trips").glob("*.json")) == sorted(
        f"{t.slug}.json" for t in SAMPLE_TRIPS
    )
    assert len(routing.requests) == 4
    assert summary["denver-cheyenne"] == 1
    assert summary["weather_nodes"] == len(weather.requested) > 0
    assert len(load_weather(tmp_path / "weather.json")) == summary["weather_nodes"]


@pytest.mark.django_db
def test_recorded_fixtures_can_be_replayed_by_the_fixture_providers(tmp_path: Path) -> None:
    record_fixtures(FakeRouting(), FakeWeather(), tmp_path, get_rules(), NOW)
    replay = FixtureRoutingProvider(tmp_path)
    trip = SAMPLE_TRIPS[2]
    routes = replay.routes(
        (trip.origin.lat, trip.origin.lon),
        (trip.destination.lat, trip.destination.lon),
        NOW,
        VEHICLE,
    )
    assert len(routes) == 1
