"""Provider interfaces and the plain data they exchange.

Adapters (TomTom, Open-Meteo, fixtures) implement these protocols, so a provider can be swapped by
writing one adapter. Nothing here talks to the network.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from core.models import HourlySeries, Point
from core.rules import Rules

_KG_PER_LB = 0.45359237


class ProviderError(Exception):
    """Base class for provider failures."""


class ProviderUnavailable(ProviderError):  # noqa: N818 - reads better as a state than as "Error"
    """The provider is down, rate-limited or timed out: try again later."""


class NoRoute(ProviderError):  # noqa: N818
    """The provider found no truck route between the two places."""


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True, order=True)
class GridPoint:
    """A weather location snapped to the grid; also the cache key."""

    lat: float
    lon: float


@dataclass(frozen=True)
class Vehicle:
    """What the routing engine needs to know about the truck (gross weight, not cargo)."""

    weight_kg: float
    max_speed_kmh: float


def vehicle_for_load(load_lb: float, rules: Rules) -> Vehicle:
    """Gross vehicle weight = configured tare weight + cargo (plan.md section 4.11)."""
    gross_lb = rules.truck.tare_weight_lb + load_lb
    return Vehicle(weight_kg=gross_lb * _KG_PER_LB, max_speed_kmh=rules.truck.max_speed_kmh)


@dataclass(frozen=True)
class RoadMark:
    """The road the truck is on from `mile` until the next mark."""

    mile: float
    road: str


@dataclass(frozen=True)
class RawRoute:
    """A truck route as returned by the routing engine, in miles and seconds."""

    points: tuple[Point, ...]  # full-resolution geometry
    distance_mi: float  # as reported by the provider
    drive_s: float  # provider travel time, without required stops
    # (miles from start, seconds from start) pairs, including (0, 0) and the end of the route.
    anchors: tuple[tuple[float, float], ...]
    roads: tuple[RoadMark, ...]


class RoutingProvider(Protocol):
    def routes(
        self, origin: Point, destination: Point, depart_at_utc: datetime, vehicle: Vehicle
    ) -> list[RawRoute]:
        """Up to the provider's alternatives, best first. Raises NoRoute / ProviderUnavailable."""
        ...

    def search(self, query: str, limit: int) -> list[Place]:
        """Autocomplete for US places. Raises ProviderUnavailable."""
        ...


class WeatherProvider(Protocol):
    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        """Hourly series (UTC) per point; a point without data is simply absent from the result.
        Raises ProviderUnavailable."""
        ...
