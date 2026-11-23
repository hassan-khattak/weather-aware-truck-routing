"""Load and validate rules.yaml, the single home of every threshold and tunable."""

from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Level = Literal["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL"]


class RulesError(Exception):
    """rules.yaml is missing, unreadable or invalid."""


class _Model(BaseModel):
    # Unknown keys are errors so typos fail fast; populate_by_name lets `from_` map to "from".
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Classification(_Model):
    wind_source: Literal["sustained", "gust"]


class Band(_Model):
    level: Level
    from_: float = Field(alias="from")
    inclusive: bool


class Thresholds(_Model):
    wind_mph: list[Band]
    rain_in_hr: list[Band]
    snow_in_hr: list[Band]


class LoadRule(_Model):
    condition: Literal["wind_mph"]
    from_: float = Field(alias="from")
    to_exclusive: float | None
    load_gt_lb: float | None
    level: Level


class Scoring(_Model):
    class Rounding(_Model):
        miles: int
        avg_risk: int

    level_weights: dict[Level, float]
    rounding: Rounding


class IntervalRule(_Model):
    max_mi_exclusive: float | None = None
    max_mi_inclusive: float | None = None
    otherwise: bool = False
    interval_mi: float

    @model_validator(mode="after")
    def _exactly_one_bound(self) -> Self:
        bounds = [
            self.max_mi_exclusive is not None,
            self.max_mi_inclusive is not None,
            self.otherwise,
        ]
        if sum(bounds) != 1:
            raise ValueError(
                "interval needs exactly one of max_mi_exclusive, max_mi_inclusive, otherwise"
            )
        return self


class HoursOfService(_Model):
    break_after_driving_h: float
    break_duration_min: float
    max_driving_h: float
    rest_duration_h: float


class Truck(_Model):
    max_speed_kmh: float
    tare_weight_lb: float
    load_min_lb: float
    load_max_lb: float
    load_warning_lb: float


class Alternatives(_Model):
    max_overlap_ratio: float
    max_time_ratio: float
    via_offset_ratio: float


class Departure(_Model):
    max_ahead_h: float
    past_grace_min: float
    long_range_note_h: float


class GridTier(_Model):
    """Heatmap cell size for trips up to a given length (the last tier is `otherwise`)."""

    max_mi_inclusive: float | None = None
    otherwise: bool = False
    deg: float

    @model_validator(mode="after")
    def _exactly_one_bound(self) -> Self:
        if (self.max_mi_inclusive is not None) == self.otherwise:
            raise ValueError("heatmap tier needs exactly one of max_mi_inclusive, otherwise")
        return self


class WeatherGrid(_Model):
    checkpoint_deg: float
    heatmap_tiers: list[GridTier]
    corridor_mi: float
    forecast_ttl_s: int
    stale_ttl_s: int
    batch_size: int

    @field_validator("heatmap_tiers")
    @classmethod
    def _tiers_end_with_otherwise(cls, value: list[GridTier]) -> list[GridTier]:
        if not value or not value[-1].otherwise:
            raise ValueError("heatmap_tiers must end with an 'otherwise' entry")
        return value

    @model_validator(mode="after")
    def _cells_are_multiples_of_the_checkpoint_grid(self) -> Self:
        for tier in self.heatmap_tiers:
            ratio = tier.deg / self.checkpoint_deg
            if abs(ratio - round(ratio)) > 1e-6:
                raise ValueError(
                    f"heatmap tier size {tier.deg} must be a multiple of checkpoint_deg "
                    f"({self.checkpoint_deg})"
                )
        return self


class Heatmap(_Model):
    hours: int


class Display(_Model):
    """Presentation tuning: how much detail the browser gets."""

    # Route lines are simplified (Douglas-Peucker) to this many degrees before being sent for
    # drawing; the full geometry is kept for all calculations. 0.002 deg is about 0.14 miles.
    geometry_tolerance_deg: float = Field(gt=0)


class Rules(_Model):
    version: int
    levels: list[Level]
    classification: Classification
    thresholds: Thresholds
    load_rules: list[LoadRule]
    scoring: Scoring
    intervals: list[IntervalRule]
    hours_of_service: HoursOfService
    truck: Truck
    alternatives: Alternatives
    departure: Departure
    weather_grid: WeatherGrid
    heatmap: Heatmap
    display: Display

    @field_validator("intervals")
    @classmethod
    def _intervals_end_with_otherwise(cls, value: list[IntervalRule]) -> list[IntervalRule]:
        if not value or not value[-1].otherwise:
            raise ValueError("intervals must end with an 'otherwise' entry")
        return value

    @model_validator(mode="after")
    def _weights_cover_levels(self) -> Self:
        if set(self.scoring.level_weights) != set(self.levels):
            raise ValueError("scoring.level_weights must have exactly the keys listed in levels")
        return self


def _format_error(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "<root>"
        lines.append(f"{where}: {item['msg']} (got {item['input']!r})")
    return "Invalid rules.yaml:\n  " + "\n  ".join(lines)


def parse_rules(document: dict[str, Any]) -> Rules:
    """Validate an already-loaded document."""
    try:
        return Rules.model_validate(document)
    except ValidationError as error:
        raise RulesError(_format_error(error)) from error


def load_rules(path: Path | str) -> Rules:
    """Read and validate a rules.yaml file."""
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RulesError(f"rules file not found: {file}") from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise RulesError(f"Invalid YAML in {file}: {error}") from error
    if not isinstance(document, dict):
        raise RulesError(f"{file} must contain a mapping at the top level")
    return parse_rules(document)
