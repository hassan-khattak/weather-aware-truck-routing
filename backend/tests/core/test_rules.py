"""Specification of the rules.yaml loader (plan.md section 9).

Written before the implementation (TDD red). The loader lives in core/rules.py.
"""

import ast
import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.rules import Rules, RulesError, load_rules, parse_rules

BACKEND_DIR = Path(__file__).resolve().parents[2]

REQUIRED_SECTIONS = [
    "version",
    "levels",
    "classification",
    "thresholds",
    "load_rules",
    "scoring",
    "intervals",
    "hours_of_service",
    "truck",
    "alternatives",
    "departure",
    "weather_grid",
    "heatmap",
]


def valid_rules() -> dict[str, Any]:
    """A minimal valid document mirroring the spec tables."""
    return {
        "version": 1,
        "levels": ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL"],
        "classification": {"wind_source": "sustained"},
        "thresholds": {
            "wind_mph": [
                {"level": "MODERATE", "from": 25, "inclusive": True},
                {"level": "HIGH", "from": 35, "inclusive": True},
                {"level": "SEVERE", "from": 45, "inclusive": True},
                {"level": "NO_TRAVEL", "from": 55, "inclusive": True},
            ],
            "rain_in_hr": [
                {"level": "MODERATE", "from": 0.10, "inclusive": True},
                {"level": "HIGH", "from": 0.25, "inclusive": True},
                {"level": "SEVERE", "from": 0.50, "inclusive": True},
                {"level": "NO_TRAVEL", "from": 1.00, "inclusive": False},
            ],
            "snow_in_hr": [
                {"level": "MODERATE", "from": 0.5, "inclusive": True},
                {"level": "HIGH", "from": 1.0, "inclusive": True},
                {"level": "SEVERE", "from": 2.0, "inclusive": True},
                {"level": "NO_TRAVEL", "from": 3.0, "inclusive": False},
            ],
        },
        "load_rules": [
            {
                "condition": "wind_mph",
                "from": 55,
                "to_exclusive": None,
                "load_gt_lb": None,
                "level": "NO_TRAVEL",
            },
            {
                "condition": "wind_mph",
                "from": 45,
                "to_exclusive": 55,
                "load_gt_lb": 30000,
                "level": "NO_TRAVEL",
            },
            {
                "condition": "wind_mph",
                "from": 35,
                "to_exclusive": 45,
                "load_gt_lb": 40000,
                "level": "SEVERE",
            },
        ],
        "scoring": {
            "level_weights": {"LOW": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3, "NO_TRAVEL": 4},
            "rounding": {"miles": 1, "avg_risk": 3},
        },
        "intervals": [
            {"max_mi_exclusive": 400, "interval_mi": 10},
            {"max_mi_inclusive": 1000, "interval_mi": 25},
            {"otherwise": True, "interval_mi": 50},
        ],
        "hours_of_service": {
            "break_after_driving_h": 8,
            "break_duration_min": 30,
            "max_driving_h": 11,
            "rest_duration_h": 10,
        },
        "truck": {
            "max_speed_kmh": 105,
            "tare_weight_lb": 35000,
            "load_min_lb": 1000,
            "load_max_lb": 80000,
            "load_warning_lb": 45000,
        },
        "alternatives": {
            "max_overlap_ratio": 0.70,
            "max_time_ratio": 1.40,
            "via_offset_ratio": 0.12,
        },
        "departure": {"max_ahead_h": 48, "past_grace_min": 5, "long_range_note_h": 72},
        "weather_grid": {
            "checkpoint_deg": 0.1,
            "heatmap_deg": 0.2,
            "corridor_mi": 30,
            "forecast_ttl_s": 3600,
            "stale_ttl_s": 86400,
            "batch_size": 200,
        },
        "heatmap": {"hours": 49},
    }


def test_valid_document_parses() -> None:
    rules = parse_rules(valid_rules())
    assert isinstance(rules, Rules)
    assert rules.version == 1
    assert rules.levels == ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL"]


