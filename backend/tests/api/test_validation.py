"""POST /routes request validation (plan.md sections 3.2, 3.13, 4.10, 4.11)."""

from datetime import UTC, datetime
from typing import Any

import pytest
import time_machine
from rest_framework.exceptions import ValidationError

from api.errors import OutOfCoverage
from api.rules import get_rules
from api.validation import LOAD_WARNING, TripRequest, is_us_zone, parse_routes_request

DALLAS: dict[str, Any] = {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970}
DENVER: dict[str, Any] = {"label": "Denver, CO", "lat": 39.7392, "lon": -104.9903}
# Departure 2026-11-24 15:00 in Dallas (CST, UTC-6) is 21:00 UTC.
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)


def body(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "origin": dict(DALLAS),
        "destination": dict(DENVER),
        "departure_local": "2026-11-24T15:00",
        "load_lb": 42_000,
    }
    data.update(overrides)
    return data


def parse(data: dict[str, Any], now: datetime = NOW) -> TripRequest:
    return parse_routes_request(data, now=now, rules=get_rules())


def field_error(data: dict[str, Any], now: datetime = NOW) -> dict[str, str]:
    with pytest.raises(ValidationError) as error:
        parse(data, now)
    detail = error.value.detail
    assert isinstance(detail, dict)
    return {key: str(value) for key, value in _flat(detail).items()}


def _flat(detail: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in detail.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flat(value, name))
        else:
            out[name] = value[0] if isinstance(value, list) else value
    return out


# --- the happy path ---


def test_a_valid_request_is_parsed_with_the_departure_resolved_in_the_origin_zone() -> None:
    trip = parse(body())
    assert trip.origin.label == "Dallas, TX"
    assert trip.destination.lat == 39.7392
    assert trip.load_lb == 42_000
    assert trip.departure.tz == "America/Chicago"
    assert trip.departure.utc == datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
    assert trip.departure.local == datetime(2026, 11, 24, 15, 0)
    assert trip.warnings == ()


def test_seconds_in_the_departure_are_accepted() -> None:
    assert parse(body(departure_local="2026-11-24T15:00:30")).departure.utc.second == 30


# --- fields ---


def test_missing_fields_are_reported() -> None:
    data = body()
    del data["origin"]
    assert "origin" in field_error(data)


def test_a_place_needs_coordinates_chosen_from_a_suggestion() -> None:
    data = body(origin={"label": "Dallas, TX"})
    errors = field_error(data)
    assert "origin.lat" in errors
    assert "origin.lon" in errors


def test_out_of_range_coordinates_are_rejected() -> None:
    assert "origin.lat" in field_error(body(origin={**DALLAS, "lat": 95}))


def test_unknown_fields_are_rejected_to_catch_typos() -> None:
    assert "load_lbs" in field_error(body(load_lbs=1000))


def test_unknown_place_fields_are_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        parse(body(origin={**DALLAS, "zip": "75201"}))
    assert "zip" in str(error.value.detail)


def test_the_load_must_be_a_number() -> None:
    assert "load_lb" in field_error(body(load_lb="heavy"))


# --- origin and destination ---


def test_origin_and_destination_must_differ() -> None:
    errors = field_error(body(destination=dict(DALLAS)))
    assert errors["destination"] == "Choose a destination different from the origin."


def test_places_a_fraction_of_a_mile_apart_count_as_the_same_place() -> None:
    near = {**DALLAS, "lat": DALLAS["lat"] + 0.002}  # ~0.14 mi
    assert "destination" in field_error(body(destination=near))


# --- coverage ---


