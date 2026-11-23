"""Interval choice and exact checkpoint placement (plan.md sections 3.1, 4.6)."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.checkpoints import (
    EARTH_RADIUS_MI,
    choose_interval,
    cumulative_miles,
    haversine_mi,
    place_checkpoints,
    point_at_mile,
    route_length_mi,
)
from core.models import Point
from core.rules import load_rules

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")

DEGREE_MI = 2 * 3.141592653589793 * EARTH_RADIUS_MI / 360  # one degree of arc, ~69.09 mi


def test_earth_radius_matches_the_plan() -> None:
    assert EARTH_RADIUS_MI == 3958.8


def test_haversine_one_degree_of_latitude() -> None:
    assert haversine_mi((35.0, -100.0), (36.0, -100.0)) == pytest.approx(DEGREE_MI, abs=0.01)


def test_haversine_dallas_to_denver_is_about_660_miles() -> None:
    assert 655 < haversine_mi((32.7767, -96.7970), (39.7392, -104.9903)) < 670


def test_haversine_of_the_same_point_is_zero() -> None:
    assert haversine_mi((35.0, -100.0), (35.0, -100.0)) == 0


@pytest.mark.parametrize(
    ("longest_mi", "interval"),
    [
        (0, 10),
        (399, 10),
        (399.99, 10),
        (400, 25),
        (1000, 25),
        (1000.01, 50),
        (1001, 50),
        (2050, 50),
    ],
)
def test_interval_choice_boundaries(longest_mi: float, interval: float) -> None:
    assert choose_interval(longest_mi, RULES) == interval


def test_route_length_sums_segments() -> None:
    points: list[Point] = [(35.0, -100.0), (36.0, -100.0), (37.0, -100.0)]
    assert route_length_mi(points) == pytest.approx(2 * DEGREE_MI, abs=0.02)
    assert cumulative_miles(points)[0] == 0
    assert cumulative_miles(points)[1] == pytest.approx(DEGREE_MI, abs=0.01)


def test_checkpoints_start_at_mile_zero_every_interval_and_end_at_the_destination() -> None:
    route: list[Point] = [(35.0, -100.0), (36.0, -100.0)]  # ~69.09 mi
    checkpoints = place_checkpoints(route, 25)
    assert [round(c.mile, 2) for c in checkpoints] == [0, 25, 50, round(DEGREE_MI, 2)]
    assert [c.idx for c in checkpoints] == [0, 1, 2, 3]
    assert (checkpoints[0].lat, checkpoints[0].lon) == (35.0, -100.0)
    assert (checkpoints[-1].lat, checkpoints[-1].lon) == (36.0, -100.0)


def test_checkpoints_are_interpolated_exactly_not_snapped_to_vertices() -> None:
    route: list[Point] = [(35.0, -100.0), (36.0, -100.0)]
    checkpoint = place_checkpoints(route, 25)[1]
    assert checkpoint.lat == pytest.approx(35.0 + 25 / DEGREE_MI, abs=1e-6)
    assert checkpoint.lon == pytest.approx(-100.0, abs=1e-9)
    assert haversine_mi(route[0], (checkpoint.lat, checkpoint.lon)) == pytest.approx(25, abs=0.01)


def test_checkpoint_on_a_later_segment_uses_distance_along_the_whole_route() -> None:
    # Two legs of ~69 mi; mile 100 is ~31 mi into the second leg.
    route: list[Point] = [(35.0, -100.0), (36.0, -100.0), (36.0, -98.8)]
    cumulative = cumulative_miles(route)
    lat, lon = point_at_mile(route, cumulative, 100)
    assert lat == pytest.approx(36.0, abs=1e-6)
    assert lon > -100.0
    assert haversine_mi(route[1], (lat, lon)) == pytest.approx(100 - DEGREE_MI, abs=0.05)


def test_a_last_gap_under_one_mile_is_absorbed_by_the_destination() -> None:
    route: list[Point] = [(35.0, -100.0), (35.0 + 50.5 / DEGREE_MI, -100.0)]  # ~50.5 mi
    miles = [round(c.mile, 2) for c in place_checkpoints(route, 25)]
    assert miles == [0, 25, 50.5]


def test_a_last_gap_of_one_and_a_half_miles_keeps_the_regular_checkpoint() -> None:
    route: list[Point] = [(35.0, -100.0), (35.0 + 51.5 / DEGREE_MI, -100.0)]
    miles = [round(c.mile, 2) for c in place_checkpoints(route, 25)]
    assert miles == [0, 25, 50, 51.5]


def test_a_route_shorter_than_the_interval_has_only_origin_and_destination() -> None:
    route: list[Point] = [(35.0, -100.0), (35.0 + 8 / DEGREE_MI, -100.0)]
    assert [round(c.mile, 2) for c in place_checkpoints(route, 25)] == [0, 8]


def test_a_route_shorter_than_one_mile_keeps_origin_and_destination() -> None:
    route: list[Point] = [(35.0, -100.0), (35.0 + 0.4 / DEGREE_MI, -100.0)]
    assert [round(c.mile, 2) for c in place_checkpoints(route, 25)] == [0, 0.4]


def test_a_zero_length_route_is_rejected() -> None:
    with pytest.raises(ValueError, match="length"):
        place_checkpoints([(35.0, -100.0), (35.0, -100.0)], 25)


def test_a_route_needs_at_least_two_points() -> None:
    with pytest.raises(ValueError, match="two points"):
        place_checkpoints([(35.0, -100.0)], 25)


@given(
    steps=st.lists(
        st.tuples(st.floats(-0.3, 0.3), st.floats(0.01, 0.3)),
        min_size=1,
        max_size=40,
    ),
    interval=st.sampled_from([10, 25, 50]),
)
def test_property_checkpoints_are_ordered_and_span_the_route(
    steps: list[tuple[float, float]], interval: int
) -> None:
    route: list[Point] = [(35.0, -100.0)]
    for dlat, dlon in steps:
        lat, lon = route[-1]
        route.append((lat + dlat, lon + dlon))
    total = route_length_mi(route)
    checkpoints = place_checkpoints(route, interval)

    assert checkpoints[0].mile == 0
    assert checkpoints[-1].mile == pytest.approx(total, abs=1e-6)
    assert all(a.mile < b.mile for a, b in zip(checkpoints, checkpoints[1:], strict=False))
    assert [c.idx for c in checkpoints] == list(range(len(checkpoints)))
