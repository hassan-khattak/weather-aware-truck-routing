"""TomTom truck routing adapter (plan.md sections 4.7, 6).

Calls the Calculate Route API with the truck profile and converts the response into plain
`RawRoute`s: full-resolution geometry, timing anchors (miles, seconds) taken from the guidance
instructions, and the road name along the route. The browser never talks to TomTom.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from core.models import Point
from providers.base import (
    NoRoute,
    Place,
    ProviderError,
    ProviderUnavailable,
    RawRoute,
    RoadMark,
    Vehicle,
)

_METERS_PER_MILE = 1609.344
_BASE_URL = "https://api.tomtom.com"
# TomTom 400 codes that mean "there is no truck route for these two places".
_NO_ROUTE_CODES = {"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"}
_ROUTE_CACHE_TTL_S = 30 * 60
_PLACES_CACHE_TTL_S = 24 * 60 * 60
# TomTom is asked for more results than the UI shows, because filtering and de-duplicating
# (Alaska, Hawaii, territories, repeated entries) removes some.
_SEARCH_FETCH = 10
# The continental US plus DC: the only places the app routes between (plan.md section 3.13).
_SUPPORTED_STATES = frozenset(
    "AL AZ AR CA CO CT DE DC FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)


class Cache(Protocol):
    """The slice of Django's cache API the adapters use."""

    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any, timeout: float | None = ...) -> None: ...


def _miles(meters: float) -> float:
    return meters / _METERS_PER_MILE


