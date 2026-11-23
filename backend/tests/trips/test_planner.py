"""The routes pipeline on the recorded real trips (fixture provider, no network)."""

from datetime import UTC, datetime, timedelta

import pytest

from api.rules import get_rules
from api.validation import Departure, TripRequest
from providers.base import NoRoute, Place
from providers.fixtures_provider import FixtureRoutingProvider
from providers.sample_trips import SAMPLE_TRIPS, SampleTrip
from trips.planner import MAX_ROUTES, Trip, distinct_routes_note, plan_trip, route_id

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
TRIPS = {t.slug: t for t in SAMPLE_TRIPS}


def request_for(
    trip: SampleTrip, depart_in: timedelta = timedelta(hours=3), load_lb: float = 42_000
) -> TripRequest:
    utc = NOW + depart_in
    return TripRequest(
        origin=trip.origin,
        destination=trip.destination,
        departure=Departure(utc=utc, tz="America/Chicago", local=utc.replace(tzinfo=None)),
        load_lb=load_lb,
        warnings=(),
    )


def plan(slug: str, depart_in: timedelta = timedelta(hours=3)) -> Trip:
    return plan_trip(
        request_for(TRIPS[slug], depart_in), FixtureRoutingProvider(), get_rules(), NOW
    )


def test_route_ids_are_letters_in_order() -> None:
    assert [route_id(i) for i in range(3)] == ["A", "B", "C"]


def test_a_three_route_trip_has_ids_orders_and_sources() -> None:
    trip = plan("chicago-dallas")
    assert [r.id for r in trip.routes] == ["A", "B", "C"]
    assert [r.order for r in trip.routes] == [0, 1, 2]
    assert {r.source for r in trip.routes} == {"api"}
    assert len(trip.routes) <= MAX_ROUTES


def test_the_interval_comes_from_the_longest_route() -> None:
    assert plan("denver-cheyenne").interval_mi == 10
    assert plan("saltlake-denver").interval_mi == 25
    assert plan("chicago-dallas").interval_mi == 50
    assert plan("seattle-chicago").interval_mi == 50


def test_every_route_shares_one_interval() -> None:
    trip = plan("saltlake-denver")
    assert trip.interval_mi == 25
    assert len(trip.routes) == 3


def test_routes_are_measured_along_their_full_geometry() -> None:
    for route in plan("chicago-dallas").routes:
        assert route.length_mi == pytest.approx(route.raw.distance_mi, rel=0.03)


def test_long_trips_include_required_stops_in_the_total_time() -> None:
    route = plan("seattle-chicago").routes[0]
    assert route.plan.drive_s == pytest.approx(route.raw.drive_s, rel=0.001)
    assert route.plan.total_s > route.plan.drive_s + 20 * 3600
    assert [s.type for s in route.plan.stops].count("rest") >= 2


def test_short_trips_have_no_stops() -> None:
    route = plan("denver-cheyenne").routes[0]
    assert route.plan.stops == ()
    assert route.plan.total_s == pytest.approx(route.plan.drive_s)


def test_a_two_route_trip_says_so() -> None:
    trip = plan("denver-cheyenne")
    assert len(trip.routes) == 2
    assert trip.notes == ("2 distinct truck routes found for this trip.",)


def test_a_three_route_trip_has_no_note() -> None:
    assert plan("chicago-dallas").notes == ()


@pytest.mark.parametrize(
    ("count", "note"),
    [
        (1, "Only 1 truck route found for this trip."),
        (2, "2 distinct truck routes found for this trip."),
        (3, None),
    ],
)
def test_note_wording(count: int, note: str | None) -> None:
    assert distinct_routes_note(count) == note


def test_a_trip_that_reaches_past_72_hours_is_flagged_as_long_range() -> None:
    soon = plan("seattle-chicago", depart_in=timedelta(hours=1))
    later = plan("seattle-chicago", depart_in=timedelta(hours=40))
    assert soon.routes[0].long_range_forecast is False  # arrives in about 2.5 days
    assert later.routes[0].long_range_forecast is True


def test_a_short_trip_is_never_long_range() -> None:
    assert (
        plan("denver-cheyenne", depart_in=timedelta(hours=47)).routes[0].long_range_forecast
        is False
    )


def test_the_truck_weight_sent_to_routing_is_tare_plus_cargo() -> None:
    seen = []

    class Spy(FixtureRoutingProvider):
        def routes(self, origin, destination, depart_at_utc, vehicle):  # type: ignore[no-untyped-def]
            seen.append(vehicle)
            return super().routes(origin, destination, depart_at_utc, vehicle)

    plan_trip(request_for(TRIPS["denver-cheyenne"], load_lb=10_000), Spy(), get_rules(), NOW)
    assert seen[0].weight_kg == pytest.approx((35_000 + 10_000) * 0.45359237)
    assert seen[0].max_speed_kmh == 105


def test_a_trip_with_no_route_raises() -> None:
    request = TripRequest(
        origin=Place("Miami, FL", 25.76, -80.19),
        destination=Place("Seattle, WA", 47.6, -122.3),
        departure=Departure(utc=NOW, tz="America/New_York", local=NOW.replace(tzinfo=None)),
        load_lb=1000,
        warnings=(),
    )
    with pytest.raises(NoRoute):
        plan_trip(request, FixtureRoutingProvider(), get_rules(), NOW)
