"""The committed recordings of the four sample trips run through the whole domain core.

These are real TomTom and Open-Meteo responses (thinned), so this proves the data parses into the
core models and that the pipeline produces sensible answers on real routes, with no live calls.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from api.rules import get_rules
from core.checkpoints import choose_interval, haversine_mi, place_checkpoints, route_length_mi
from core.eta import build_eta_plan
from core.forecast_hour import weather_at
from core.models import Level
from core.risk import classify
from core.scoring import RouteScore, attribute_miles, recommend, summarize
from providers.base import GridPoint, RawRoute, Vehicle
from providers.fixture_io import load_trip
from providers.fixtures_provider import (
    DEFAULT_FIXTURE_DIR,
    FixtureRoutingProvider,
    FixtureWeatherProvider,
)
from providers.sample_trips import SAMPLE_TRIPS, SampleTrip

# slug -> (min miles, max miles, expected interval)
EXPECTED = {
    "denver-cheyenne": (90, 140, 10),
    "saltlake-denver": (450, 620, 25),
    "chicago-dallas": (1000, 1300, 50),  # TomTom's truck routes are over 1,000 mi
    "seattle-chicago": (1900, 2300, 50),
}
NOW = datetime(2026, 11, 24, 15, 40, tzinfo=UTC)
TRIP_FILES = sorted((DEFAULT_FIXTURE_DIR / "trips").glob("*.json"))


def test_all_four_sample_trips_are_recorded() -> None:
    assert [p.stem for p in TRIP_FILES] == sorted(t.slug for t in SAMPLE_TRIPS)


@pytest.mark.parametrize("path", TRIP_FILES, ids=lambda p: p.stem)
def test_recorded_routes_are_real_distinct_and_consistent(path: Path) -> None:
    trip, routes = load_trip(path)
    low, high, _ = EXPECTED[trip.slug]
    assert len(routes) >= 2  # real alternatives, never fabricated
    for route in routes:
        assert low < route.distance_mi < high
        # Geometry runs from the origin to the destination.
        assert haversine_mi(route.points[0], (trip.origin.lat, trip.origin.lon)) < 5
        assert haversine_mi(route.points[-1], (trip.destination.lat, trip.destination.lon)) < 5
        # The thinned geometry is close to the provider's distance.
        assert route_length_mi(route.points) == pytest.approx(route.distance_mi, rel=0.03)
        # Timing anchors start at zero, end at the totals and never go backwards.
        assert route.anchors[0] == (0.0, 0.0)
        assert route.anchors[-1][0] == pytest.approx(route.distance_mi, rel=0.001)
        assert route.anchors[-1][1] == pytest.approx(route.drive_s, rel=0.001)
        miles = [a[0] for a in route.anchors]
        seconds = [a[1] for a in route.anchors]
        assert miles == sorted(miles)
        assert seconds == sorted(seconds)
        # Realistic truck speed: under the 65 mph cap on average.
        assert route.distance_mi / (route.drive_s / 3600) < 65
        assert route.roads


@pytest.mark.parametrize("path", TRIP_FILES, ids=lambda p: p.stem)
def test_the_interval_matches_the_trip_length(path: Path) -> None:
    trip, routes = load_trip(path)
    longest = max(r.distance_mi for r in routes)
    assert choose_interval(longest, get_rules()) == EXPECTED[trip.slug][2]


def score_route(
    route_id: str, order: int, route: RawRoute, trip: SampleTrip, weather: FixtureWeatherProvider
) -> RouteScore:
    """Run one recorded route through checkpoints, ETAs, weather, risk and scoring."""
    rules = get_rules()
    interval = EXPECTED[trip.slug][2]
    length = route_length_mi(route.points)
    checkpoints = place_checkpoints(route.points, interval)
    plan = build_eta_plan(route.anchors, length, NOW, rules)

    points = [GridPoint(round(c.lat, 1), round(c.lon, 1)) for c in checkpoints]
    series = weather.hourly(points, NOW, NOW + timedelta(days=6))
    levels = []
    for checkpoint, point in zip(checkpoints, points, strict=True):
        found = weather_at(series[point], plan.eta_at_mile(checkpoint.mile))
        levels.append(Level.NO_FORECAST if found is None else classify(found, 42_000, rules).level)

    summary = summarize(attribute_miles([c.mile for c in checkpoints], levels, length), rules)
    return RouteScore(
        id=route_id, order=order, distance_mi=length, total_s=plan.total_s, summary=summary
    )


@pytest.mark.parametrize("path", TRIP_FILES, ids=lambda p: p.stem)
def test_every_recorded_trip_scores_and_gets_a_recommendation(path: Path) -> None:
    trip, routes = load_trip(path)
    weather = FixtureWeatherProvider(now=lambda: NOW)
    scores = [score_route(chr(65 + i), i, route, trip, weather) for i, route in enumerate(routes)]

    for score in scores:
        # Risk miles add up to the route and every mile has forecast data in this window.
        assert sum(score.summary.miles.values()) == pytest.approx(score.distance_mi, abs=0.01)
        assert score.summary.miles[Level.NO_FORECAST] == 0
        assert score.total_s >= routes[0].drive_s * 0.5

    result = recommend(scores, get_rules())
    assert result.route_id in {s.id for s in scores}
    assert sorted(result.ranking) == sorted(s.id for s in scores)
    assert result.reason


def test_long_trips_include_required_stops_in_their_total_time() -> None:
    trip, routes = load_trip(DEFAULT_FIXTURE_DIR / "trips" / "seattle-chicago.json")
    plan = build_eta_plan(routes[0].anchors, route_length_mi(routes[0].points), NOW, get_rules())
    assert plan.total_s > plan.drive_s + 10 * 3600  # at least one 10 h rest
    assert [s.type for s in plan.stops].count("rest") >= 2


def test_the_fixture_routing_provider_serves_the_recorded_trips() -> None:
    provider = FixtureRoutingProvider()
    for trip in SAMPLE_TRIPS:
        routes = provider.routes(
            (trip.origin.lat, trip.origin.lon),
            (trip.destination.lat, trip.destination.lon),
            NOW,
            Vehicle(30_000, 105),
        )
        assert len(routes) >= 2


def test_recorded_weather_covers_a_full_week_with_real_values() -> None:
    weather = FixtureWeatherProvider(now=lambda: NOW)
    some_point = GridPoint(40.0, -105.0)
    series = weather.hourly([some_point], NOW, NOW + timedelta(days=6))[some_point]
    assert len(series.wind_mph) >= 150
    assert series.start_utc == datetime(2026, 11, 24, 15, 0, tzinfo=UTC)
    assert any(v and v > 0 for v in series.wind_mph)
