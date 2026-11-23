"""The 49-hour heatmap built during risk assessment (plan.md sections 3.11, 4.13, 7.4)."""

import base64
import gzip
import json
import struct
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from api.rules import get_rules
from api.validation import Departure, TripRequest
from core.checkpoints import haversine_mi
from core.models import HourlySeries
from providers.base import GridPoint
from providers.fixtures_provider import FixtureRoutingProvider, FixtureWeatherProvider
from providers.sample_trips import SAMPLE_TRIPS
from trips.planner import Trip, plan_trip
from trips.risk import _heatmap_cells, assess
from weather_grid.service import WeatherGridService

RULES = get_rules()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
DEPARTURE = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
MIDNIGHT = datetime(2026, 11, 24, tzinfo=UTC)
TRIPS = {t.slug: t for t in SAMPLE_TRIPS}
HOURS = 49


def make_trip(slug: str = "denver-cheyenne", load_lb: float = 42_000) -> Trip:
    trip = TRIPS[slug]
    request = TripRequest(
        origin=trip.origin,
        destination=trip.destination,
        departure=Departure(
            utc=DEPARTURE, tz="America/Chicago", local=datetime(2026, 11, 24, 15, 0)
        ),
        load_lb=load_lb,
        warnings=(),
    )
    return plan_trip(request, FixtureRoutingProvider(), RULES, NOW)


def series_from(values: list[float]) -> HourlySeries:
    n = len(values)
    return HourlySeries(
        start_utc=MIDNIGHT,
        wind_mph=tuple(values),
        gust_mph=tuple(values),
        rain_in_hr=(0.0,) * n,
        snow_in_hr=(0.0,) * n,
    )


class Scripted:
    def __init__(self, series: HourlySeries, drop: set[GridPoint] | None = None) -> None:
        self.series = series
        self.drop = drop or set()
        self.requested: list[GridPoint] = []

    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        self.requested.extend(points)
        return {p: self.series for p in points if p not in self.drop}


class DictCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def set(self, key: str, value: Any, timeout: float | None = None) -> None:
        self.store[key] = value


def run(trip: Trip, provider: Any) -> Any:
    service = WeatherGridService(
        provider, DictCache(), RULES, now=lambda: NOW, sleep=lambda _: None
    )
    return assess(trip, service, RULES, lambda lat, lon: None)


def decode(text: str, fmt: str, count: int) -> tuple[Any, ...]:
    return struct.unpack(f"<{count}{fmt}", base64.b64decode(text))


def cell_count(result: Any) -> int:
    return len(base64.b64decode(result.heatmap.cells)) // 8


def test_layers_hold_one_value_per_cell_per_hour() -> None:
    result = run(make_trip(), Scripted(series_from([5.0] * 168)))
    cells = cell_count(result)
    assert cells > 0
    assert result.heatmap.hours == HOURS
    assert len(base64.b64decode(result.heatmap.layers["risk"])) == HOURS * cells
    assert len(base64.b64decode(result.heatmap.layers["wind"])) == HOURS * cells
    assert len(base64.b64decode(result.heatmap.layers["rain"])) == HOURS * cells * 2
    assert len(base64.b64decode(result.heatmap.layers["snow"])) == HOURS * cells * 2


def test_hour_zero_is_the_departure_time_and_layers_are_hour_major() -> None:
    # Wind equals the hour index, so the value at slider hour h must be 21 + h (departure 21:00).
    result = run(make_trip(), Scripted(series_from([float(i) for i in range(168)])))
    cells = cell_count(result)
    wind = decode(result.heatmap.layers["wind"], "B", HOURS * cells)
    for hour in (0, 1, 12, 48):
        one_hour = wind[hour * cells : (hour + 1) * cells]  # one contiguous slice
        assert set(one_hour) == {21 + hour}
    assert result.heatmap_start_utc == DEPARTURE


