"""Geometry along a route: distances, checkpoint interval and exact checkpoint placement."""

from bisect import bisect_right
from collections.abc import Sequence
from math import asin, cos, radians, sin, sqrt

from core.models import CheckpointPoint, Point
from core.rules import Rules

EARTH_RADIUS_MI = 3958.8

# A final gap shorter than this is absorbed: the destination replaces the last regular checkpoint.
_MIN_LAST_GAP_MI = 1.0


def haversine_mi(a: Point, b: Point) -> float:
    """Great-circle distance in miles."""
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(h))


def cumulative_miles(points: Sequence[Point]) -> list[float]:
    """Distance from the start to each vertex (first value is 0)."""
    cumulative = [0.0]
    for previous, current in zip(points, points[1:], strict=False):
        cumulative.append(cumulative[-1] + haversine_mi(previous, current))
    return cumulative


def route_length_mi(points: Sequence[Point]) -> float:
    return cumulative_miles(points)[-1]


def choose_interval(longest_route_mi: float, rules: Rules) -> float:
    """Checkpoint spacing for all routes, chosen from the longest one (rules.yaml `intervals`)."""
    for rule in rules.intervals:
        if rule.max_mi_exclusive is not None and longest_route_mi < rule.max_mi_exclusive:
            return rule.interval_mi
        if rule.max_mi_inclusive is not None and longest_route_mi <= rule.max_mi_inclusive:
            return rule.interval_mi
        if rule.otherwise:
            return rule.interval_mi
    raise ValueError("intervals has no matching entry")  # unreachable: schema requires 'otherwise'


def point_at_mile(points: Sequence[Point], cumulative: Sequence[float], mile: float) -> Point:
    """The coordinate `mile` miles along the route, interpolated exactly on its segment."""
    if mile <= 0:
        return points[0]
    if mile >= cumulative[-1]:
        return points[-1]
    index = bisect_right(cumulative, mile) - 1
    start, end = points[index], points[index + 1]
    length = cumulative[index + 1] - cumulative[index]
    if length == 0:
        return start
    fraction = (mile - cumulative[index]) / length
    return (start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction)


def place_checkpoints(points: Sequence[Point], interval_mi: float) -> list[CheckpointPoint]:
    """Checkpoints at mile 0, every `interval_mi`, and the destination (plan.md section 4.6).

    Distances are measured along the full-resolution geometry. If the last gap would be under
    a mile, the destination replaces the last regular checkpoint.
    """
    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    cumulative = cumulative_miles(points)
    total = cumulative[-1]
    if total <= 0:
        raise ValueError("route length must be greater than zero")

    miles = [0.0]
    step = 1
    while step * interval_mi < total:
        miles.append(step * interval_mi)
        step += 1
    if len(miles) > 1 and total - miles[-1] < _MIN_LAST_GAP_MI:
        miles.pop()
    miles.append(total)

    checkpoints = []
    for idx, mile in enumerate(miles):
        lat, lon = point_at_mile(points, cumulative, mile)
        checkpoints.append(CheckpointPoint(idx=idx, mile=mile, lat=lat, lon=lon))
    return checkpoints
