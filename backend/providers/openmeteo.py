"""Open-Meteo hourly forecast adapter (plan.md sections 4.9, 6).

Requests imperial units directly (mph, inches), always in GMT, and converts the response into
`HourlySeries` per grid point:

- rain = `rain` + `showers`. Never `precipitation`: it includes snow as water equivalent, so a
  snowstorm would also count as heavy rain.
- snow = `snowfall` (depth), which is what the in/hr thresholds mean.
- values are rounded on ingest (wind 1 decimal, rain and snow 2) so float noise such as
  0.2499999 can never slip under a threshold.

Free tier limits (checked 2026-11-23): non-commercial use, every location in a request counts as
one call, 600 calls/minute, 5,000/hour, 10,000/day. Exceeding them returns HTTP 429.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from core.models import HourlySeries
from providers.base import GridPoint, ProviderError, ProviderUnavailable

_BASE_URL = "https://api.open-meteo.com"
_HOURLY = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _sum_rounded(a: float | None, b: float | None, digits: int) -> float | None:
    """a + b, or None if either is missing (an unknown hour must never look dry)."""
    return None if a is None or b is None else round(a + b, digits)


def parse_series(location: dict[str, Any]) -> HourlySeries:
    """One location object of an Open-Meteo response → `HourlySeries`."""
    hourly = location["hourly"]
    times = hourly["time"]
    start = datetime.fromisoformat(times[0]).replace(tzinfo=UTC)
    if len(times) > 1:
        step = datetime.fromisoformat(times[1]) - datetime.fromisoformat(times[0])
        if step != timedelta(hours=1):
            raise ProviderError("Open-Meteo returned a non-hourly series")

    rain = hourly["rain"]
    showers = hourly["showers"]
    return HourlySeries(
        start_utc=start,
        wind_mph=tuple(_round(v, 1) for v in hourly["wind_speed_10m"]),
        gust_mph=tuple(_round(v, 1) for v in hourly["wind_gusts_10m"]),
        rain_in_hr=tuple(_sum_rounded(r, s, 2) for r, s in zip(rain, showers, strict=True)),
        snow_in_hr=tuple(_round(v, 2) for v in hourly["snowfall"]),
    )


class OpenMeteoWeatherProvider:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        base_url: str = _BASE_URL,
        batch_size: int = 200,
        timeout_s: float = 40.0,
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout_s)
        self._base_url = base_url
        self._batch_size = batch_size

    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        """Hourly series covering the UTC days from `start_utc` to `end_utc`, in batches."""
        if start_utc.tzinfo is None or end_utc.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        result: dict[GridPoint, HourlySeries] = {}
        for first in range(0, len(points), self._batch_size):
            batch = points[first : first + self._batch_size]
            result.update(self._fetch(batch, start_utc, end_utc))
        return result

    def _fetch(
        self, batch: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        params = {
            "latitude": ",".join(f"{p.lat:g}" for p in batch),
            "longitude": ",".join(f"{p.lon:g}" for p in batch),
            "hourly": _HOURLY,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "start_date": start_utc.astimezone(UTC).date().isoformat(),
            "end_date": end_utc.astimezone(UTC).date().isoformat(),
        }
        try:
            response = self._client.get(f"{self._base_url}/v1/forecast", params=params)
        except httpx.HTTPError:
            raise ProviderUnavailable("Open-Meteo is unreachable") from None

        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderUnavailable(f"Open-Meteo unavailable (HTTP {response.status_code})")
        body = response.json() if response.content else {}
        if response.status_code != 200 or (isinstance(body, dict) and body.get("error")):
            reason = body.get("reason", "unknown error") if isinstance(body, dict) else "unknown"
            raise ProviderError(f"Open-Meteo rejected the request: {reason}")

        # One location is returned as an object, several as a list (in request order).
        locations = body if isinstance(body, list) else [body]
        if len(locations) != len(batch):
            raise ProviderError("Open-Meteo returned a different number of locations")
        return {point: parse_series(item) for point, item in zip(batch, locations, strict=True)}
