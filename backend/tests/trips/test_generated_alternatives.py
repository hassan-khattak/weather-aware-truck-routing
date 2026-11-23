"""Generated alternatives: real routes only, and only when clearly different (plan.md 3.8)."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from api.rules import get_rules
from api.validation import Departure, TripRequest
from core.checkpoints import cumulative_miles, haversine_mi, point_at_mile
from core.models import Point
from providers.base import NoRoute, ProviderUnavailable, RawRoute, Vehicle
from providers.fixtures_provider import FixtureRoutingProvider
from providers.sample_trips import SAMPLE_TRIPS
from trips.planner import plan_trip

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
TRIP = SAMPLE_TRIPS[0]  # Denver -> Cheyenne: the fixture has 2 API routes
BASE = FixtureRoutingProvider().routes(
    (TRIP.origin.lat, TRIP.origin.lon),
    (TRIP.destination.lat, TRIP.destination.lon),
    NOW,
    Vehicle(30_000, 105),
)


def shifted(route: RawRoute, d_lon: float, time_factor: float) -> RawRoute:
    """A different-looking route: same shape moved sideways, slower by `time_factor`."""
    return RawRoute(
        points=tuple((lat, lon + d_lon) for lat, lon in route.points),
        distance_mi=route.distance_mi * time_factor,
        drive_s=route.drive_s * time_factor,
        anchors=tuple((mi * time_factor, s * time_factor) for mi, s in route.anchors),
        roads=route.roads,
    )


class Scripted:
    """API routes plus a script for what each via request returns (or raises)."""

    def __init__(
        self,
        base: list[RawRoute],
        via_results: list[Callable[[], list[RawRoute]]],
    ) -> None:
        self.base = base
        self.via_results = via_results
        self.via_calls: list[tuple[Point, ...]] = []

    def routes(
        self,
        origin: Point,
        destination: Point,
        depart_at_utc: datetime,
        vehicle: Vehicle,
        via: Sequence[Point] = (),
    ) -> list[RawRoute]:
        if not via:
            return self.base
        self.via_calls.append(tuple(via))
        return self.via_results[len(self.via_calls) - 1]()

    def search(self, query: str, limit: int) -> list[Any]:  # pragma: no cover - unused
        return []


def request() -> TripRequest:
    return TripRequest(
        origin=TRIP.origin,
        destination=TRIP.destination,
        departure=Departure(
            utc=NOW + timedelta(hours=3), tz="America/Denver", local=NOW.replace(tzinfo=None)
        ),
        load_lb=42_000,
        warnings=(),
    )


def plan(provider: Scripted):  # type: ignore[no-untyped-def]  # noqa: ANN201
    return plan_trip(request(), provider, get_rules(), NOW)


def distinct() -> list[RawRoute]:
    return [shifted(BASE[0], 0.6, 1.2)]  # ~30 mi east, 20% slower


def test_a_distinct_reasonable_via_route_becomes_the_third_option() -> None:
    provider = Scripted(BASE, [distinct])
    trip = plan(provider)

    assert [r.id for r in trip.routes] == ["A", "B", "C"]
    assert [r.source for r in trip.routes] == ["api", "api", "generated"]
    assert trip.notes == ()
    assert len(provider.via_calls) == 1  # stops asking once it has three


def test_the_first_attempt_goes_to_the_left_of_the_main_route() -> None:
    provider = Scripted(BASE, [distinct, distinct])
    plan(provider)
    main = BASE[0].points
    cumulative = cumulative_miles(main)
    midpoint = point_at_mile(main, cumulative, cumulative[-1] / 2)
    (via,) = provider.via_calls[0]
    assert haversine_mi(midpoint, via) == pytest.approx(0.12 * cumulative[-1], abs=0.5)
    # Travelling north from Denver to Cheyenne, left is west.
    assert via[1] < midpoint[1]


def test_a_via_route_that_follows_an_existing_route_is_rejected_and_the_other_side_is_tried() -> (
    None
):
    follows_main = lambda: [BASE[0]]  # noqa: E731
    provider = Scripted(BASE, [follows_main, distinct])
    trip = plan(provider)

    assert len(provider.via_calls) == 2
    assert provider.via_calls[0] != provider.via_calls[1]
    assert [r.source for r in trip.routes] == ["api", "api", "generated"]


def test_routes_that_are_far_slower_than_the_fastest_are_rejected() -> None:
    too_slow = lambda: [shifted(BASE[0], 0.6, 2.0)]  # noqa: E731
    trip = plan(Scripted(BASE, [too_slow, too_slow]))
    assert len(trip.routes) == 2
    assert trip.notes == ("2 distinct truck routes found for this trip.",)


def test_when_nothing_acceptable_is_found_the_note_says_how_many_routes_exist() -> None:
    nothing = lambda: [BASE[1]]  # noqa: E731
    trip = plan(Scripted(BASE, [nothing, nothing]))
    assert [r.source for r in trip.routes] == ["api", "api"]
    assert trip.notes == ("2 distinct truck routes found for this trip.",)


@pytest.mark.parametrize("error", [NoRoute("none"), ProviderUnavailable("down")])
def test_a_failing_via_request_is_skipped_not_fatal(error: Exception) -> None:
    def fail() -> list[RawRoute]:
        raise error

    trip = plan(Scripted(BASE, [fail, distinct]))
    assert [r.source for r in trip.routes] == ["api", "api", "generated"]


def test_an_empty_via_answer_is_skipped() -> None:
    trip = plan(Scripted(BASE, [list, list]))
    assert len(trip.routes) == 2


def test_three_api_routes_need_no_generated_ones() -> None:
    three = [BASE[0], BASE[1], shifted(BASE[0], 1.0, 1.1)]
    provider = Scripted(three, [])
    trip = plan(provider)
    assert [r.source for r in trip.routes] == ["api", "api", "api"]
    assert provider.via_calls == []


def test_api_routes_are_never_replaced_or_reordered() -> None:
    trip = plan(Scripted(BASE, [distinct]))
    assert trip.routes[0].raw == BASE[0]
    assert trip.routes[1].raw == BASE[1]


def test_the_generated_route_gets_its_own_eta_plan() -> None:
    trip = plan(Scripted(BASE, [distinct]))
    generated = trip.routes[2]
    assert generated.plan.drive_s == pytest.approx(BASE[0].drive_s * 1.2, rel=0.01)


def test_the_fixture_provider_never_invents_via_routes() -> None:
    trip = plan_trip(request(), FixtureRoutingProvider(), get_rules(), NOW)
    assert [r.source for r in trip.routes] == ["api", "api"]
