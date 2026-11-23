"""ETAs along a route: timing anchors, hours of service and the elapsed-time timeline.

Plan.md sections 3.3 and 4.7. Everything is UTC; the truck is parked during stops, so stops
add elapsed time but no miles.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from core.models import Stop
from core.rules import HoursOfService, Rules

_HOUR_S = 3600.0
# Two driving times closer than this are "the same moment" (float noise from interpolation).
_EPSILON_S = 1e-6

# (type, driving seconds at which it starts, duration seconds)
_RawStop = tuple[Literal["break", "rest"], float, float]


@dataclass(frozen=True)
class EtaPlan:
    """When the truck is where, for one route and departure."""

    departure_utc: datetime
    route_mi: float
    drive_s: float
    total_s: float
    stops: tuple[Stop, ...]
    # (elapsed seconds since departure, mile) pairs; flat in `mile` while the truck is parked.
    timeline: tuple[tuple[float, float], ...]
    anchor_miles: tuple[float, ...] = field(repr=False)
    anchor_seconds: tuple[float, ...] = field(repr=False)
    stop_drive_s: tuple[float, ...] = field(repr=False)
    stop_durations_s: tuple[float, ...] = field(repr=False)

    def drive_s_at_mile(self, mile: float) -> float:
        """Driving time (no stops) to reach `mile`, interpolated between the anchors."""
        mile = min(max(mile, 0.0), self.route_mi)
        return _interpolate(self.anchor_miles, self.anchor_seconds, mile)

    def elapsed_s_at_drive(self, drive_s: float) -> float:
        """Elapsed time when `drive_s` of driving is done. A stop exactly at that point has not
        happened yet: the truck has only just arrived."""
        stops_before = sum(
            duration
            for at, duration in zip(self.stop_drive_s, self.stop_durations_s, strict=True)
            if at < drive_s - _EPSILON_S
        )
        return drive_s + stops_before

    def eta_at_mile(self, mile: float) -> datetime:
        """Arrival time at `mile` (the arrival time, even if a stop happens right there)."""
        elapsed = self.elapsed_s_at_drive(self.drive_s_at_mile(mile))
        return self.departure_utc + timedelta(seconds=elapsed)


def _interpolate(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    """Piecewise-linear y(x) for non-decreasing xs, clamped to the ends."""
    index = min(max(bisect_right(xs, x) - 1, 0), len(xs) - 2)
    x0, x1 = xs[index], xs[index + 1]
    y0, y1 = ys[index], ys[index + 1]
    if x1 == x0:
        return y0
    fraction = min(max((x - x0) / (x1 - x0), 0.0), 1.0)
    return y0 + (y1 - y0) * fraction


def _normalise_anchors(
    anchors: Sequence[tuple[float, float]], route_mi: float
) -> tuple[list[float], list[float]]:
    """Validate anchors, add the (0, 0) origin if missing, and rescale distances so the last
    anchor sits at the measured route length (the routing engine and our haversine length differ
    slightly)."""
    pairs = list(anchors)
    if pairs and pairs[0][0] > 0:
        pairs.insert(0, (0.0, 0.0))
    if len(pairs) < 2:
        raise ValueError("need at least two timing anchors")
    for (d0, t0), (d1, t1) in zip(pairs, pairs[1:], strict=False):
        if d1 < d0 or t1 < t0:
            raise ValueError("timing anchors must not go backwards in distance or time")
    if pairs[0] != (0, 0) or pairs[-1][0] <= 0:
        raise ValueError("timing anchors must start at (0, 0) and end past mile 0")
    scale = route_mi / pairs[-1][0]
    return [d * scale for d, _ in pairs], [t for _, t in pairs]


def _hos_stops(
    total_drive_s: float, hos: HoursOfService
) -> list[tuple[Literal["break", "rest"], float, float]]:
    """Required stops as (type, driving seconds when it starts, duration seconds).

    A break is due after `break_after_driving_h` of driving since the last break or rest; a
    rest is due after `max_driving_h` since the last rest and resets both counters. Arriving
    exactly at a limit does not need a stop.
    """
    if hos.break_after_driving_h <= 0 or hos.max_driving_h <= 0:
        raise ValueError("hours of service limits must be positive")
    break_after = hos.break_after_driving_h * _HOUR_S
    max_drive = hos.max_driving_h * _HOUR_S
    break_s = hos.break_duration_min * 60.0
    rest_s = hos.rest_duration_h * _HOUR_S

    stops: list[_RawStop] = []
    last_break = last_rest = 0.0
    while True:
        next_break, next_rest = last_break + break_after, last_rest + max_drive
        kind: Literal["break", "rest"] = "rest" if next_rest <= next_break else "break"
        at = next_rest if kind == "rest" else next_break
        if at >= total_drive_s - _EPSILON_S:
            return stops
        stops.append((kind, at, rest_s if kind == "rest" else break_s))
        last_break = at
        if kind == "rest":
            last_rest = at


def build_eta_plan(
    anchors: Sequence[tuple[float, float]],
    route_mi: float,
    departure_utc: datetime,
    rules: Rules,
) -> EtaPlan:
    """Combine timing anchors (miles, seconds) with hours-of-service stops.

    `route_mi` is the route length measured along the geometry; anchors are rescaled to it.
    """
    if departure_utc.tzinfo is None:
        raise ValueError("departure must be timezone-aware")
    if route_mi <= 0:
        raise ValueError("route length must be greater than zero")
    departure = departure_utc.astimezone(UTC)

    miles, seconds = _normalise_anchors(anchors, route_mi)
    drive_s = seconds[-1]
    raw_stops = _hos_stops(drive_s, rules.hours_of_service)
    stop_at = tuple(at for _, at, _ in raw_stops)
    stop_len = tuple(duration for *_, duration in raw_stops)

    def elapsed(drive: float) -> float:
        return drive + sum(
            d for at, d in zip(stop_at, stop_len, strict=True) if at < drive - _EPSILON_S
        )

    stops = tuple(
        Stop(
            type=kind,
            mile=_interpolate(seconds, miles, at),
            start_utc=departure + timedelta(seconds=elapsed(at)),
            duration_s=duration,
        )
        for kind, at, duration in raw_stops
    )

    # Timeline key points are driving times: every anchor, plus every stop (joined to an anchor
    # when they coincide so the elapsed time can never step backwards).
    mile_at: dict[float, float] = {}
    for mile, second in zip(miles, seconds, strict=True):
        mile_at.setdefault(second, mile)
    stop_key: dict[float, float] = {}
    for _kind, at, duration in raw_stops:
        key = next((k for k in mile_at if abs(k - at) <= _EPSILON_S), at)
        mile_at.setdefault(key, _interpolate(seconds, miles, at))
        stop_key[key] = duration

    timeline: list[tuple[float, float]] = []
    for key in sorted(mile_at):
        arrive = elapsed(key)
        timeline.append((arrive, mile_at[key]))
        if key in stop_key:
            timeline.append((arrive + stop_key[key], mile_at[key]))

    return EtaPlan(
        departure_utc=departure,
        route_mi=route_mi,
        drive_s=drive_s,
        total_s=elapsed(drive_s),
        stops=stops,
        timeline=tuple(timeline),
        anchor_miles=tuple(miles),
        anchor_seconds=tuple(seconds),
        stop_drive_s=stop_at,
        stop_durations_s=stop_len,
    )
