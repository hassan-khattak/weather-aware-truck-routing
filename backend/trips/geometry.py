"""Geometry for drawing: simplified copies of routes. Calculations always use full geometry."""

from collections.abc import Sequence

from shapely.geometry import LineString

from core.models import Point


def simplify(points: Sequence[Point], tolerance_deg: float) -> list[Point]:
    """Douglas-Peucker simplification. Always keeps the first and last point."""
    if len(points) <= 2:
        return list(points)
    line = LineString([(lon, lat) for lat, lon in points])  # shapely uses (x, y) = (lon, lat)
    simplified = line.simplify(tolerance_deg, preserve_topology=False)
    return [(lat, lon) for lon, lat in simplified.coords]