@pytest.mark.parametrize(
    ("name", "lat", "lon"),
    [
        ("Toronto", 43.6532, -79.3832),
        ("Vancouver", 49.2827, -123.1207),
        ("Tijuana", 32.5149, -117.0382),
        ("Ciudad Juarez", 31.6904, -106.4245),
        ("Anchorage", 61.2181, -149.9003),
        ("Honolulu", 21.3069, -157.8583),
        ("Atlantic Ocean", 30.0, -70.0),
        ("London", 51.5074, -0.1278),
    ],
)
def test_places_outside_the_continental_us_are_out_of_coverage(
    name: str, lat: float, lon: float
) -> None:
    outside = {"label": name, "lat": lat, "lon": lon}
    with pytest.raises(OutOfCoverage):
        parse(body(origin=outside))
    with pytest.raises(OutOfCoverage):
        parse(body(destination=outside))


@pytest.mark.parametrize(
    ("lat", "lon", "zone"),
    [
        (47.6062, -122.3321, "America/Los_Angeles"),
        (33.4484, -112.0740, "America/Phoenix"),
        (39.7684, -86.1581, "America/Indiana/Indianapolis"),
        (38.2527, -85.7585, "America/Kentucky/Louisville"),
        (46.8772, -96.7898, "America/Chicago"),
        (25.7617, -80.1918, "America/New_York"),
    ],
)
def test_us_zones_are_recognised(lat: float, lon: float, zone: str) -> None:
    assert is_us_zone(zone)
    place = {"label": "x", "lat": lat, "lon": lon}
    assert parse(body(destination=place, departure_local="2026-11-24T15:00")).destination.lat == lat


def test_canadian_and_mexican_zones_are_not_us_zones() -> None:
    assert not is_us_zone("America/Toronto")
    assert not is_us_zone("America/Tijuana")
    assert not is_us_zone("America/Vancouver")


# --- load ---


@pytest.mark.parametrize("load", [1_000, 45_000, 80_000])
def test_loads_within_limits_are_accepted(load: float) -> None:
    assert parse(body(load_lb=load)).load_lb == load


@pytest.mark.parametrize("load", [999, 80_001, 0, -5])
def test_loads_outside_limits_are_rejected_with_the_range(load: float) -> None:
    assert field_error(body(load_lb=load))["load_lb"] == "Load must be between 1,000 and 80,000 lb."


def test_a_load_above_45000_lb_gets_a_soft_warning() -> None:
    assert parse(body(load_lb=45_001)).warnings == (LOAD_WARNING,)
    assert parse(body(load_lb=45_000)).warnings == ()


# --- departure window (grace 5 min, ahead 48 h) ---


@time_machine.travel(NOW, tick=False)
def test_a_departure_in_the_past_is_rejected() -> None:
    errors = field_error(body(departure_local="2026-11-24T11:00"))  # 17:00 UTC, an hour ago
    assert errors["departure_local"] == "Departure can't be in the past."


def test_the_departure_may_be_up_to_five_minutes_in_the_past() -> None:
    now = datetime(2026, 11, 24, 21, 5, 0, tzinfo=UTC)  # departure 21:00 UTC is exactly 5 min ago
    assert parse(body(), now).departure.utc == datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
    too_late = datetime(2026, 11, 24, 21, 5, 1, tzinfo=UTC)
    assert "departure_local" in field_error(body(), too_late)


def test_the_departure_may_be_up_to_48_hours_ahead() -> None:
    now = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
    assert parse(body(departure_local="2026-11-26T15:00"), now)  # exactly +48 h
    errors = field_error(body(departure_local="2026-11-26T15:01"), now)
    assert errors["departure_local"] == "Departure must be within the next 48 hours."


@pytest.mark.parametrize("text", ["tomorrow", "2026-11-24", "24/11/2026 15:00", "", "15:00"])
def test_a_departure_must_be_an_iso_wall_clock_time(text: str) -> None:
    assert "departure_local" in field_error(body(departure_local=text))


@pytest.mark.parametrize("text", ["2026-11-24T15:00Z", "2026-11-24T15:00:00+00:00"])
def test_a_departure_with_a_utc_offset_is_rejected(text: str) -> None:
    errors = field_error(body(departure_local=text))
    assert "without a UTC offset" in errors["departure_local"]
