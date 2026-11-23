"""Quality gates and via-points for generated alternative routes (plan.md sections 3.8, 4.12).

A generated alternative is only shown if it is a real route that is clearly different from the
routes already shown (overlap under the limit) and not unreasonably slow. This module holds the
geometry and the gate decisions; calling the routing provider lives elsewhere.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from math import asin, atan2, cos, degrees, floor, radians, sin
from typing import Literal

from core.checkpoints import EARTH_RADIUS_MI, cumulative_miles, haversine_mi, point_at_mile
from core.models import Point
from core.rules import Rules

_OVERLAP_SAMPLE_MI = 0.5  # candidate is sampled this often
_OVERLAP_WITHIN_MI = 0.3  # a sample this close to an existing route counts as overlapping
_INDEX_STEP_MI = 0.1  # existing routes are resampled this finely for the proximity test
_CELL_DEG = 0.01  # grid cell for the proximity index (>= 0.3 mi everywhere in the US)
_EPSILON = 1e-9


def resample(points: Sequence[Point], step_mi: float) -> list[Point]:
    """Points every `step_mi` along the route, ending exactly at its last point."""
    cumulative = cumulative_miles(points)
    total = cumulative[-1]
    miles = [0.0]
    while miles[-1] + step_mi < total - _EPSILON:
        miles.append(miles[-1] + step_mi)
    resampled = [point_at_mile(points, cumulative, mile) for mile in miles]
    if total > 0:
        resampled.append(points[-1])
    return resampled


class _ProximityIndex:
    """Answers "is this point within X miles of the route?" without comparing against every
    vertex: the route is resampled finely and bucketed into small lat/lon cells."""

    def __init__(self, route: Sequence[Point], within_mi: float) -> None:
        self._within_mi = within_mi
        self._cells: dict[tuple[int, int], list[Point]] = {}
        for point in resample(route, _INDEX_STEP_MI):
            self._cells.setdefault(self._cell(point), []).append(point)

    @staticmethod
    def _cell(point: Point) -> tuple[int, int]:
        return floor(point[0] / _CELL_DEG), floor(point[1] / _CELL_DEG)

    def is_near(self, point: Point) -> bool:
        row, col = self._cell(point)
        return any(
            haversine_mi(point, candidate) <= self._within_mi
            for d_row in (-1, 0, 1)
            for d_col in (-1, 0, 1)
            for candidate in self._cells.get((row + d_row, col + d_col), ())
        )


def overlap_ratio(candidate: Sequence[Point], existing: Sequence[Point]) -> float:
    """Share (0..1) of the candidate's length that lies within 0.3 mi of one existing route.

    Accuracy is about 0.05 mi on the 0.3 mi threshold (existing routes are resampled every
    0.1 mi), which is far below the uncertainty of the 70% overlap limit itself.
    """
    index = _ProximityIndex(existing, _OVERLAP_WITHIN_MI)
    samples = resample(candidate, _OVERLAP_SAMPLE_MI)
    return sum(index.is_near(sample) for sample in samples) / len(samples)


def max_overlap(candidate: Sequence[Point], existing_routes: Sequence[Sequence[Point]]) -> float:
    """Highest overlap with any single route already shown (each is measured separately)."""
    return max((overlap_ratio(candidate, route) for route in existing_routes), default=0.0)


def overlap_too_high(ratio: float, rules: Rules) -> bool:
    return ratio >= rules.alternatives.max_overlap_ratio


def too_slow(total_s: float, fastest_total_s: float, rules: Rules) -> bool:
    return total_s > fastest_total_s * rules.alternatives.max_time_ratio + _EPSILON


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    reason: Literal["overlap", "too_slow"] | None
    overlap: float


def evaluate_candidate(
    candidate: Sequence[Point],
    candidate_total_s: float,
    existing_routes: Sequence[Sequence[Point]],
    fastest_total_s: float,
    rules: Rules,
) -> GateResult:
    """Decide whether a generated route may be shown next to the routes already shown."""
    overlap = max_overlap(candidate, existing_routes)
    if overlap_too_high(overlap, rules):
        return GateResult(accepted=False, reason="overlap", overlap=overlap)
    if too_slow(candidate_total_s, fastest_total_s, rules):
        return GateResult(accepted=False, reason="too_slow", overlap=overlap)
    return GateResult(accepted=True, reason=None, overlap=overlap)


def _bearing(start: Point, end: Point) -> float:
    """Initial compass bearing in radians from `start` to `end`."""
    lat1, lat2 = radians(start[0]), radians(end[0])
    d_lon = radians(end[1] - start[1])
    return atan2(sin(d_lon) * cos(lat2), cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(d_lon))


def _destination(start: Point, bearing: float, distance_mi: float) -> Point:
    """The point `distance_mi` from `start` along `bearing` (radians) on a sphere."""
    lat1, lon1 = radians(start[0]), radians(start[1])
    delta = distance_mi / EARTH_RADIUS_MI
    lat2 = asin(sin(lat1) * cos(delta) + cos(lat1) * sin(delta) * cos(bearing))
    lon2 = lon1 + atan2(sin(bearing) * sin(delta) * cos(lat1), cos(delta) - sin(lat1) * sin(lat2))
    return degrees(lat2), degrees(lon2)


def via_point(route: Sequence[Point], offset_ratio: float, side: Literal["left", "right"]) -> Point:
    """A point halfway along `route`, pushed sideways by `offset_ratio` of the route length.

    "Left" and "right" are relative to the direction of travel at the halfway point. Asking the
    routing provider for origin → via → destination yields a real route that bends that way.
    """
    cumulative = cumulative_miles(route)
    length = cumulative[-1]
    if length <= 0:
        raise ValueError("route length must be greater than zero")

    middle = length / 2
    index = min(bisect_right(cumulative, middle) - 1, len(route) - 2)
    here = point_at_mile(route, cumulative, middle)
    heading = _bearing(route[index], route[index + 1])
    quarter_turn = radians(90)
    sideways = heading - quarter_turn if side == "left" else heading + quarter_turn
    return _destination(here, sideways, offset_ratio * length)


def via_candidates(route: Sequence[Point], rules: Rules) -> list[Point]:
    """Via-points to try, left side first, then right (plan.md section 4.12)."""
    ratio = rules.alternatives.via_offset_ratio
    return [via_point(route, ratio, "left"), via_point(route, ratio, "right")]
