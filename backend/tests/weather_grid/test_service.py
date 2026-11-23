"""Weather grid cache behaviour with a fake provider (no network)."""

import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from core.models import HourlySeries
from core.rules import load_rules
from providers.base import GridPoint, ProviderUnavailable
from weather_grid.service import (
    SERIES_DAYS,
    CachedSeries,
    WeatherGridService,
    fresh_key,
    stale_key,
)

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")
NOW = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
A, B, C = GridPoint(35.2, -101.8), GridPoint(35.3, -101.8), GridPoint(35.4, -101.8)


def series(wind: float = 10.0) -> HourlySeries:
    return HourlySeries(
        start_utc=datetime(2026, 11, 24, tzinfo=UTC),
        wind_mph=(wind,) * 3,
        gust_mph=(wind,) * 3,
        rain_in_hr=(0.0,) * 3,
        snow_in_hr=(0.0,) * 3,
    )


class DictCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.timeouts: dict[str, float | None] = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def set(self, key: str, value: Any, timeout: float | None = None) -> None:
        self.store[key] = value
        self.timeouts[key] = timeout


class FakeProvider:
    def __init__(self, *, failures: int = 0, always_fail: bool = False) -> None:
        self.calls: list[tuple[list[GridPoint], datetime, datetime]] = []
        self.failures = failures
        self.always_fail = always_fail
        self._lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0

    def hourly(
        self, points: Sequence[GridPoint], start_utc: datetime, end_utc: datetime
    ) -> dict[GridPoint, HourlySeries]:
        with self._lock:
            self.calls.append((list(points), start_utc, end_utc))
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            fail = self.always_fail or self.failures > 0
            if self.failures > 0:
                self.failures -= 1
        try:
            time.sleep(0.01)
            if fail:
                raise ProviderUnavailable("down")
            return {p: series(wind=p.lat) for p in points}
        finally:
            with self._lock:
                self.in_flight -= 1


def service(provider: FakeProvider, cache: DictCache, now: datetime = NOW) -> WeatherGridService:
    return WeatherGridService(provider, cache, RULES, now=lambda: now, sleep=lambda _: None)


def test_missing_cells_are_fetched_once_and_returned() -> None:
    provider, cache = FakeProvider(), DictCache()
    result = service(provider, cache).get_series([A, B])

    assert set(result.series) == {A, B}
    assert len(provider.calls) == 1
    assert set(provider.calls[0][0]) == {A, B}
    assert result.stale is False
    assert result.missing == frozenset()
    assert result.as_of == NOW


def test_a_second_identical_request_makes_zero_provider_calls() -> None:
    provider, cache = FakeProvider(), DictCache()
    first = service(provider, cache).get_series([A, B])
    second = service(provider, cache).get_series([A, B])

    assert len(provider.calls) == 1  # still just the first request's call
    assert second.series == first.series


def test_only_the_missing_cells_are_fetched() -> None:
    provider, cache = FakeProvider(), DictCache()
    service(provider, cache).get_series([A])
    service(provider, cache).get_series([A, B, C])

    assert [set(call[0]) for call in provider.calls] == [{A}, {B, C}]


def test_duplicate_points_are_fetched_once() -> None:
    provider, cache = FakeProvider(), DictCache()
    result = service(provider, cache).get_series([A, A, B, A])
    assert len(provider.calls[0][0]) == 2
    assert set(result.series) == {A, B}


def test_no_points_means_no_calls_and_an_empty_result() -> None:
    provider, cache = FakeProvider(), DictCache()
    result = service(provider, cache).get_series([])
    assert result.series == {}
    assert provider.calls == []


def test_cache_keys_and_lifetimes_follow_the_plan() -> None:
    provider, cache = FakeProvider(), DictCache()
    service(provider, cache).get_series([A])

    assert fresh_key(A) == "wx:v1:35.2:-101.8"
    assert stale_key(A) == "wx:stale:v1:35.2:-101.8"
    assert cache.timeouts[fresh_key(A)] == 3600
    assert cache.timeouts[stale_key(A)] == 86400
    assert isinstance(cache.store[fresh_key(A)], CachedSeries)


