"""GET /api/v1/places (plan.md section 7.2)."""

from typing import Any

import pytest
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from providers.base import ProviderUnavailable

URL = "/api/v1/places"


def get(query: str | None) -> Any:
    return APIClient().get(URL, {} if query is None else {"q": query})


def test_returns_matching_places_with_coordinates() -> None:
    response = get("Den")
    assert response.status_code == 200
    assert response.json() == [{"label": "Denver, CO", "lat": 39.7392, "lon": -104.9903}]


def test_the_query_is_trimmed_and_case_insensitive() -> None:
    assert get("  chey  ").json()[0]["label"] == "Cheyenne, WY"


def test_no_match_is_an_empty_list() -> None:
    response = get("zzzz")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("query", [None, "", "de", "  d  "])
def test_a_query_under_three_characters_is_rejected(query: str | None) -> None:
    response = get(query)
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["fields"]["q"] == "Type at least 3 characters to search."


def test_a_provider_outage_is_a_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        def search(self, query: str, limit: int) -> list[Any]:
            raise ProviderUnavailable("down")

    monkeypatch.setattr("api.views.routing_provider", lambda: Down())
    response = get("Den")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_places_are_rate_limited_per_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"places": "3/hour"})
    client = APIClient()
    statuses = [client.get(URL, {"q": "Den"}).status_code for _ in range(5)]
    assert statuses == [200, 200, 200, 429, 429]
    limited = client.get(URL, {"q": "Den"})
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in limited


def test_clients_are_limited_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"places": "1/hour"})
    first = APIClient(REMOTE_ADDR="10.0.0.1")
    second = APIClient(REMOTE_ADDR="10.0.0.2")
    assert first.get(URL, {"q": "Den"}).status_code == 200
    assert first.get(URL, {"q": "Den"}).status_code == 429
    assert second.get(URL, {"q": "Den"}).status_code == 200


def test_the_health_check_is_never_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"places": "1/hour"})
    assert all(APIClient().get("/api/v1/health").status_code == 200 for _ in range(5))
