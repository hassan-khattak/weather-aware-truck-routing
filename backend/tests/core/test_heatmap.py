"""Heatmap corridor cells and packed typed arrays (plan.md sections 4.13, 7.4)."""

import base64
import math
import struct
from pathlib import Path

import pytest

from core.alternatives import resample
from core.checkpoints import EARTH_RADIUS_MI, haversine_mi
from core.heatmap import corridor_cells, pack_heatmap, snap, snap_point
from core.models import Point, Weather
from core.rules import load_rules

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")
DEGREE_MI = 2 * math.pi * EARTH_RADIUS_MI / 360

MAIN: list[Point] = [(35.0, -100.0), (36.0, -100.0)]


def test_snap_rounds_to_the_nearest_grid_point() -> None:
    assert snap(35.04, 0.1) == 35.0
    assert snap(35.06, 0.1) == 35.1
    assert snap(-100.26, 0.2) == -100.2
    assert snap_point(35.04, -100.26, 0.1) == (35.0, -100.3)


def test_snapping_is_stable_and_free_of_float_noise() -> None:
    assert snap(0.30000000000000004, 0.1) == 0.3
    assert snap(snap(35.123, 0.1), 0.1) == snap(35.123, 0.1)


def test_corridor_cells_are_0_2_degrees_with_centres_on_the_0_1_grid() -> None:
    cells = corridor_cells([MAIN], RULES)
    assert cells
    for lat, lon in cells:
        assert lat * 5 == pytest.approx(round(lat * 5), abs=1e-6)  # multiple of 0.2
        assert lon * 5 == pytest.approx(round(lon * 5), abs=1e-6)
        assert lat * 10 == pytest.approx(round(lat * 10), abs=1e-6)  # so also on the 0.1 grid


def test_corridor_includes_cells_within_30_miles_and_excludes_those_beyond() -> None:
    cells = set(corridor_cells([MAIN], RULES))
    assert (35.4, -100.0) in cells
    assert (35.4, -100.4) in cells  # ~22 mi east/west
    assert (35.4, -100.6) not in cells  # ~34 mi
    assert (34.6, -100.0) in cells  # ~27.6 mi south of the origin
    assert (34.4, -100.0) not in cells  # ~41 mi
    assert (34.6, -100.4) not in cells  # corner: ~36 mi from the origin


def test_corridor_matches_a_brute_force_distance_test() -> None:
    cells = set(corridor_cells([MAIN], RULES))
    route = resample(MAIN, 0.1)
    for lat_step in range(170, 190):
        for lon_step in range(-510, -490):
            centre = (round(lat_step * 0.2, 6), round(lon_step * 0.2, 6))
            nearest = min(haversine_mi(centre, p) for p in route)
            if nearest < 29.8:
                assert centre in cells, centre
            elif nearest > 30.2:
                assert centre not in cells, centre


def test_corridor_covers_all_routes_together() -> None:
    east: list[Point] = [(35.0, -97.0), (36.0, -97.0)]
    cells = set(corridor_cells([MAIN, east], RULES))
    assert (35.4, -100.0) in cells
    assert (35.4, -97.0) in cells
    assert (35.4, -98.6) not in cells  # far from both


def test_corridor_of_no_routes_is_empty() -> None:
    assert corridor_cells([], RULES) == []


def test_corridor_cells_are_unique_and_sorted() -> None:
    cells = corridor_cells([MAIN, MAIN], RULES)
    assert cells == sorted(set(cells))


# --- packing ---

CELLS: list[Point] = [(35.0, -100.0), (35.2, -100.0)]


def decode(text: str, fmt: str, count: int) -> tuple[float, ...]:
    return struct.unpack(f"<{count}{fmt}", base64.b64decode(text))


def w(wind: float = 0.0, rain: float = 0.0, snow: float = 0.0) -> Weather:
    return Weather(wind_mph=wind, gust_mph=wind, rain_in_hr=rain, snow_in_hr=snow)


def test_cells_are_packed_as_little_endian_float32_lat_lon_pairs() -> None:
    packed = pack_heatmap(CELLS, [[w(), w()]], 0, RULES)
    values = decode(packed.cells, "f", 4)
    assert values == pytest.approx((35.0, -100.0, 35.2, -100.0))
    assert packed.grid_deg == 0.2


def test_layers_are_hour_major_one_hour_is_a_contiguous_slice() -> None:
    hours = [
        [w(wind=10), w(wind=20)],  # hour 0: cells 0, 1
        [w(wind=30), w(wind=40)],  # hour 1
        [w(wind=50), w(wind=60)],  # hour 2
    ]
    packed = pack_heatmap(CELLS, hours, 0, RULES)
    assert packed.hours == 3
    assert decode(packed.layers["wind"], "B", 6) == (10, 20, 30, 40, 50, 60)


def test_risk_layer_holds_level_ordinals_with_load_rules_applied() -> None:
    hours = [[w(wind=40), w(wind=10)]]
    heavy = pack_heatmap(CELLS, hours, 42_000, RULES)
    light = pack_heatmap(CELLS, hours, 10_000, RULES)
    assert decode(heavy.layers["risk"], "B", 2) == (3, 0)  # Severe, Low
    assert decode(light.layers["risk"], "B", 2) == (2, 0)  # High, Low


def test_missing_weather_uses_the_no_data_sentinels() -> None:
    packed = pack_heatmap(CELLS, [[None, w(wind=10, rain=0.1, snow=0.5)]], 0, RULES)
    assert decode(packed.layers["risk"], "B", 2) == (255, 1)  # rain 0.1 / snow 0.5 = Moderate
    assert decode(packed.layers["wind"], "B", 2) == (255, 10)
    assert decode(packed.layers["rain"], "H", 2) == (65535, 10)
    assert decode(packed.layers["snow"], "H", 2) == (65535, 50)


def test_units_are_whole_mph_and_hundredths_of_an_inch_per_hour() -> None:
    packed = pack_heatmap(CELLS, [[w(wind=38.4, rain=0.256, snow=1.0), w()]], 0, RULES)
    assert decode(packed.layers["wind"], "B", 2)[0] == 38
    assert decode(packed.layers["rain"], "H", 2)[0] == 26
    assert decode(packed.layers["snow"], "H", 2)[0] == 100


def test_values_are_clipped_below_the_sentinels() -> None:
    packed = pack_heatmap(CELLS, [[w(wind=300, rain=700, snow=900), w()]], 0, RULES)
    assert decode(packed.layers["wind"], "B", 2)[0] == 254
    assert decode(packed.layers["rain"], "H", 2)[0] == 65534
    assert decode(packed.layers["snow"], "H", 2)[0] == 65534


def test_payload_sizes_match_cells_times_hours() -> None:
    hours = [[w(), w()] for _ in range(49)]
    packed = pack_heatmap(CELLS, hours, 0, RULES)
    assert packed.hours == 49
    assert len(base64.b64decode(packed.layers["risk"])) == 49 * 2
    assert len(base64.b64decode(packed.layers["rain"])) == 49 * 2 * 2


def test_every_hour_must_have_one_value_per_cell() -> None:
    with pytest.raises(ValueError, match="cell"):
        pack_heatmap(CELLS, [[w()]], 0, RULES)


def test_at_least_one_hour_is_required() -> None:
    with pytest.raises(ValueError, match="hour"):
        pack_heatmap(CELLS, [], 0, RULES)
