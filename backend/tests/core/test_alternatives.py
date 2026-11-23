"""Quality gates and via-points for generated alternative routes (plan.md sections 3.8, 4.12)."""

from pathlib import Path

import pytest

from core.alternatives import (
    evaluate_candidate,
    max_overlap,
    overlap_ratio,
    overlap_too_high,
    resample,
    too_slow,
    via_candidates,
    via_point,
)
from core.checkpoints import haversine_mi, route_length_mi
from core.models import Point
from core.rules import load_rules

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")
DEGREE_MI = 69.093  # one degree of latitude


def north_south(lat_from: float, lat_to: float, lon: float = -100.0) -> list[Point]:
    return [(lat_from, lon), (lat_to, lon)]


MAIN = north_south(35.0, 36.0)  # ~69 mi, due north


def test_resample_places_points_every_step_and_keeps_the_end() -> None:
    points = resample(north_south(35.0, 35.0 + 10 / DEGREE_MI), 0.5)
    assert points[0] == (35.0, -100.0)
    assert len(points) == 21
    assert points[-1] == pytest.approx((35.0 + 10 / DEGREE_MI, -100.0))
    assert haversine_mi(points[0], points[1]) == pytest.approx(0.5, abs=0.01)


def test_an_identical_route_overlaps_completely() -> None:
    assert overlap_ratio(MAIN, MAIN) == pytest.approx(1.0)


def test_a_route_far_away_does_not_overlap() -> None:
    far = north_south(35.0, 36.0, lon=-98.0)  # ~110 mi east
    assert overlap_ratio(far, MAIN) == 0.0


def test_a_route_within_the_corridor_width_counts_as_overlapping() -> None:
    # 0.2 mi east of the main route (inside the 0.3 mi limit).
    close = north_south(35.0, 36.0, lon=-100.0 + 0.2 / 56.6)
    assert overlap_ratio(close, MAIN) == pytest.approx(1.0)


def test_a_route_just_outside_the_corridor_width_does_not_overlap() -> None:
    near = north_south(35.0, 36.0, lon=-100.0 + 1.0 / 56.6)  # ~1 mi east
    assert overlap_ratio(near, MAIN) == 0.0


def test_a_route_that_shares_half_its_length_overlaps_about_half() -> None:
    half = DEGREE_MI / 2
    middle = 35.0 + half / DEGREE_MI
    diverging: list[Point] = [(35.0, -100.0), (middle, -100.0), (middle, -100.0 + half / 56.6)]
    assert overlap_ratio(diverging, MAIN) == pytest.approx(0.5, abs=0.03)


def test_overlap_is_measured_against_each_existing_route_separately() -> None:
    other = north_south(35.0, 36.0, lon=-98.0)
    assert max_overlap(MAIN, [other, MAIN]) == pytest.approx(1.0)
    assert max_overlap(MAIN, [other]) == 0.0
    assert max_overlap(MAIN, []) == 0.0


@pytest.mark.parametrize(
    ("ratio", "rejected"), [(0.0, False), (0.699, False), (0.70, True), (0.9, True)]
)
def test_overlap_of_70_percent_or_more_is_rejected(ratio: float, rejected: bool) -> None:
    assert overlap_too_high(ratio, RULES) is rejected


@pytest.mark.parametrize(
    ("minutes", "rejected"),
    [(100, False), (139.99, False), (140, False), (140.01, True), (300, True)],
)
def test_more_than_1_4_times_the_fastest_time_is_rejected(minutes: float, rejected: bool) -> None:
    assert too_slow(minutes * 60, 100 * 60, RULES) is rejected


def test_a_distinct_reasonably_fast_candidate_is_accepted() -> None:
    far = north_south(35.0, 36.0, lon=-98.0)
    result = evaluate_candidate(far, 110 * 60, [MAIN], 100 * 60, RULES)
    assert result.accepted is True
    assert result.reason is None


def test_a_candidate_that_follows_an_existing_route_is_rejected_for_overlap() -> None:
    result = evaluate_candidate(MAIN, 100 * 60, [MAIN], 100 * 60, RULES)
    assert result.accepted is False
    assert result.reason == "overlap"
    assert result.overlap == pytest.approx(1.0)


def test_a_candidate_that_takes_far_too_long_is_rejected_for_time() -> None:
    far = north_south(35.0, 36.0, lon=-98.0)
    result = evaluate_candidate(far, 150 * 60, [MAIN], 100 * 60, RULES)
    assert result.accepted is False
    assert result.reason == "too_slow"


def test_via_point_sits_halfway_along_and_offset_by_12_percent_of_the_length() -> None:
    length = route_length_mi(MAIN)
    midpoint: Point = (35.5, -100.0)
    left = via_point(MAIN, RULES.alternatives.via_offset_ratio, "left")
    right = via_point(MAIN, RULES.alternatives.via_offset_ratio, "right")

    assert haversine_mi(midpoint, left) == pytest.approx(0.12 * length, abs=0.05)
    assert haversine_mi(midpoint, right) == pytest.approx(0.12 * length, abs=0.05)
    # Travelling north, left is west and right is east.
    assert left[1] < -100.0 < right[1]
    assert left[0] == pytest.approx(35.5, abs=0.05)


def test_via_candidates_try_left_before_right() -> None:
    left, right = via_candidates(MAIN, RULES)
    assert left[1] < -100.0 < right[1]


def test_via_point_follows_the_local_direction_of_a_bent_route() -> None:
    # East then north: the halfway point is on the east-going leg, where "left" means north.
    bent: list[Point] = [(35.0, -100.0), (35.0, -99.0), (35.2, -99.0)]
    left = via_point(bent, 0.12, "left")
    right = via_point(bent, 0.12, "right")
    assert left[0] > 35.0 > right[0]  # north / south of the east-going leg


def test_via_point_needs_a_route_with_length() -> None:
    with pytest.raises(ValueError, match="length"):
        via_point([(35.0, -100.0), (35.0, -100.0)], 0.12, "left")