def _anchors(route: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    """(miles, seconds) timing points: origin, every guidance instruction, destination."""
    summary = route["summary"]
    pairs = [(0.0, 0.0)]
    for instruction in route.get("guidance", {}).get("instructions", []):
        pairs.append(
            (
                _miles(instruction["routeOffsetInMeters"]),
                float(instruction["travelTimeInSeconds"]),
            )
        )
    pairs.append((_miles(summary["lengthInMeters"]), float(summary["travelTimeInSeconds"])))

    # Guard against any out-of-order or duplicate points so downstream interpolation is safe.
    cleaned: list[tuple[float, float]] = []
    for miles, seconds in pairs:
        if cleaned:
            miles, seconds = max(miles, cleaned[-1][0]), max(seconds, cleaned[-1][1])
            if (miles, seconds) == cleaned[-1]:
                continue
        cleaned.append((miles, seconds))
    return tuple(cleaned)


def _roads(route: dict[str, Any]) -> tuple[RoadMark, ...]:
    """The road the truck is on, as it changes along the route (route number if there is one)."""
    marks: list[RoadMark] = []
    for instruction in route.get("guidance", {}).get("instructions", []):
        numbers = instruction.get("roadNumbers") or []
        name = numbers[0] if numbers else instruction.get("street")
        if not name or (marks and marks[-1].road == name):
            continue
        marks.append(RoadMark(mile=_miles(instruction["routeOffsetInMeters"]), road=name))
    return tuple(marks)


def parse_places(payload: dict[str, Any]) -> list[Place]:
    """Search results in the continental US, without repeats, in TomTom's order."""
    places: list[Place] = []
    seen: set[tuple[str, float, float]] = set()
    for result in payload.get("results", []):
        address = result.get("address", {})
        state = address.get("countrySubdivision")
        label = address.get("freeformAddress")
        position = result.get("position")
        if state not in _SUPPORTED_STATES or not label or not position:
            continue
        lat, lon = position["lat"], position["lon"]
        key = (label, round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)
        places.append(Place(label=label, lat=lat, lon=lon))
    return places


def parse_routes(payload: dict[str, Any]) -> list[RawRoute]:
    """Convert a Calculate Route response into `RawRoute`s (best first, as TomTom orders them)."""
    routes = []
    for route in payload.get("routes", []):
        points = tuple(
            (point["latitude"], point["longitude"])
            for leg in route["legs"]
            for point in leg["points"]
        )
        summary = route["summary"]
        routes.append(
            RawRoute(
                points=points,
                distance_mi=_miles(summary["lengthInMeters"]),
                drive_s=float(summary["travelTimeInSeconds"]),
                anchors=_anchors(route),
                roads=_roads(route),
            )
        )
    return routes


class TomTomRoutingProvider:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        cache: Cache | None = None,
        base_url: str = _BASE_URL,
        timeout_s: float = 25.0,
        max_alternatives: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("TomTom API key is not configured")
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout_s)
        self._cache = cache
        self._base_url = base_url
        self._max_alternatives = max_alternatives

    def _params(self, depart_at_utc: datetime, vehicle: Vehicle) -> dict[str, str]:
        departure = depart_at_utc.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "key": self._api_key,
            "travelMode": "truck",
            "vehicleCommercial": "true",
            "vehicleWeight": str(round(vehicle.weight_kg)),
            "vehicleMaxSpeed": str(round(vehicle.max_speed_kmh)),
            "departAt": departure,
            "maxAlternatives": str(self._max_alternatives),
            "instructionsType": "text",
            "language": "en-US",
            "traffic": "true",
            "routeRepresentation": "polyline",
        }

    @staticmethod
    def _cache_key(origin: Point, destination: Point, params: dict[str, str]) -> str:
        inputs = {
            "o": [round(v, 5) for v in origin],
            "d": [round(v, 5) for v in destination],
            "p": {k: v for k, v in params.items() if k != "key"},
        }
        digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        return f"route:v1:{digest}"

    def routes(
        self, origin: Point, destination: Point, depart_at_utc: datetime, vehicle: Vehicle
    ) -> list[RawRoute]:
        params = self._params(depart_at_utc, vehicle)
        cache_key = self._cache_key(origin, destination, params)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return list(cached)

        locations = f"{origin[0]:.5f},{origin[1]:.5f}:{destination[0]:.5f},{destination[1]:.5f}"
        url = f"{self._base_url}/routing/1/calculateRoute/{locations}/json"
        try:
            response = self._client.get(url, params=params)
        except httpx.HTTPError:
            # `from None`: httpx errors carry the request URL, which contains the API key.
            raise ProviderUnavailable("TomTom routing is unreachable") from None

        routes = self._handle(response)
        if self._cache is not None:
            self._cache.set(cache_key, routes, _ROUTE_CACHE_TTL_S)
        return routes

    def search(self, query: str, limit: int) -> list[Place]:
        """Autocomplete for cities, addresses and ZIP codes in the continental US."""
        text = " ".join(query.split())
        cache_key = f"places:v1:{text.lower()}"
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return list(cached)[:limit]

        params = {
            "key": self._api_key,
            "typeahead": "true",
            "limit": str(_SEARCH_FETCH),
            "countrySet": "US",
            "idxSet": "Geo,Addr,PAD,Str",
            "language": "en-US",
        }
        url = f"{self._base_url}/search/2/search/{quote(text, safe='')}.json"
        try:
            response = self._client.get(url, params=params)
        except httpx.HTTPError:
            raise ProviderUnavailable("TomTom search is unreachable") from None
        if response.status_code == 400:
            raise ProviderError("TomTom rejected the search request")
        if response.status_code != 200:
            raise ProviderUnavailable(f"TomTom search unavailable (HTTP {response.status_code})")

        places = parse_places(response.json())
        if self._cache is not None:
            self._cache.set(cache_key, places, _PLACES_CACHE_TTL_S)
        return places[:limit]

    @staticmethod
    def _handle(response: httpx.Response) -> list[RawRoute]:
        if response.status_code == 200:
            routes = parse_routes(response.json())
            if not routes:
                raise NoRoute("TomTom returned no routes")
            return routes
        if response.status_code == 400:
            code = _error_code(response)
            if code in _NO_ROUTE_CODES:
                raise NoRoute(f"no truck route found ({code})")
            raise ProviderError(f"TomTom rejected the request ({code or 'unknown error'})")
        # 401/403 (bad or exhausted key), 429 (rate limited), 5xx: not the user's fault.
        raise ProviderUnavailable(f"TomTom routing unavailable (HTTP {response.status_code})")


def _error_code(response: httpx.Response) -> str | None:
    try:
        code = response.json().get("detailedError", {}).get("code")
    except ValueError:
        return None
    return code if isinstance(code, str) else None
