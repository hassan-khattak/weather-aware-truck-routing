"""TomTom search adapter against trimmed real responses (no live calls)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from providers.base import Place, ProviderError, ProviderUnavailable, RoutingProvider
from providers.tomtom import TomTomRoutingProvider

FIXTURE = Path(__file__).resolve().parents[2] / "providers/fixtures/tomtom_search.json"
SEARCH_URL = "https://api.tomtom.com/search/2/search/{}.json"
SECRET = "secret-key-123"


@pytest.fixture
def responses() -> dict[str, Any]:
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


def test_the_tomtom_adapter_satisfies_the_routing_provider_protocol() -> None:
    adapter: RoutingProvider = provider()
    assert adapter is not None


@respx.mock
def test_returns_labels_and_coordinates(responses: dict[str, Any]) -> None:
    respx.get(SEARCH_URL.format("Dalla")).mock(
        return_value=httpx.Response(200, json=responses["dalla"])
    )
    places = provider().search("Dalla", 6)
    assert places[0] == Place(label="Dallas, TX", lat=32.777976, lon=-96.796215)
    assert [p.label for p in places][:3] == ["Dallas, TX", "Dallas, GA", "Dallas, NC"]


@respx.mock
def test_alaska_and_hawaii_are_excluded(responses: dict[str, Any]) -> None:
    respx.get(SEARCH_URL.format("Honolulu")).mock(
        return_value=httpx.Response(200, json=responses["hnl"])
    )
    labels = [p.label for p in provider().search("Honolulu", 6)]
    assert not any(label.endswith(", HI") for label in labels)
    assert "South Honolulu Street, Ashland, IL 62612" in labels  # lower-48 street kept

    respx.get(SEARCH_URL.format("Anchorage")).mock(
        return_value=httpx.Response(200, json=responses["anc"])
    )
    anchorage = [p.label for p in provider().search("Anchorage", 6)]
    assert anchorage == ["Anchorage, KY"]


@respx.mock
def test_territories_and_missing_data_are_dropped() -> None:
    body = {
        "results": [
            {
                "address": {"freeformAddress": "San Juan, PR", "countrySubdivision": "PR"},
                "position": {"lat": 18.4, "lon": -66.1},
            },
            {"address": {"countrySubdivision": "TX"}, "position": {"lat": 1.0, "lon": 2.0}},
            {
                "address": {"freeformAddress": "Austin, TX", "countrySubdivision": "TX"},
                "position": {"lat": 30.27, "lon": -97.74},
            },
        ]
    }
    respx.get(SEARCH_URL.format("x")).mock(return_value=httpx.Response(200, json=body))
    assert [p.label for p in provider().search("x", 6)] == ["Austin, TX"]


@respx.mock
def test_repeated_entries_are_collapsed() -> None:
    entry = {
        "address": {"freeformAddress": "Dallas, TX", "countrySubdivision": "TX"},
        "position": {"lat": 32.7780, "lon": -96.7962},
    }
    body = {"results": [entry, dict(entry), dict(entry)]}
    respx.get(SEARCH_URL.format("Dallas")).mock(return_value=httpx.Response(200, json=body))
    assert len(provider().search("Dallas", 6)) == 1


@respx.mock
def test_the_limit_is_respected(responses: dict[str, Any]) -> None:
    respx.get(SEARCH_URL.format("Dalla")).mock(
        return_value=httpx.Response(200, json=responses["dalla"])
    )
    assert len(provider().search("Dalla", 3)) == 3


@respx.mock
def test_zip_codes_and_streets_are_supported(responses: dict[str, Any]) -> None:
    respx.get(SEARCH_URL.format("60601")).mock(
        return_value=httpx.Response(200, json=responses["zip"])
    )
    labels = [p.label for p in provider().search("60601", 6)]
    assert labels[0] == "Chicago, IL 60601"


@respx.mock
def test_sends_us_only_typeahead_parameters_and_encodes_the_query(
    responses: dict[str, Any],
) -> None:
    route = respx.get(url__startswith="https://api.tomtom.com/search/2/search/").mock(
        return_value=httpx.Response(200, json=responses["dalla"])
    )
    provider().search("  St. Louis,  MO ", 6)
    request = route.calls.last.request
    assert request.url.raw_path.startswith(b"/search/2/search/St.%20Louis%2C%20MO.json")
    params = dict(request.url.params)
    assert params["typeahead"] == "true"
    assert params["countrySet"] == "US"
    assert params["key"] == SECRET


@respx.mock
def test_repeated_searches_are_cached_case_insensitively(responses: dict[str, Any]) -> None:
    route = respx.get(url__startswith="https://api.tomtom.com/search/2/search/").mock(
        return_value=httpx.Response(200, json=responses["dalla"])
    )
    cache = DictCache()
    first = provider(cache).search("Dalla", 6)
    second = provider(cache).search("dalla ", 6)
    assert route.call_count == 1
    assert first == second
    assert list(cache.store) == ["places:v1:dalla"]


@respx.mock
@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_service_errors_are_unavailable(status: int) -> None:
    respx.get(url__startswith="https://api.tomtom.com/search/2/search/").mock(
        return_value=httpx.Response(status)
    )
    with pytest.raises(ProviderUnavailable):
        provider().search("Dallas", 6)


@respx.mock
def test_bad_requests_are_provider_errors() -> None:
    respx.get(url__startswith="https://api.tomtom.com/search/2/search/").mock(
        return_value=httpx.Response(400)
    )
    with pytest.raises(ProviderError):
        provider().search("Dallas", 6)


@respx.mock
def test_network_failure_does_not_leak_the_key() -> None:
    respx.get(url__startswith="https://api.tomtom.com/search/2/search/").mock(
        side_effect=httpx.ConnectError("boom")
    )
    with pytest.raises(ProviderUnavailable) as error:
        provider().search("Dallas", 6)
    assert SECRET not in str(error.value)
