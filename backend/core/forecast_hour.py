"""Match an ETA to forecast hours (plan.md section 4.8)."""

from datetime import UTC, datetime, timedelta

from core.models import HourlySeries, Weather

_HOUR = timedelta(hours=1)


def _hour_index(series: HourlySeries, hour: datetime) -> int:
    return int((hour - series.start_utc) / _HOUR)


def _value(values: tuple[float | None, ...], index: int) -> float | None:
    if 0 <= index < len(values):
        return values[index]
    return None


def weather_at(series: HourlySeries, eta_utc: datetime) -> Weather | None:
    """Weather the truck meets at `eta_utc`, or None when any needed hour is missing.

    - Rain and snow are totals for the hour ending at a label, so they use the label
      `ceil_to_hour(ETA)` (an ETA exactly on the hour uses that hour).
    - Wind is instantaneous at the label, so it uses the higher of `floor` and `ceil`.
    """
    if eta_utc.tzinfo is None:
        raise ValueError("ETA must be timezone-aware (UTC)")
    eta = eta_utc.astimezone(UTC)

    floor = eta.replace(minute=0, second=0, microsecond=0)
    ceil = floor if eta == floor else floor + _HOUR
    low, high = _hour_index(series, floor), _hour_index(series, ceil)

    wind = (_value(series.wind_mph, low), _value(series.wind_mph, high))
    gust = (_value(series.gust_mph, low), _value(series.gust_mph, high))
    rain = _value(series.rain_in_hr, high)
    snow = _value(series.snow_in_hr, high)

    if None in wind or None in gust or rain is None or snow is None:
        return None
    return Weather(
        wind_mph=max(v for v in wind if v is not None),
        gust_mph=max(v for v in gust if v is not None),
        rain_in_hr=rain,
        snow_in_hr=snow,
    )
