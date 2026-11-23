"""Heatmap grid: which cells to show around the routes, and compact packing for the browser.

Plan.md sections 4.13 and 7.4. Heatmap cells are 0.2 degrees with centres on multiples of 0.2,
which are also points of the 0.1 degree checkpoint grid, so the heatmap and the checkpoints share
one weather cache. The packed layers are hour-major (`index = hour * cells + cell`) so one hour
is a contiguous slice.
"""

import base64
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, cos, floor, hypot, radians

from core.checkpoints import EARTH_RADIUS_MI
from core.models import Point, Weather
from core.risk import classify
from core.rules import Rules

_DEGREE_MI = 2 * 3.141592653589793 * EARTH_RADIUS_MI / 360
_EPSILON = 1e-9

NO_DATA_U8 = 255
NO_DATA_U16 = 65535
_MAX_U8 = 254  # 255 is reserved for "no data"
_MAX_U16 = 65534  # 65535 is reserved for "no data"


def snap(value: float, grid_deg: float) -> float:
    """Nearest grid point; rounded to 6 decimals so 0.30000000000000004 cannot leak out."""
    return round(round(value / grid_deg) * grid_deg, 6)


def snap_point(lat: float, lon: float, grid_deg: float) -> Point:
    return snap(lat, grid_deg), snap(lon, grid_deg)


def _distance_to_segment_mi(centre: Point, a: Point, b: Point) -> float:
    """Miles from `centre` to the segment a-b, in a flat projection around `centre`
    (accurate to a fraction of a percent at corridor distances)."""
    scale = cos(radians(centre[0]))

    def project(p: Point) -> tuple[float, float]:
        return (p[1] - centre[1]) * scale * _DEGREE_MI, (p[0] - centre[0]) * _DEGREE_MI

    ax, ay = project(a)
    bx, by = project(b)
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return hypot(ax + t * dx, ay + t * dy)


def corridor_cells(routes: Sequence[Sequence[Point]], rules: Rules) -> list[Point]:
    """Centres of the heatmap cells within `corridor_mi` of any route, sorted and unique.

    Simplified route geometry is fine here: the corridor is 30 miles wide.
    """
    step = rules.weather_grid.heatmap_deg
    reach_mi = rules.weather_grid.corridor_mi
    found: set[Point] = set()

    for route in routes:
        segments = list(zip(route, route[1:], strict=False)) or [(p, p) for p in route]
        for a, b in segments:
            lat_lo, lat_hi = min(a[0], b[0]), max(a[0], b[0])
            lon_lo, lon_hi = min(a[1], b[1]), max(a[1], b[1])
            widest_lat = max(abs(lat_lo), abs(lat_hi))
            d_lat = reach_mi / _DEGREE_MI
            d_lon = reach_mi / (_DEGREE_MI * max(cos(radians(widest_lat)), 0.05))
            for lat_k in range(
                ceil((lat_lo - d_lat) / step - _EPSILON),
                floor((lat_hi + d_lat) / step + _EPSILON) + 1,
            ):
                for lon_k in range(
                    ceil((lon_lo - d_lon) / step - _EPSILON),
                    floor((lon_hi + d_lon) / step + _EPSILON) + 1,
                ):
                    centre = (round(lat_k * step, 6), round(lon_k * step, 6))
                    if centre not in found and _distance_to_segment_mi(centre, a, b) <= reach_mi:
                        found.add(centre)
    return sorted(found)


@dataclass(frozen=True)
class PackedHeatmap:
    """Base64 typed arrays (little-endian) the browser decodes once.

    `cells`: float32 [lat, lon, ...]. Layers are hour-major over cells:
    `risk` uint8 level ordinal (255 = no data), `wind` uint8 whole mph (255 = no data),
    `rain` / `snow` uint16 hundredths of an inch per hour (65535 = no data).
    """

    grid_deg: float
    hours: int
    cells: str
    layers: dict[str, str]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _u8(values: Sequence[int]) -> str:
    return _b64(bytes(values))


def _u16(values: Sequence[int]) -> str:
    return _b64(struct.pack(f"<{len(values)}H", *values))


def pack_heatmap(
    cells: Sequence[Point],
    weather_by_hour: Sequence[Sequence[Weather | None]],
    load_lb: float,
    rules: Rules,
) -> PackedHeatmap:
    """Pack weather for every cell and hour. `None` means no forecast for that cell and hour.

    The risk layer uses the same classification and load rules as the checkpoints.
    """
    if not weather_by_hour:
        raise ValueError("need at least one hour of weather")
    if any(len(hour) != len(cells) for hour in weather_by_hour):
        raise ValueError("every hour needs exactly one weather value per cell")

    risk: list[int] = []
    wind: list[int] = []
    rain: list[int] = []
    snow: list[int] = []
    for hour in weather_by_hour:
        for weather in hour:
            if weather is None:
                risk.append(NO_DATA_U8)
                wind.append(NO_DATA_U8)
                rain.append(NO_DATA_U16)
                snow.append(NO_DATA_U16)
                continue
            risk.append(int(classify(weather, load_lb, rules).level))
            wind.append(min(_MAX_U8, round(weather.wind_mph)))
            rain.append(min(_MAX_U16, round(weather.rain_in_hr * 100)))
            snow.append(min(_MAX_U16, round(weather.snow_in_hr * 100)))

    flat_cells = [float(v) for cell in cells for v in cell]
    return PackedHeatmap(
        grid_deg=rules.weather_grid.heatmap_deg,
        hours=len(weather_by_hour),
        cells=_b64(struct.pack(f"<{len(flat_cells)}f", *flat_cells)),
        layers={"risk": _u8(risk), "wind": _u8(wind), "rain": _u16(rain), "snow": _u16(snow)},
    )
