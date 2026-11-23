"""The POST /routes body built from a planned trip (plan.md section 7.3)."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from api.polyline import decode
from api.rules import get_rules
from api.validation import Departure, TripRequest
from providers.fixtures_provider import FixtureRoutingProvider
from providers.sample_trips import SAMPLE_TRIPS
from trips.payload import iso_z, routes_payload
from trips.planner import plan_trip

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
TRIPS = {t.slug: t for t in SAMPLE_TRIPS}


def payload_for(slug: str, warnings: tuple[str, ...] = ()) -> dict:  # type: ignore[type-arg]
    trip = TRIPS[slug]
    departure = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
    request = TripRequest(
        origin=trip.origin,
        destination=trip.destination,
        departure=Departure(
            utc=departure, tz="America/Chicago", local=datetime(2026, 11, 24, 15, 0)
        ),
        load_lb=42_000,
        warnings=warnings,
    )
    planned = plan_trip(request, FixtureRoutingProvider(), get_rules(), NOW)
    return routes_payload(planned, "t_abc123", get_rules())


def test_iso_z_formatting() -> None:
    assert iso_z(datetime(2026, 11, 24, 21, 0, tzinfo=UTC)) == "2026-11-24T21:00:00Z"


def test_the_trip_level_fields_match_the_contract() -> None:
    body = payload_for("chicago-dallas", warnings=("careful",))
    assert body["trip_id"] == "t_abc123"
    assert body["departure"] == {
        "utc": "2026-11-24T21:00:00Z",
        "tz": "America/Chicago",
        "local": "2026-11-24T15:00",
    }
    assert body["interval_mi"] == 50
    assert body["notes"] == []
    assert body["warnings"] == ["careful"]
    assert set(body) == {"trip_id", "departure", "interval_mi", "routes", "notes", "warnings"}


def test_each_route_has_the_documented_fields() -> None:
    route = payload_for("chicago-dallas")["routes"][0]
    assert set(route) == {
        "id",
        "order",
        "source",
        "distance_mi",
        "drive_s",
        "total_s",
        "geometry",
        "stops",
        "timeline",
        "long_range_forecast",
    }
    assert route["id"] == "A"
    assert route["source"] == "api"
    assert route["total_s"] > route["drive_s"] > 0
    assert isinstance(route["geometry"], str)


def test_stops_carry_type_mile_start_and_duration() -> None:
    stops = payload_for("chicago-dallas")["routes"][0]["stops"]
    assert [s["type"] for s in stops] == ["break", "rest"]
    assert stops[0]["duration_s"] == 1800
    assert stops[1]["duration_s"] == 36000
    assert stops[0]["start_utc"].endswith("Z")
    assert stops[0]["mile"] < stops[1]["mile"]


def test_the_timeline_starts_at_zero_ends_at_the_totals_and_is_flat_during_stops() -> None:
    route = payload_for("chicago-dallas")["routes"][0]
    timeline = route["timeline"]
    assert timeline[0] == [0, 0.0]
    assert timeline[-1][0] == route["total_s"]
    assert timeline[-1][1] == pytest.approx(route["distance_mi"], abs=0.2)
    assert [t[0] for t in timeline] == sorted(t[0] for t in timeline)
    # The rest stop appears as two points with the same mile.
    rest = next(s for s in route["stops"] if s["type"] == "rest")
    flat = [t for t in timeline if t[1] == rest["mile"]]
    assert len(flat) >= 2
    assert max(t[0] for t in flat) - min(t[0] for t in flat) == 36000


def test_the_drawn_geometry_is_simplified_but_still_spans_the_route() -> None:
    body = payload_for("seattle-chicago")
    trip = TRIPS["seattle-chicago"]
    for route in body["routes"]:
        drawn = decode(route["geometry"])
        assert 20 < len(drawn) < 3000  # far fewer than the thousands of recorded points
        assert drawn[0] == pytest.approx((trip.origin.lat, trip.origin.lon), abs=0.05)
        assert drawn[-1] == pytest.approx((trip.destination.lat, trip.destination.lon), abs=0.05)


def test_the_payload_is_small_enough_for_the_first_step() -> None:
    size = len(json.dumps(payload_for("seattle-chicago")))
    assert size < 120_000


def test_values_are_rounded_for_the_wire() -> None:
    route = payload_for("saltlake-denver")["routes"][0]
    assert route["distance_mi"] == round(route["distance_mi"], 1)
    assert isinstance(route["drive_s"], int)
    assert all(isinstance(t[0], int) for t in route["timeline"])


def test_a_two_route_trip_carries_the_note() -> None:
    assert payload_for("denver-cheyenne")["notes"] == [
        "2 distinct truck routes found for this trip."
    ]


def test_departure_arithmetic_is_consistent() -> None:
    route = payload_for("chicago-dallas")["routes"][0]
    departure = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
    first_stop = datetime.fromisoformat(route["stops"][0]["start_utc"])
    assert first_stop - departure == timedelta(hours=8)
