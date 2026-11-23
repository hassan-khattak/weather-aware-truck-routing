"""Risk classification and load rules (plan.md sections 3.4, 3.5, 4.2-4.5)."""

from pathlib import Path

import pytest
from core.risk import classify
from hypothesis import given
from hypothesis import strategies as st

from core.models import RANKED_LEVELS, Level, Weather
from core.rules import Classification, load_rules

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")

LOW, MOD, HIGH, SEV, NT = (
    Level.LOW,
    Level.MODERATE,
    Level.HIGH,
    Level.SEVERE,
    Level.NO_TRAVEL,
)


def wx(
    wind: float = 0.0, rain: float = 0.0, snow: float = 0.0, gust: float | None = None
) -> Weather:
    return Weather(
        wind_mph=wind,
        gust_mph=wind if gust is None else gust,
        rain_in_hr=rain,
        snow_in_hr=snow,
    )


@pytest.mark.parametrize(
    ("wind", "expected"),
    [
        (24.9, LOW),
        (25, MOD),
        (34.9, MOD),
        (35, HIGH),
        (44.9, HIGH),
        (45, SEV),
        (54.9, SEV),
        (55, NT),
    ],
)
def test_wind_boundaries(wind: float, expected: Level) -> None:
    assert classify(wx(wind=wind), 0, RULES).level == expected


@pytest.mark.parametrize(
    ("rain", "expected"),
    [
        (0.09, LOW),
        (0.10, MOD),
        (0.24, MOD),
        (0.25, HIGH),
        (0.49, HIGH),
        (0.50, SEV),
        (1.00, SEV),
        (1.01, NT),
    ],
)
def test_rain_boundaries(rain: float, expected: Level) -> None:
    assert classify(wx(rain=rain), 0, RULES).level == expected


@pytest.mark.parametrize(
    ("snow", "expected"),
    [
        (0.49, LOW),
        (0.5, MOD),
        (0.99, MOD),
        (1.0, HIGH),
        (1.99, HIGH),
        (2.0, SEV),
        (3.0, SEV),
        (3.01, NT),
    ],
)
def test_snow_boundaries(snow: float, expected: Level) -> None:
    assert classify(wx(snow=snow), 0, RULES).level == expected


def test_rain_exactly_0_25_is_high() -> None:
    assert classify(wx(rain=0.25), 0, RULES).level == HIGH


def test_rain_exactly_1_00_is_severe_not_no_travel() -> None:
    assert classify(wx(rain=1.00), 0, RULES).level == SEV


def test_snow_exactly_3_0_is_severe_not_no_travel() -> None:
    assert classify(wx(snow=3.0), 0, RULES).level == SEV


@pytest.mark.parametrize(
    ("wind", "load_lb", "expected"),
    [
        (50, 30_000, SEV),
        (50, 30_001, NT),
        (40, 40_000, HIGH),
        (40, 40_001, SEV),
        (56, 1_000, NT),
        (44.9, 80_000, SEV),
        (34.9, 80_000, MOD),
    ],
)
def test_load_rules(wind: float, load_lb: float, expected: Level) -> None:
    assert classify(wx(wind=wind), load_lb, RULES).level == expected


def test_load_rules_can_only_raise_never_lower() -> None:
    # Snow already says No Travel; a 45,000 lb load with wind 40 (Severe by load) must not lower it.
    assert classify(wx(wind=40, snow=3.01), 45_000, RULES).level == NT


def test_load_rules_do_not_apply_to_rain_or_snow() -> None:
    assert classify(wx(rain=0.30), 80_000, RULES).level == HIGH
    assert classify(wx(snow=1.0), 80_000, RULES).level == HIGH


def test_level_is_the_worst_of_wind_rain_and_snow() -> None:
    assert classify(wx(wind=10, rain=0.10, snow=1.0), 0, RULES).level == HIGH


def test_calm_dry_weather_is_low_with_no_reasons() -> None:
    result = classify(wx(), 40_000, RULES)
    assert result.level == LOW
    assert result.reasons == ()


def test_reasons_explain_base_level_and_load_rule() -> None:
    result = classify(wx(wind=38), 42_000, RULES)
    assert result.level == SEV
    assert result.reasons == (
        "Wind 38 mph → High",
        "Load 42,000 lb > 40,000 with wind 35–44 mph → Severe",
    )


def test_reasons_list_every_condition_that_is_not_low() -> None:
    result = classify(wx(wind=26, rain=0.30, snow=0.6), 0, RULES)
    assert result.level == HIGH
    assert result.reasons == (
        "Wind 26 mph → Moderate",
        "Rain 0.3 in/hr → High",
        "Snow 0.6 in/hr → Moderate",
    )


def test_load_reason_is_omitted_when_the_load_rule_does_not_raise_the_level() -> None:
    result = classify(wx(wind=56), 80_000, RULES)
    assert result.reasons == ("Wind 56 mph → No Travel",)


def test_gusts_are_ignored_by_default() -> None:
    assert classify(wx(wind=10, gust=60), 0, RULES).level == LOW


def test_gust_source_classifies_on_gusts_and_says_so() -> None:
    gust_rules = RULES.model_copy(update={"classification": Classification(wind_source="gust")})
    result = classify(wx(wind=10, gust=40), 0, gust_rules)
    assert result.level == HIGH
    assert result.reasons == ("Gust 40 mph → High",)


weather_strategy = st.builds(
    Weather,
    wind_mph=st.floats(0, 120),
    gust_mph=st.floats(0, 160),
    rain_in_hr=st.floats(0, 3),
    snow_in_hr=st.floats(0, 6),
)
load_strategy = st.floats(0, 120_000)


@given(weather=weather_strategy, load=load_strategy)
def test_property_load_rules_never_lower_a_level(weather: Weather, load: float) -> None:
    assert classify(weather, load, RULES).level >= classify(weather, 0, RULES).level


@given(weather=weather_strategy, a=load_strategy, b=load_strategy)
def test_property_heavier_load_never_gives_a_lower_level(
    weather: Weather, a: float, b: float
) -> None:
    light, heavy = sorted((a, b))
    assert classify(weather, light, RULES).level <= classify(weather, heavy, RULES).level


@given(weather=weather_strategy, load=load_strategy)
def test_property_every_level_is_defined_and_non_low_levels_have_reasons(
    weather: Weather, load: float
) -> None:
    result = classify(weather, load, RULES)
    assert result.level in RANKED_LEVELS
    if result.level != Level.LOW:
        assert len(result.reasons) >= 1
