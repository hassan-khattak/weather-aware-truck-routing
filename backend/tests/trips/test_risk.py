"""Risk assessment of planned trips (plan.md sections 3.5-3.7, 4.8)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from api.rules import get_rules
from api.validation import Departure, TripRequest
from core.checkpoints import place_checkpoints
from core.models import HourlySeries, Level
from core.scoring import recommend
from places.nearest import NearestTown
from providers.base import GridPoint, ProviderUnavailable
from providers.fixtures_provider import FixtureRoutingProvider
from providers.sample_trips import SAMPLE_TRIPS
from trips.planner import Trip, plan_trip
from trips.risk import NO_FORECAST_REASON, assess, road_at
from weather_grid.service import CachedSeries, WeatherGridService, stale_key

RULES = get_rules()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
DEPARTURE = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
TRIPS = {t.slug: t for t in SAMPLE_TRIPS}
MIDNIGHT = datetime(2026, 11, 24, 0, 0, tzinfo=UTC)


def make_trip(slug: str = "denver-cheyenne", load_lb: float = 42_000) -> Trip:
    trip = TRIPS[slug]
    request = TripRequest(
        origin=trip.origin,
        destination=trip.destination,
        departure=Departure(
            utc=DEPARTURE, tz="America/Denver", local=datetime(2026, 11, 24, 14, 0)
        ),
        load_lb=load_lb,
        warnings=(),
    )
    return plan_trip(request, FixtureRoutingProvider(), RULES, NOW)


def flat_series(
    wind: float = 5.0, rain: float = 0.0, snow: float = 0.0, **hours: float
) -> HourlySeries:
    """168 hourly values from midnight UTC; `hours` overrides wind by hour index, e.g. h21=50."""
    values = [hours.get(f"h{i}", wind) for i in range(168)]
    return HourlySeries(
        start_utc=MIDNIGHT,
        wind_mph=tuple(values),
        gust_mph=tuple(v + 5 for v in values),
        rain_in_hr=(rain,) * 168,
        snow_in_hr=(snow,) * 168,
    )


class ScriptedWeather:
    def __init__(self, series: HourlySeries | None = None, *, drop: set[GridPoint] | None = None):
        self.series = series or flat_series()
        self.drop = drop or set()
        self.calls: list[list[GridPoint]] = []
        self.fail = False

    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        self.calls.append(list(points))
        if self.fail:
            raise ProviderUnavailable("down")
        return {p: self.series for p in points if p not in self.drop}


class DictCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def set(self, key: str, value: Any, timeout: float | None = None) -> None:
        self.store[key] = value


def service(weather: ScriptedWeather, cache: DictCache | None = None) -> WeatherGridService:
    return WeatherGridService(
        weather, cache or DictCache(), RULES, now=lambda: NOW, sleep=lambda _: None
    )


def no_towns(lat: float, lon: float) -> None:
    return None


# --- structure ---


def test_every_route_gets_checkpoints_with_etas_names_and_levels() -> None:
    trip = make_trip()
    result = assess(trip, service(ScriptedWeather()), RULES, no_towns)

    assert [r.route.id for r in result.routes] == ["A", "B"]
    for risk in result.routes:
        expected = place_checkpoints(risk.route.raw.points, trip.interval_mi)
        assert [c.idx for c in risk.checkpoints] == [c.idx for c in expected]
        assert [round(c.mile, 3) for c in risk.checkpoints] == [round(c.mile, 3) for c in expected]
        assert risk.checkpoints[0].mile == 0
        assert risk.checkpoints[-1].mile == pytest.approx(risk.route.length_mi)
        assert risk.checkpoints[0].eta_utc == DEPARTURE
        etas = [c.eta_utc for c in risk.checkpoints]
        assert etas == sorted(etas)
        assert all(c.tz == "America/Denver" for c in risk.checkpoints[:3])
        assert all(c.road for c in risk.checkpoints)


def test_calm_weather_is_low_everywhere_and_the_recommendation_says_all_clear() -> None:
    result = assess(make_trip(), service(ScriptedWeather()), RULES, no_towns)
    for risk in result.routes:
        assert {c.level for c in risk.checkpoints} == {Level.LOW}
        assert all(c.reasons == () for c in risk.checkpoints)
        assert risk.summary.miles[Level.LOW] == pytest.approx(risk.route.length_mi, abs=0.01)
        assert len(risk.segments) == 1
    assert result.recommendation.all_clear is True
    assert result.recommendation.all_unsafe is False


def test_the_recommendation_matches_core_scoring_on_the_route_scores() -> None:
    result = assess(make_trip(), service(ScriptedWeather()), RULES, no_towns)
    assert result.recommendation == recommend([r.score for r in result.routes], RULES)
    assert result.recommendation.route_id in {"A", "B"}


# --- classification with load rules and reasons ---


def test_wind_is_classified_with_the_load_rules_and_explains_itself() -> None:
    result = assess(
        make_trip(load_lb=42_000), service(ScriptedWeather(flat_series(wind=38))), RULES, no_towns
    )
    checkpoint = result.routes[0].checkpoints[3]
    assert checkpoint.level == Level.SEVERE
    assert checkpoint.reasons == (
        "Wind 38 mph → High",
        "Load 42,000 lb > 40,000 with wind 35–44 mph → Severe",
    )
    assert checkpoint.weather is not None
    assert checkpoint.weather.wind_mph == 38


def test_a_lighter_load_gets_a_lower_level_for_the_same_weather() -> None:
    result = assess(
        make_trip(load_lb=10_000), service(ScriptedWeather(flat_series(wind=38))), RULES, no_towns
    )
    assert {c.level for c in result.routes[0].checkpoints} == {Level.HIGH}


def test_rain_and_snow_are_classified_too() -> None:
    rain = assess(make_trip(), service(ScriptedWeather(flat_series(rain=0.3))), RULES, no_towns)
    assert {c.level for c in rain.routes[0].checkpoints} == {Level.HIGH}
    snow = assess(make_trip(), service(ScriptedWeather(flat_series(snow=2.5))), RULES, no_towns)
    assert {c.level for c in snow.routes[0].checkpoints} == {Level.SEVERE}


# --- ETA to forecast hour (trap T2) ---


def test_each_checkpoint_uses_the_forecast_hours_around_its_own_eta() -> None:
    # Wind is only dangerous at 22:00 UTC (index 22). The departure checkpoint is at exactly 21:00,
    # which uses hour 21 only; every later checkpoint's ETA is between 21:00 and 23:00, so it
    # touches hour 22 (the higher of the two surrounding hours counts).
    series = flat_series(h22=50)
    result = assess(make_trip(), service(ScriptedWeather(series)), RULES, no_towns)
    checkpoints = result.routes[0].checkpoints
    assert checkpoints[0].eta_utc == DEPARTURE
    assert checkpoints[0].level == Level.LOW
    later = [c for c in checkpoints[1:] if c.eta_utc < datetime(2026, 11, 24, 23, 0, tzinfo=UTC)]
    assert later
    assert all(c.level == Level.NO_TRAVEL for c in later)  # wind 50 with 42,000 lb


# --- missing and stale weather ---


def test_a_checkpoint_without_forecast_is_no_forecast_never_low() -> None:
    trip = make_trip()
    victim = place_checkpoints(trip.routes[0].raw.points, trip.interval_mi)[2]
    from trips.risk import grid_point

    dropped = grid_point(victim.lat, victim.lon, RULES)
    result = assess(trip, service(ScriptedWeather(drop={dropped})), RULES, no_towns)

    risk = result.routes[0]
    missing = [c for c in risk.checkpoints if c.level == Level.NO_FORECAST]
    assert missing
    assert all(c.reasons == (NO_FORECAST_REASON,) and c.weather is None for c in missing)
    assert risk.summary.miles[Level.NO_FORECAST] > 0
    assert risk.summary.miles[Level.LOW] < risk.route.length_mi
    assert result.recommendation.all_clear is False
    assert dropped in result.weather.missing


def test_stale_weather_is_used_and_flagged_when_the_provider_fails() -> None:
    trip = make_trip()
    cache = DictCache()
    warm = ScriptedWeather()
    assess(trip, service(warm, cache), RULES, no_towns)
    for key in [k for k in cache.store if k.startswith("wx:v1:")]:
        del cache.store[key]  # the 1 h copies expired; the 24 h stale copies remain

    failing = ScriptedWeather()
    failing.fail = True
    later = WeatherGridService(
        failing, cache, RULES, now=lambda: NOW + timedelta(hours=2), sleep=lambda _: None
    )
    result = assess(trip, later, RULES, no_towns)

    assert result.weather.stale is True
    assert result.weather.as_of == NOW
    assert {c.level for c in result.routes[0].checkpoints} == {Level.LOW}


def test_without_any_weather_at_all_the_assessment_fails() -> None:
    weather = ScriptedWeather()
    weather.fail = True
    with pytest.raises(ProviderUnavailable):
        assess(make_trip(), service(weather), RULES, no_towns)


def test_a_second_assessment_makes_no_provider_calls() -> None:
    trip, cache, weather = make_trip(), DictCache(), ScriptedWeather()
    assess(trip, service(weather, cache), RULES, no_towns)
    first_calls = len(weather.calls)
    assess(trip, service(weather, cache), RULES, no_towns)
    assert first_calls >= 1
    assert len(weather.calls) == first_calls


def test_all_routes_share_one_weather_fetch() -> None:
    weather = ScriptedWeather()
    assess(make_trip("saltlake-denver"), service(weather), RULES, no_towns)
    assert len(weather.calls) == 1  # one batch for three routes
    cells = weather.calls[0]
    assert len(cells) == len(set(cells))


# --- naming places ---


def test_towns_come_from_the_lookup_and_may_be_missing() -> None:
    def lookup(lat: float, lon: float) -> NearestTown | None:
        return NearestTown(name="Fort Collins", state="CO", distance_mi=3.2, direction="S")

    named = assess(make_trip(), service(ScriptedWeather()), RULES, lookup)
    town = named.routes[0].checkpoints[1].town
    assert town is not None
    assert town.label == "Fort Collins, CO"
    unnamed = assess(make_trip(), service(ScriptedWeather()), RULES, no_towns)
    assert unnamed.routes[0].checkpoints[1].town is None


def test_road_names_follow_the_route() -> None:
    route = make_trip("chicago-dallas").routes[0]
    assert road_at(route, 0) == route.raw.roads[0].road
    names = {road_at(route, mile) for mile in range(0, int(route.length_mi), 25)}
    assert "I-55 S" in names or any("I-" in (n or "") for n in names)
    assert road_at(route, route.length_mi + 50) == route.raw.roads[-1].road


def test_road_at_handles_a_route_without_road_names() -> None:
    from dataclasses import replace

    route = make_trip().routes[0]
    bare = replace(route, raw=replace(route.raw, roads=()))
    assert road_at(bare, 10) is None


def test_stale_cache_key_helper_is_per_cell() -> None:
    assert stale_key(GridPoint(35.2, -101.8)) != stale_key(GridPoint(35.3, -101.8))
    assert CachedSeries is not None
