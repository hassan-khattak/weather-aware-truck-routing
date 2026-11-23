"""Matching an ETA to forecast hours (plan.md section 4.8, trap T2)."""

from datetime import UTC, datetime, timedelta

import pytest

from core.forecast_hour import weather_at
from core.models import HourlySeries, Weather

START = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def series(
    wind: list[float | None],
    rain: list[float | None] | None = None,
    snow: list[float | None] | None = None,
    gust: list[float | None] | None = None,
) -> HourlySeries:
    n = len(wind)
    return HourlySeries(
        start_utc=START,
        wind_mph=tuple(wind),
        gust_mph=tuple(gust if gust is not None else wind),
        rain_in_hr=tuple(rain if rain is not None else [0.0] * n),
        snow_in_hr=tuple(snow if snow is not None else [0.0] * n),
    )


def at(hour: int, minute: int = 0, second: int = 0, micro: int = 0) -> datetime:
    return datetime(2026, 11, 24, hour, minute, second, micro, tzinfo=UTC)


def test_eta_exactly_on_the_hour_uses_that_hour_for_everything() -> None:
    s = series(wind=[10, 20, 30, 40], rain=[0.0, 0.1, 0.2, 0.3], snow=[0.0, 1.0, 2.0, 3.0])
    assert weather_at(s, at(14)) == Weather(
        wind_mph=30, gust_mph=30, rain_in_hr=0.2, snow_in_hr=2.0
    )


def test_precipitation_uses_the_hour_ending_after_the_eta() -> None:
    # 14:40 -> the 15:00 value (total for the hour ending at 15:00).
    s = series(wind=[10, 10, 10, 10], rain=[0.0, 0.0, 0.1, 0.9], snow=[0.0, 0.0, 0.5, 4.0])
    result = weather_at(s, at(14, 40))
    assert result is not None
    assert result.rain_in_hr == 0.9
    assert result.snow_in_hr == 4.0


def test_wind_is_the_higher_of_the_two_surrounding_hours() -> None:
    s = series(wind=[10, 20, 50, 30])
    result = weather_at(s, at(14, 40))  # between 14:00 (50) and 15:00 (30)
    assert result is not None
    assert result.wind_mph == 50


def test_wind_takes_the_later_hour_when_it_is_higher() -> None:
    s = series(wind=[10, 20, 30, 45])
    result = weather_at(s, at(14, 10))  # between 14:00 (30) and 15:00 (45)
    assert result is not None
    assert result.wind_mph == 45


def test_gusts_follow_the_same_rule_as_wind() -> None:
    s = series(wind=[10, 10, 10, 10], gust=[15, 25, 60, 35])
    result = weather_at(s, at(14, 30))
    assert result is not None
    assert result.gust_mph == 60


def test_one_second_after_the_hour_counts_as_the_next_hour() -> None:
    s = series(wind=[10, 10, 10, 10], rain=[0.0, 0.0, 0.1, 0.7])
    result = weather_at(s, at(14, 0, 1))
    assert result is not None
    assert result.rain_in_hr == 0.7


def test_microsecond_after_the_hour_counts_as_the_next_hour() -> None:
    s = series(wind=[10, 10, 10, 10], rain=[0.0, 0.0, 0.1, 0.7])
    result = weather_at(s, at(14, 0, 0, 1))
    assert result is not None
    assert result.rain_in_hr == 0.7


def test_missing_precipitation_hour_means_no_forecast() -> None:
    s = series(wind=[10, 10, 10, 10], rain=[0.0, 0.0, 0.1, None])
    assert weather_at(s, at(14, 40)) is None


def test_missing_wind_hour_means_no_forecast() -> None:
    s = series(wind=[10, 10, None, 10])
    assert weather_at(s, at(14, 40)) is None


def test_missing_snow_hour_means_no_forecast() -> None:
    s = series(wind=[10, 10, 10, 10], snow=[0.0, 0.0, 0.0, None])
    assert weather_at(s, at(14, 40)) is None


def test_eta_before_the_series_starts_has_no_forecast() -> None:
    s = series(wind=[10, 10, 10, 10])
    assert weather_at(s, START - timedelta(minutes=1)) is None


def test_eta_after_the_series_ends_has_no_forecast() -> None:
    s = series(wind=[10, 10, 10, 10])  # covers 12:00 .. 15:00
    assert weather_at(s, at(15, 1)) is None


def test_last_hour_of_the_series_is_usable_exactly_on_the_hour() -> None:
    s = series(wind=[10, 10, 10, 33])
    result = weather_at(s, at(15))
    assert result is not None
    assert result.wind_mph == 33


def test_naive_datetimes_are_rejected() -> None:
    s = series(wind=[10, 10, 10, 10])
    with pytest.raises(ValueError, match="timezone"):
        weather_at(s, datetime(2026, 11, 24, 14, 0))  # noqa: DTZ001
