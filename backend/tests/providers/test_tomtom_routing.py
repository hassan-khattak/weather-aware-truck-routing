"""TomTom routing adapter against a trimmed real response (no live calls)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from providers.base import NoRoute, ProviderError, ProviderUnavailable, Vehicle
from providers.tomtom import TomTomRoutingProvider

FIXTURE = Path(__file__).resolve().parents[2] / "providers/fixtures/tomtom_route_dallas_denver.json"
DALLAS = (32.7767, -96.7970)
DENVER = (39.7392, -104.9903)
DEPART = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
VEHICLE = Vehicle(weight_kg=34_926.6, max_speed_kmh=105)
URL = "https://api.tomtom.com/routing/1/calculateRoute/32.77670,-96.79700:39.73920,-104.99030/json"
SECRET = "secret-key-123"


@pytest.fixture
def payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    return data


class DictCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def set(self, key: str, value: Any, timeout: float | None = None) -> None:
        self.store[key] = value


def provider(cache: DictCache | None = None) -> TomTomRoutingProvider:
    return TomTomRoutingProvider(SECRET, cache=cache)


@respx.mock
def test_parses_real_routes_into_geometry_anchors_and_roads(payload: dict[str, Any]) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
    routes = provider().routes(DALLAS, DENVER, DEPART, VEHICLE)

    assert len(routes) == 3
    best = routes[0]
    assert best.distance_mi == pytest.approx(797.9, abs=0.1)
    assert best.drive_s == 47472
    assert best.points[0] == pytest.approx((32.77667, -96.79699), abs=1e-5)
    assert best.points[-1] == pytest.approx((39.73922, -104.99024), abs=1e-3)

    # Anchors: origin, every instruction, destination; never going backwards.
    assert best.anchors[0] == (0.0, 0.0)
    assert best.anchors[-1] == pytest.approx((best.distance_mi, 47472))
    miles = [a[0] for a in best.anchors]
    seconds = [a[1] for a in best.anchors]
    assert miles == sorted(miles)
    assert seconds == sorted(seconds)
    assert len(best.anchors) > 20

    # Road names prefer route numbers and change along the route.
    names = [mark.road for mark in best.roads]
    assert "I-35E N" in names
    assert all(a != b for a, b in zip(names, names[1:], strict=False))
    assert [m.mile for m in best.roads] == sorted(m.mile for m in best.roads)


@respx.mock
def test_sends_the_truck_profile_with_the_agreed_parameters(payload: dict[str, Any]) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
    provider().routes(DALLAS, DENVER, DEPART, VEHICLE)

    params = dict(route.calls.last.request.url.params)
    assert params["travelMode"] == "truck"
    assert params["vehicleCommercial"] == "true"
    assert params["vehicleWeight"] == "34927"  # gross weight in kg, rounded
    assert params["vehicleMaxSpeed"] == "105"
    assert params["departAt"] == "2026-11-24T21:00:00Z"
    assert params["maxAlternatives"] == "2"
    assert params["instructionsType"] == "text"
    assert params["language"] == "en-US"
    assert params["key"] == SECRET


@respx.mock
def test_departure_in_another_zone_is_sent_as_utc(payload: dict[str, Any]) -> None:
    from datetime import timedelta, timezone

    route = respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
    local = datetime(2026, 11, 24, 15, 0, tzinfo=timezone(timedelta(hours=-6)))
    provider().routes(DALLAS, DENVER, local, VEHICLE)
    assert route.calls.last.request.url.params["departAt"] == "2026-11-24T21:00:00Z"


@respx.mock
@pytest.mark.parametrize("code", ["NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"])
def test_no_route_errors_become_no_route(code: str) -> None:
    body = {"detailedError": {"code": code, "message": "x"}}
    respx.get(URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(NoRoute):
        provider().routes(DALLAS, DENVER, DEPART, VEHICLE)


@respx.mock
def test_an_empty_route_list_is_no_route() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"routes": []}))
    with pytest.raises(NoRoute):
        provider().routes(DALLAS, DENVER, DEPART, VEHICLE)


@respx.mock
def test_other_bad_requests_are_provider_errors_not_no_route() -> None:
    body = {"detailedError": {"code": "BAD_REQUEST", "message": "x"}}
    respx.get(URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(ProviderError) as error:
        provider().routes(DALLAS, DENVER, DEPART, VEHICLE)
    assert not isinstance(error.value, NoRoute | ProviderUnavailable)


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_auth_rate_limit_and_server_errors_are_unavailable(status: int) -> None:
    respx.get(URL).mock(return_value=httpx.Response(status, json={}))
    with pytest.raises(ProviderUnavailable):
        provider().routes(DALLAS, DENVER, DEPART, VEHICLE)


@respx.mock
def test_network_failures_are_unavailable_and_never_leak_the_api_key() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(ProviderUnavailable) as error:
        provider().routes(DALLAS, DENVER, DEPART, VEHICLE)
    assert SECRET not in str(error.value)
    assert error.value.__cause__ is None


@respx.mock
def test_an_identical_second_request_is_served_from_the_cache(payload: dict[str, Any]) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
    cache = DictCache()
    first = provider(cache).routes(DALLAS, DENVER, DEPART, VEHICLE)
    second = provider(cache).routes(DALLAS, DENVER, DEPART, VEHICLE)

    assert route.call_count == 1
    assert second == first
    assert all(key.startswith("route:v1:") for key in cache.store)
    assert all(SECRET not in key for key in cache.store)


@respx.mock
def test_a_different_departure_or_weight_is_not_a_cache_hit(payload: dict[str, Any]) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
    cache = DictCache()
    p = provider(cache)
    p.routes(DALLAS, DENVER, DEPART, VEHICLE)
    p.routes(DALLAS, DENVER, datetime(2026, 11, 24, 22, 0, tzinfo=UTC), VEHICLE)
    p.routes(DALLAS, DENVER, DEPART, Vehicle(weight_kg=20_000, max_speed_kmh=105))
    assert route.call_count == 3


def test_a_missing_api_key_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="API key"):
        TomTomRoutingProvider("")


@respx.mock
def test_via_points_are_added_to_the_route_and_alternatives_are_not_requested(
    payload: dict[str, Any],
) -> None:
    url = (
        "https://api.tomtom.com/routing/1/calculateRoute/"
        "32.77670,-96.79700:36.00000,-100.50000:39.73920,-104.99030/json"
    )
    route = respx.get(url).mock(return_value=httpx.Response(200, json=payload))
    provider().routes(DALLAS, DENVER, DEPART, VEHICLE, via=[(36.0, -100.5)])
    assert route.calls.last.request.url.params["maxAlternatives"] == "0"


@respx.mock
def test_a_via_request_is_cached_separately_from_the_plain_route(payload: dict[str, Any]) -> None:
    respx.get(url__startswith="https://api.tomtom.com/routing/1/calculateRoute/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    cache = DictCache()
    p = provider(cache)
    p.routes(DALLAS, DENVER, DEPART, VEHICLE)
    p.routes(DALLAS, DENVER, DEPART, VEHICLE, via=[(36.0, -100.5)])
    p.routes(DALLAS, DENVER, DEPART, VEHICLE, via=[(36.0, -100.5)])
    assert len(cache.store) == 2


def test_the_fixture_provider_has_no_via_routes() -> None:
    from providers.fixtures_provider import FixtureRoutingProvider

    with pytest.raises(NoRoute):
        FixtureRoutingProvider().routes(
            (39.7392, -104.9903), (41.14, -104.8202), DEPART, VEHICLE, via=[(40.5, -105.2)]
        )