def test_the_requested_range_is_today_utc_plus_the_next_six_days() -> None:
    provider, cache = FakeProvider(), DictCache()
    service(provider, cache).get_series([A])
    _, start, end = provider.calls[0]
    assert start == datetime(2026, 11, 24, 0, 0, tzinfo=UTC)
    assert end == start + timedelta(days=SERIES_DAYS - 1)


def test_large_requests_are_batched_and_fetched_in_parallel_up_to_four_at_a_time() -> None:
    points = [GridPoint(30 + i / 10, -100.0) for i in range(450)]
    provider, cache = FakeProvider(), DictCache()
    result = service(provider, cache).get_series(points)

    sizes = sorted(len(call[0]) for call in provider.calls)
    assert sizes == [50, 200, 200]
    assert len(result.series) == 450


def test_parallelism_is_capped_at_four() -> None:
    rules_small = RULES.model_copy(
        update={"weather_grid": RULES.weather_grid.model_copy(update={"batch_size": 5})}
    )
    points = [GridPoint(30 + i / 10, -100.0) for i in range(60)]  # 12 batches
    provider, cache = FakeProvider(), DictCache()
    WeatherGridService(provider, cache, rules_small, now=lambda: NOW).get_series(points)
    assert 1 < provider.max_in_flight <= 4


def test_a_transient_failure_is_retried_once() -> None:
    provider, cache = FakeProvider(failures=1), DictCache()
    sleeps: list[float] = []
    svc = WeatherGridService(provider, cache, RULES, now=lambda: NOW, sleep=sleeps.append)
    result = svc.get_series([A])

    assert len(provider.calls) == 2
    assert sleeps == [1.5]
    assert result.stale is False
    assert set(result.series) == {A}


def test_provider_failure_falls_back_to_the_stale_copy_and_says_so() -> None:
    cache = DictCache()
    old_time = NOW - timedelta(hours=2)
    cache.store[stale_key(A)] = CachedSeries(series=series(wind=33), fetched_at=old_time)
    result = service(FakeProvider(always_fail=True), cache).get_series([A])

    assert result.stale is True
    assert result.as_of == old_time  # "Weather as of 2 h ago"
    assert result.series[A].wind_mph[0] == 33
    assert result.missing == frozenset()


def test_when_the_fresh_cache_has_expired_the_stale_copy_still_serves_during_an_outage() -> None:
    cache = DictCache()
    first = service(FakeProvider(), cache)
    first.get_series([A])
    del cache.store[fresh_key(A)]  # the 1 h fresh entry expired; the 24 h stale one remains

    later = NOW + timedelta(hours=2)
    result = service(FakeProvider(always_fail=True), cache, now=later).get_series([A])
    assert result.stale is True
    assert result.as_of == NOW


def test_with_no_stale_copy_the_failed_cells_are_reported_missing() -> None:
    cache = DictCache()
    service(FakeProvider(), cache).get_series([A])  # A is now fresh in the cache
    result = service(FakeProvider(always_fail=True), cache).get_series([A, B])

    assert set(result.series) == {A}
    assert result.missing == frozenset({B})  # never treated as safe: shown as "No forecast"
    assert result.stale is False


def test_total_failure_without_any_cached_data_raises() -> None:
    with pytest.raises(ProviderUnavailable):
        service(FakeProvider(always_fail=True), DictCache()).get_series([A, B])


def test_fresh_data_is_not_marked_stale_just_because_other_cells_are() -> None:
    cache = DictCache()
    cache.store[stale_key(B)] = CachedSeries(series=series(wind=33), fetched_at=NOW)
    cache.store[fresh_key(A)] = CachedSeries(series=series(wind=1), fetched_at=NOW)
    result = service(FakeProvider(always_fail=True), cache).get_series([A, B])
    assert result.stale is True  # B came from the stale cache
    assert set(result.series) == {A, B}