def test_the_risk_layer_uses_the_same_load_rules_as_the_checkpoints() -> None:
    steady = Scripted(series_from([40.0] * 168))
    heavy = run(make_trip(load_lb=42_000), steady)
    light = run(make_trip(load_lb=10_000), Scripted(series_from([40.0] * 168)))
    cells = cell_count(heavy)
    assert set(decode(heavy.heatmap.layers["risk"], "B", HOURS * cells)) == {3}  # Severe
    assert set(decode(light.heatmap.layers["risk"], "B", HOURS * cells)) == {2}  # High


def test_cells_without_a_forecast_are_marked_no_data_in_every_layer() -> None:
    trip = make_trip()
    cells, _ = _heatmap_cells(trip, RULES)
    gap = cells[len(cells) // 2]
    result = run(trip, Scripted(series_from([5.0] * 168), drop={gap}))

    count = cell_count(result)
    lat_lon = decode(result.heatmap.cells, "f", count * 2)
    index = next(
        i
        for i in range(count)
        if (round(lat_lon[2 * i], 1), round(lat_lon[2 * i + 1], 1)) == (gap.lat, gap.lon)
    )
    risk = decode(result.heatmap.layers["risk"], "B", HOURS * count)
    wind = decode(result.heatmap.layers["wind"], "B", HOURS * count)
    rain = decode(result.heatmap.layers["rain"], "H", HOURS * count)
    for hour in range(HOURS):
        assert risk[hour * count + index] == 255
        assert wind[hour * count + index] == 255
        assert rain[hour * count + index] == 65535
    assert risk[1] != 255 or index == 1  # neighbouring cells still have data


def test_hours_beyond_the_forecast_are_no_data() -> None:
    # A series that ends at index 29 (05:00 UTC the next day) covers departure + 0..8 h only.
    result = run(make_trip(), Scripted(series_from([5.0] * 30)))
    cells = cell_count(result)
    risk = decode(result.heatmap.layers["risk"], "B", HOURS * cells)
    assert set(risk[: 9 * cells]) == {0}
    assert set(risk[9 * cells :]) == {255}


def test_the_cell_size_grows_with_the_trip() -> None:
    sizes = {}
    for slug in ("denver-cheyenne", "saltlake-denver", "chicago-dallas", "seattle-chicago"):
        sizes[slug] = run(make_trip(slug), Scripted(series_from([5.0] * 168))).heatmap.grid_deg
    assert sizes == {
        "denver-cheyenne": 0.2,  # ~110 mi
        "saltlake-denver": 0.4,  # ~535 mi
        "chicago-dallas": 0.8,  # TomTom's truck routes are 1,050+ mi
        "seattle-chicago": 0.8,  # ~2,100 mi
    }


@pytest.mark.parametrize("slug", [t.slug for t in SAMPLE_TRIPS])
def test_a_search_stays_within_the_weather_provider_budget(slug: str) -> None:
    provider = Scripted(series_from([5.0] * 168))
    result = run(make_trip(slug), provider)
    assert cell_count(result) <= 300
    assert len(set(provider.requested)) <= 450  # one minute's quota is 600 calls


def test_the_heatmap_covers_the_route_start() -> None:
    trip = make_trip()
    result = run(trip, Scripted(series_from([5.0] * 168)))
    count = cell_count(result)
    flat = decode(result.heatmap.cells, "f", count * 2)
    origin = (trip.request.origin.lat, trip.request.origin.lon)
    nearest = min(haversine_mi(origin, (flat[2 * i], flat[2 * i + 1])) for i in range(count))
    assert nearest < 15  # a 0.2 degree cell is about 14 miles tall


def test_the_longest_trip_fits_the_payload_budget_with_real_weather() -> None:
    trip = make_trip("seattle-chicago")
    service = WeatherGridService(
        FixtureWeatherProvider(now=lambda: NOW), DictCache(), RULES, now=lambda: NOW
    )
    result = assess(trip, service, RULES, lambda lat, lon: None)
    heatmap = {
        "grid_deg": result.heatmap.grid_deg,
        "hours": result.heatmap.hours,
        "cells": result.heatmap.cells,
        "layers": result.heatmap.layers,
    }
    assert len(gzip.compress(json.dumps(heatmap).encode())) < 400_000
