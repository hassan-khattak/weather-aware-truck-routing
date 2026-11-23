"""POST /api/v1/routes (plan.md section 7.3) in fixture mode."""

import pickle
from datetime import UTC, datetime
from typing import Any

import pytest
import time_machine
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from api.rules import get_rules
from api.validation import Departure, TripRequest
from providers.base import ProviderUnavailable
from providers.fixtures_provider import FixtureRoutingProvider
from providers.sample_trips import SAMPLE_TRIPS
from trips.planner import plan_trip
from trips.store import TRIP_TTL_S, load_trip, save_trip

URL = "/api/v1/routes"
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)  # 11:00 in Denver (MST)
DENVER = {"label": "Denver, CO", "lat": 39.7392, "lon": -104.9903}
CHEYENNE = {"label": "Cheyenne, WY", "lat": 41.1400, "lon": -104.8202}
CHICAGO = {"label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298}
DALLAS = {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970}


def body(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "origin": DENVER,
        "destination": CHEYENNE,
        "departure_local": "2026-11-24T14:00",
        "load_lb": 42_000,
    }
    data.update(overrides)
    return data


def post(data: Any) -> Any:
    return APIClient().post(URL, data, format="json")


@pytest.fixture(autouse=True)
def frozen_time() -> Any:
    with time_machine.travel(NOW, tick=False):
        yield


def test_a_valid_request_returns_trip_routes_and_departure() -> None:
    response = post(body())
    assert response.status_code == 200
    data = response.json()
    assert data["trip_id"].startswith("t_")
    assert data["departure"] == {
        "utc": "2026-11-24T21:00:00Z",  # 14:00 MST
        "tz": "America/Denver",
        "local": "2026-11-24T14:00",
    }
    assert data["interval_mi"] == 10
    assert [r["id"] for r in data["routes"]] == ["A", "B"]
    assert data["notes"] == ["2 distinct truck routes found for this trip."]
    assert data["warnings"] == []


def test_the_trip_is_stored_for_the_risk_step() -> None:
    data = post(body()).json()
    trip = load_trip(data["trip_id"])
    assert trip is not None
    assert len(trip.routes) == 2
    assert trip.request.load_lb == 42_000


def test_each_request_gets_its_own_trip_id() -> None:
    first, second = post(body()).json(), post(body()).json()
    assert first["trip_id"] != second["trip_id"]


def test_a_heavy_load_adds_a_warning() -> None:
    assert len(post(body(load_lb=50_000)).json()["warnings"]) == 1


def test_a_long_trip_picks_a_wider_interval_and_has_rest_stops() -> None:
    data = post(body(origin=CHICAGO, destination=DALLAS, departure_local="2026-11-24T13:00")).json()
    assert data["interval_mi"] == 50
    assert [s["type"] for s in data["routes"][0]["stops"]] == ["break", "rest"]


def test_validation_errors_use_the_error_format() -> None:
    response = post(body(load_lb=500))
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["fields"]["load_lb"] == "Load must be between 1,000 and 80,000 lb."


def test_a_departure_in_the_past_is_rejected() -> None:
    response = post(body(departure_local="2026-11-24T09:00"))
    assert response.status_code == 400
    assert (
        response.json()["error"]["fields"]["departure_local"] == "Departure can't be in the past."
    )


def test_a_trip_outside_the_us_is_out_of_coverage() -> None:
    toronto = {"label": "Toronto, ON", "lat": 43.6532, "lon": -79.3832}
    response = post(body(destination=toronto))
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "OUT_OF_COVERAGE",
            "message": "Currently supports routes within the continental US.",
        }
    }


def test_an_unroutable_trip_is_no_route() -> None:
    miami = {"label": "Miami, FL", "lat": 25.7617, "lon": -80.1918}
    response = post(body(origin=miami, departure_local="2026-11-24T13:00"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ROUTE"


def test_a_routing_outage_is_a_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        def routes(self, *args: Any) -> list[Any]:
            raise ProviderUnavailable("down")

    monkeypatch.setattr("api.views.routing_provider", lambda: Down())
    response = post(body())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_route_searches_are_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"routes": "2/hour"})
    statuses = [post(body()).status_code for _ in range(4)]
    assert statuses == [200, 200, 429, 429]
    assert post(body()).json()["error"]["code"] == "RATE_LIMITED"


def test_only_post_is_allowed() -> None:
    assert APIClient().get(URL).status_code == 405


def test_a_body_that_is_not_json_is_rejected() -> None:
    response = APIClient().post(URL, "origin=x", content_type="application/x-www-form-urlencoded")
    assert response.status_code == 415


# --- trip storage ---


class SpyCache:
    """Records what is stored, then delegates to the real cache."""

    def __init__(self) -> None:
        self.timeout: float | None = None
        self.size = 0

    def set(self, key: str, value: Any, timeout: float | None = None) -> None:
        self.timeout, self.size = timeout, len(value)
        cache.set(key, value, timeout)

    def get(self, key: str) -> Any:
        return cache.get(key)


def test_stored_trips_are_compressed_and_expire_after_an_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trip_def = SAMPLE_TRIPS[3]  # Seattle -> Chicago: the largest recorded trip
    request = TripRequest(
        origin=trip_def.origin,
        destination=trip_def.destination,
        departure=Departure(utc=NOW, tz="America/Los_Angeles", local=NOW.replace(tzinfo=None)),
        load_lb=42_000,
        warnings=(),
    )
    trip = plan_trip(request, FixtureRoutingProvider(), get_rules(), NOW)

    spy = SpyCache()
    monkeypatch.setattr("trips.store.cache", spy)
    trip_id = save_trip(trip)

    assert spy.timeout == TRIP_TTL_S == 3600
    assert spy.size < len(pickle.dumps(trip)) / 2  # compressed
    assert load_trip(trip_id) == trip


def test_unknown_or_expired_trips_load_as_none() -> None:
    assert load_trip("t_nope") is None
    trip_id = post(body()).json()["trip_id"]
    cache.clear()
    assert load_trip(trip_id) is None


def test_garbage_in_the_cache_is_not_a_trip() -> None:
    cache.set("trip:v1:t_bad", "not bytes", 60)
    assert load_trip("t_bad") is None
