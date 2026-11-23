"""Shared weather cache keyed by grid cell (plan.md sections 5.4, 6).

Every checkpoint and heatmap cell is a grid point; each point's full hourly series is cached once
and shared by all routes, hours and users. A search fetches only the cells that are missing,
in parallel batches. If the provider fails, the last good copy (the "stale" cache) is served
and flagged, so the app degrades to "weather as of 2 h ago" instead of an error.
"""

import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from core.models import HourlySeries
from core.rules import Rules
from providers.base import GridPoint, ProviderUnavailable, WeatherProvider
from providers.tomtom import Cache

# How much of the forecast each cached series covers: today (UTC) and the next six days, which is
# 48 h of heatmap plus the longest multi-day trip we can usefully forecast.
SERIES_DAYS = 7
_MAX_WORKERS = 4
_RETRY_DELAY_S = 1.5


@dataclass(frozen=True)
class CachedSeries:
    series: HourlySeries
    fetched_at: datetime


@dataclass(frozen=True)
class GridResult:
    series: dict[GridPoint, HourlySeries]
    # True when any series came from the stale cache because the provider failed.
    stale: bool
    # When the oldest data used was fetched ("weather as of ...").
    as_of: datetime | None
    # Points with no data at all (no fresh fetch and no stale copy): shown as "No forecast".
    missing: frozenset[GridPoint] = field(default_factory=frozenset)


def fresh_key(point: GridPoint) -> str:
    return f"wx:v1:{point.lat:.1f}:{point.lon:.1f}"


def stale_key(point: GridPoint) -> str:
    return f"wx:stale:v1:{point.lat:.1f}:{point.lon:.1f}"


class WeatherGridService:
    def __init__(
        self,
        provider: WeatherProvider,
        cache: Cache,
        rules: Rules,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        retry_delay_s: float = _RETRY_DELAY_S,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._grid = rules.weather_grid
        self._now = now
        self._sleep = sleep
        self._retry_delay_s = retry_delay_s

    def get_series(self, points: Sequence[GridPoint]) -> GridResult:
        """Hourly series for every point, from cache where possible.

        Raises ProviderUnavailable only if nothing at all could be obtained.
        """
        unique = list(dict.fromkeys(points))
        series: dict[GridPoint, HourlySeries] = {}
        as_of: list[datetime] = []

        missing: list[GridPoint] = []
        for point in unique:
            cached = self._cache.get(fresh_key(point))
            if cached is None:
                missing.append(point)
            else:
                series[point] = cached.series
                as_of.append(cached.fetched_at)

        stale_used = False
        unobtained: set[GridPoint] = set()
        if missing:
            fetched, failed = self._fetch_missing(missing)
            fetched_at = self._now()
            for point, data in fetched.items():
                entry = CachedSeries(series=data, fetched_at=fetched_at)
                self._cache.set(fresh_key(point), entry, self._grid.forecast_ttl_s)
                self._cache.set(stale_key(point), entry, self._grid.stale_ttl_s)
                series[point] = data
                as_of.append(fetched_at)

            for point in failed:
                old = self._cache.get(stale_key(point))
                if old is None:
                    unobtained.add(point)
                else:
                    series[point] = old.series
                    as_of.append(old.fetched_at)
                    stale_used = True
            # A provider that answered but had no data for a point leaves it unobtained too.
            unobtained.update(p for p in missing if p not in series)

        if unique and not series:
            raise ProviderUnavailable("weather data is unavailable and nothing is cached")
        return GridResult(
            series=series,
            stale=stale_used,
            as_of=min(as_of) if as_of else None,
            missing=frozenset(unobtained),
        )

    def _fetch_missing(
        self, points: list[GridPoint]
    ) -> tuple[dict[GridPoint, HourlySeries], list[GridPoint]]:
        """Fetch in batches, a few at a time. Returns (data, points whose batch failed)."""
        size = self._grid.batch_size
        batches = [points[i : i + size] for i in range(0, len(points), size)]
        today = self._now().astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = today, today + timedelta(days=SERIES_DAYS - 1)

        def fetch(batch: list[GridPoint]) -> dict[GridPoint, HourlySeries] | None:
            for attempt in range(2):
                try:
                    return self._provider.hourly(batch, start, end)
                except ProviderUnavailable:
                    if attempt == 0:
                        self._sleep(self._retry_delay_s)
            return None

        data: dict[GridPoint, HourlySeries] = {}
        failed: list[GridPoint] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            for batch, result in zip(batches, pool.map(fetch, batches), strict=True):
                if result is None:
                    failed.extend(batch)
                else:
                    data.update(result)
        return data, failed
