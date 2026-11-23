"""Shared domain types. Pure Python: no Django, no I/O."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Self

# (latitude, longitude) in decimal degrees.
Point = tuple[float, float]


class Level(IntEnum):
    """Risk level. LOW..NO_TRAVEL are ordinal (0..4).

    NO_FORECAST is a sentinel for "we have no weather for this place and time". It is
    deliberately below LOW so it can never win a max() over real levels, and it is never
    counted as safe: callers must treat it separately (see RANKED_LEVELS).
    """

    NO_FORECAST = -1
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return _LABELS[self]

    @classmethod
    def from_name(cls, name: str) -> Self:
        return cls[name]


_LABELS: dict[Level, str] = {
    Level.NO_FORECAST: "No forecast",
    Level.LOW: "Low",
    Level.MODERATE: "Moderate",
    Level.HIGH: "High",
    Level.SEVERE: "Severe",
    Level.NO_TRAVEL: "No Travel",
}

# The five ordinal levels, lowest first. NO_FORECAST is not part of the scale.
RANKED_LEVELS: tuple[Level, ...] = (
    Level.LOW,
    Level.MODERATE,
    Level.HIGH,
    Level.SEVERE,
    Level.NO_TRAVEL,
)


@dataclass(frozen=True)
class Weather:
    """Weather at one place and time, in imperial units (mph, inches per hour)."""

    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
