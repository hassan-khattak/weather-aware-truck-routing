import math

import pytest
from shapely.geometry import LineString, Point

from core.models import Point as LatLon
from trips.geometry import simplify


def test_a_straight_line_collapses_to_its_end_points() -> None:
    line: list[LatLon] = [(35.0 + i * 0.01, -100.0) for i in range(500)]
    assert simplify(line, 0.002) == [line[0], line[-1]]


def test_end_points_are_always_kept() -> None:
    line: list[LatLon] = [(35.0, -100.0), (35.5, -100.3), (36.0, -100.0)]
    result = simplify(line, 0.002)
    assert result[0] == line[0]
    assert result[-1] == line[-1]


def test_a_real_bend_is_preserved() -> None:
    corner: list[LatLon] = [(35.0, -100.0), (35.0, -99.0), (36.0, -99.0)]
    assert simplify(corner, 0.002) == corner


def test_no_dropped_point_is_further_than_the_tolerance_from_the_result() -> None:
    wiggle: list[LatLon] = [(35.0 + i * 0.01, -100.0 + 0.001 * math.sin(i)) for i in range(300)]
    tolerance = 0.002
    result = simplify(wiggle, tolerance)
    assert len(result) < len(wiggle)
    drawn = LineString([(lon, lat) for lat, lon in result])
    assert max(drawn.distance(Point(lon, lat)) for lat, lon in wiggle) <= tolerance + 1e-9


@pytest.mark.parametrize("points", [[], [(35.0, -100.0)], [(35.0, -100.0), (36.0, -100.0)]])
def test_tiny_inputs_are_returned_unchanged(points: list[LatLon]) -> None:
    assert simplify(points, 0.002) == points
