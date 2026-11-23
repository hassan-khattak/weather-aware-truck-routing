"""X-Force-Error: failures on demand, in fixture mode only."""

from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from api.force_error import FORCEABLE

EXPECTED = {
    "NO_ROUTE": 422,
    "OUT_OF_COVERAGE": 422,
    "PROVIDER_UNAVAILABLE": 503,
    "TRIP_EXPIRED": 410,
    "RATE_LIMITED": 429,
}
ENDPOINTS = [
    ("get", "/api/v1/places?q=denver", None),
    ("post", "/api/v1/routes", {}),
    ("post", "/api/v1/risk", {"trip_id": "x"}),
]


def call(method: str, url: str, data: Any, code: str | None) -> Any:
    client = APIClient()
    headers: dict[str, Any] = {"HTTP_X_FORCE_ERROR": code} if code else {}
    if method == "get":
        return client.get(url, **headers)
    return client.post(url, data, format="json", **headers)


@pytest.mark.parametrize(("method", "url", "data"), ENDPOINTS)
@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_each_code_gives_its_normal_response(method: str, url: str, data: Any, code: str) -> None:
    response = call(method, url, data, code)
    assert response.status_code == EXPECTED[code]
    assert response.json()["error"]["code"] == code


def test_rate_limit_says_how_long_to_wait() -> None:
    assert call("post", "/api/v1/routes", {}, "RATE_LIMITED")["Retry-After"] == "61"


def test_unknown_codes_are_a_validation_error() -> None:
    response = call("post", "/api/v1/routes", {}, "NOPE")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "RATE_LIMITED" in response.json()["error"]["message"]


@override_settings(PROVIDERS_MODE="live")
def test_the_header_is_ignored_outside_fixture_mode() -> None:
    response = call("post", "/api/v1/routes", {}, "PROVIDER_UNAVAILABLE")
    assert response.status_code == 400  # the empty body is invalid, nothing was forced
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_the_list_of_codes_is_complete() -> None:
    assert set(FORCEABLE) == set(EXPECTED)
