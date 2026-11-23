import dataclasses

import pytest

from core.models import RANKED_LEVELS, Level, Weather


def test_ranked_levels_have_ordinals_zero_to_four() -> None:
    assert [level.value for level in RANKED_LEVELS] == [0, 1, 2, 3, 4]
    assert [level.name for level in RANKED_LEVELS] == [
        "LOW",
        "MODERATE",
        "HIGH",
        "SEVERE",
        "NO_TRAVEL",
    ]


def test_levels_are_ordered_by_severity() -> None:
    assert Level.LOW < Level.MODERATE < Level.HIGH < Level.SEVERE < Level.NO_TRAVEL


def test_no_forecast_is_not_a_ranked_level() -> None:
    assert Level.NO_FORECAST not in RANKED_LEVELS


def test_no_forecast_can_never_win_a_max_over_levels() -> None:
    assert max(Level.LOW, Level.NO_FORECAST) == Level.LOW


def test_labels_are_human_readable() -> None:
    assert Level.NO_TRAVEL.label == "No Travel"
    assert Level.HIGH.label == "High"
    assert Level.NO_FORECAST.label == "No forecast"


def test_from_name_round_trips() -> None:
    for level in Level:
        assert Level.from_name(level.name) is level


def test_from_name_rejects_unknown_names() -> None:
    with pytest.raises(KeyError):
        Level.from_name("EXTREME")


def test_weather_is_immutable() -> None:
    weather = Weather(wind_mph=10.0, gust_mph=15.0, rain_in_hr=0.0, snow_in_hr=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        weather.wind_mph = 20.0  # type: ignore[misc]
