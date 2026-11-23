"""Golden scenario: Chicago -> Dallas end to end (plan.md section 16, Phase 3).

Frozen time, recorded real routes, recorded real weather (re-based to the frozen "now"), and no
town names (so the result does not depend on the database). The whole /routes and /risk answers
must equal tests/golden/chicago_dallas.json. The heatmap's big binary arrays are compared by
SHA-256 so the file stays readable. After an intentional change, regenerate with:

    UPDATE_GOLDEN=1 uv run pytest tests/api/test_golden.py
"""

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import time_machine
from rest_framework.test import APIClient

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "chicago_dallas.json"
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)  # noon in Chicago
REQUEST = {
    "origin": {"label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298},
    "destination": {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970},
    "departure_local": "2026-11-24T13:00",
    "load_lb": 42_000,
}


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr("api.views.lookup_town", lambda lat, lon: None)
    with time_machine.travel(NOW, tick=False):
        yield


def digest(text: str) -> dict[str, Any]:
    raw = text.encode()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "chars": len(raw)}


def run_scenario() -> dict[str, Any]:
    client = APIClient()
    routes = client.post("/api/v1/routes", REQUEST, format="json")
    assert routes.status_code == 200
    routes_body = routes.json()
    trip_id = routes_body["trip_id"]
    routes_body["trip_id"] = "t_GOLDEN"  # random per request

    risk = client.post("/api/v1/risk", {"trip_id": trip_id}, format="json")
    assert risk.status_code == 200
    risk_body = risk.json()
    heatmap = risk_body["heatmap"]
    heatmap["cells"] = digest(heatmap["cells"])
    heatmap["layers"] = {name: digest(data) for name, data in heatmap["layers"].items()}
    return {"routes": routes_body, "risk": risk_body}


def test_the_chicago_to_dallas_scenario_matches_the_golden_file() -> None:
    actual = run_scenario()
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(actual, indent=1, sort_keys=True) + "\n")
        pytest.skip("golden file regenerated")
    expected = json.loads(GOLDEN.read_text())
    assert actual == expected


def test_the_scenario_is_deterministic() -> None:
    assert run_scenario() == run_scenario()
