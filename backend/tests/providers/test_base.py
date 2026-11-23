from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.models import HourlySeries, Point
from core.rules import load_rules
from providers.base import (
    GridPoint,
    NoRoute,
    Place,
    ProviderError,
    ProviderUnavailable,
    RawRoute,
    RoutingProvider,
    Vehicle,
    WeatherProvider,
    vehicle_for_load,
)

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")


def test_vehicle_weight_is_tare_plus_cargo_converted_to_kilograms() -> None:
    vehicle = vehicle_for_load(42_000, RULES)  # 35,000 lb tare + 42,000 lb cargo
    assert vehicle.weight_kg == pytest.approx(77_000 * 0.45359237)
    assert vehicle.max_speed_kmh == 105


def test_the_cargo_weight_alone_is_not_what_routing_receives() -> None:
    assert vehicle_for_load(1_000, RULES).weight_kg > 1_000 * 0.45359237


def test_failures_share_a_base_class() -> None:
    assert issubclass(ProviderUnavailable, ProviderError)
    assert issubclass(NoRoute, ProviderError)


def test_grid_points_are_hashable_and_sortable() -> None:
    a, b = GridPoint(35.0, -100.0), GridPoint(35.0, -99.9)
    assert {a: 1}[GridPoint(35.0, -100.0)] == 1
    assert sorted([b, a]) == [a, b]


class FakeRouting:
    def routes(
        self,
        origin: Point,
        destination: Point,
        depart_at_utc: datetime,
        vehicle: Vehicle,
        via: Sequence[Point] = (),
    ) -> list[RawRoute]:
        return [
            RawRoute(
                points=(origin, destination),
                distance_mi=1.0,
                drive_s=60.0,
                anchors=((0.0, 0.0), (1.0, 60.0)),
                roads=(),
            )
        ]

    def search(self, query: str, limit: int) -> list[Place]:
        return [Place(label=query, lat=0.0, lon=0.0)][:limit]


class FakeWeather:
    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        return {}


def test_fakes_satisfy_the_protocols() -> None:
    routing: RoutingProvider = FakeRouting()
    weather: WeatherProvider = FakeWeather()
    now = datetime(2026, 11, 24, tzinfo=UTC)
    routes = routing.routes((35.0, -100.0), (36.0, -100.0), now, Vehicle(30_000, 105))
    assert routes[0].distance_mi == 1.0
    assert routing.search("Dallas", 5)[0].label == "Dallas"
    assert weather.hourly([GridPoint(35.0, -100.0)], now, now) == {}