def test_threshold_bands_keep_bounds_and_inclusivity() -> None:
    rules = parse_rules(valid_rules())
    rain_top = rules.thresholds.rain_in_hr[-1]
    assert (rain_top.level, rain_top.from_, rain_top.inclusive) == ("NO_TRAVEL", 1.0, False)
    wind_first = rules.thresholds.wind_mph[0]
    assert (wind_first.level, wind_first.from_, wind_first.inclusive) == ("MODERATE", 25, True)


def test_load_rules_keep_open_ended_values() -> None:
    rules = parse_rules(valid_rules())
    first = rules.load_rules[0]
    assert first.to_exclusive is None
    assert first.load_gt_lb is None
    assert rules.load_rules[1].load_gt_lb == 30000


def test_intervals_accept_the_three_entry_shapes() -> None:
    rules = parse_rules(valid_rules())
    exclusive, inclusive, otherwise = rules.intervals
    assert (exclusive.max_mi_exclusive, exclusive.interval_mi) == (400, 10)
    assert (inclusive.max_mi_inclusive, inclusive.interval_mi) == (1000, 25)
    assert (otherwise.otherwise, otherwise.interval_mi) == (True, 50)


def test_interval_entry_without_a_bound_is_rejected() -> None:
    doc = valid_rules()
    doc["intervals"][0] = {"interval_mi": 10}
    with pytest.raises(RulesError, match="intervals"):
        parse_rules(doc)


def test_intervals_must_end_with_an_otherwise_entry() -> None:
    doc = valid_rules()
    doc["intervals"] = doc["intervals"][:2]
    with pytest.raises(RulesError, match="intervals"):
        parse_rules(doc)


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_missing_section_is_rejected_and_named(section: str) -> None:
    doc = valid_rules()
    del doc[section]
    with pytest.raises(RulesError, match=section):
        parse_rules(doc)


def test_unknown_level_name_is_rejected() -> None:
    doc = valid_rules()
    doc["thresholds"]["wind_mph"][0]["level"] = "EXTREME"
    with pytest.raises(RulesError, match="EXTREME"):
        parse_rules(doc)


def test_no_forecast_is_not_a_threshold_level() -> None:
    doc = valid_rules()
    doc["thresholds"]["wind_mph"][0]["level"] = "NO_FORECAST"
    with pytest.raises(RulesError, match="NO_FORECAST"):
        parse_rules(doc)


def test_wrong_type_error_names_the_field() -> None:
    doc = valid_rules()
    doc["weather_grid"]["batch_size"] = "lots"
    with pytest.raises(RulesError, match=r"weather_grid\.batch_size"):
        parse_rules(doc)


def test_unknown_key_is_rejected_to_catch_typos() -> None:
    doc = valid_rules()
    doc["truck"]["tare_wieght_lb"] = 1
    with pytest.raises(RulesError, match="tare_wieght_lb"):
        parse_rules(doc)


def test_level_weights_must_cover_exactly_the_levels() -> None:
    doc = valid_rules()
    del doc["scoring"]["level_weights"]["NO_TRAVEL"]
    with pytest.raises(RulesError, match="level_weights"):
        parse_rules(doc)


def test_parsing_does_not_mutate_the_input() -> None:
    doc = valid_rules()
    before = copy.deepcopy(doc)
    parse_rules(doc)
    assert doc == before


def test_load_rules_reads_a_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(valid_rules()))
    assert load_rules(path).version == 1


def test_missing_file_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(RulesError, match="not found"):
        load_rules(tmp_path / "nope.yaml")


def test_malformed_yaml_is_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("a: [unclosed")
    with pytest.raises(RulesError, match="YAML"):
        load_rules(path)


def test_top_level_must_be_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("- just\n- a list\n")
    with pytest.raises(RulesError, match="mapping"):
        load_rules(path)


def test_shipped_rules_yaml_is_valid_and_matches_the_spec() -> None:
    rules = load_rules(BACKEND_DIR / "rules.yaml")
    assert rules.thresholds.wind_mph[-1].from_ == 55
    assert rules.hours_of_service.max_driving_h == 11
    assert rules.heatmap.hours == 49


def test_rules_module_does_not_import_django_or_io_libraries() -> None:
    source = (BACKEND_DIR / "core" / "rules.py").read_text()
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"django", "httpx", "requests", "rest_framework"}
