"""POST /api/v1/risk (plan.md section 7.4): the second step of a search, in fixture mode."""

import base64
import gzip
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import time_machine
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from providers.base import GridPoint, ProviderUnavailable
from providers.fixtures_provider import FixtureWeatherProvider

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)  # 11:00 in Denver, 10:00 in Seattle
DENVER = {"label": "Denver, CO", "lat": 39.7392, "lon": -104.9903}
CHEYENNE = {"label": "Cheyenne, WY", "lat": 41.1400, "lon": -104.8202}
SEATTLE = {"label": "Seattle, WA", "lat": 47.6062, "lon": -122.3321}
CHICAGO = {"label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298}
LEVELS = {"LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL", "NO_FORECAST"}


@pytest.fixture(autouse=True)
def frozen_time() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


def search(
    origin: dict[str, Any] = DENVER, destination: dict[str, Any] = CHEYENNE, **kw: Any
) -> Any:
    data = {
        "origin": origin,
        "destination": destination,
        "departure_local": kw.pop("departure_local", "2026-11-24T14:00"),
        "load_lb": kw.pop("load_lb", 42_000),
    }
    response = APIClient().post("/api/v1/routes", data, format="json")
    assert response.status_code == 200, response.json()
    return response.json()


def risk(trip_id: str) -> Any:
    return APIClient().post("/api/v1/risk", {"trip_id": trip_id}, format="json")


def test_the_two_step_flow_returns_the_documented_shape() -> None:
    trip = search()
    response = risk(trip["trip_id"])
    assert response.status_code == 200
    data = response.json()

    assert set(data) == {"routes", "recommendation", "heatmap", "weather_as_of", "stale"}
    assert [r["id"] for r in data["routes"]] == [r["id"] for r in trip["routes"]]
    assert data["stale"] is False
    assert data["weather_as_of"] == "2026-11-24T18:00:00Z"

    route = data["routes"][0]
    assert set(route) == {"id", "checkpoints", "segments", "summary"}
    checkpoint = route["checkpoints"][0]
    assert set(checkpoint) == {
        "idx", "mile", "lat", "lon", "eta_utc", "tz", "road", "town", "town_dist_mi", "town_dir",
        "wind_mph", "gust_mph", "rain_in_hr", "snow_in_hr", "level", "reasons", "forecast",
    }  # fmt: skip
    assert checkpoint["idx"] == 0
    assert checkpoint["mile"] == 0
    assert checkpoint["eta_utc"] == trip["departure"]["utc"]
    assert checkpoint["tz"] == "America/Denver"
    assert checkpoint["level"] in LEVELS
    assert checkpoint["forecast"] is True
    assert isinstance(checkpoint["road"], str)


def test_checkpoints_follow_the_interval_chosen_in_step_one() -> None:
    trip = search()
    route = risk(trip["trip_id"]).json()["routes"][0]
    miles = [c["mile"] for c in route["checkpoints"]]
    assert miles[:3] == [0, 10, 20]  # 10 mile interval for a ~110 mile trip
    assert miles == sorted(miles)
    assert miles[-1] == pytest.approx(trip["routes"][0]["distance_mi"], abs=0.1)


def test_segments_and_summary_cover_the_whole_route() -> None:
    trip = search()
    route = risk(trip["trip_id"]).json()["routes"][0]
    assert route["segments"][0]["from_mi"] == 0
    assert route["segments"][-1]["to_mi"] == pytest.approx(
        trip["routes"][0]["distance_mi"], abs=0.1
    )
    assert all(s["level"] in LEVELS for s in route["segments"])
    miles = route["summary"]["miles"]
    assert list(miles) == ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL", "NO_FORECAST"]
    assert sum(miles.values()) == pytest.approx(trip["routes"][0]["distance_mi"], abs=0.6)
    assert route["summary"]["avg_risk"] is not None


def test_every_non_low_checkpoint_explains_itself() -> None:
    trip = search()
    for route in risk(trip["trip_id"]).json()["routes"]:
        for checkpoint in route["checkpoints"]:
            if checkpoint["level"] != "LOW":
                assert checkpoint["reasons"]


def test_the_recommendation_is_one_of_the_routes_with_a_reason() -> None:
    trip = search()
    data = risk(trip["trip_id"]).json()
    recommendation = data["recommendation"]
    ids = [r["id"] for r in data["routes"]]
    assert recommendation["route_id"] in ids
    assert sorted(recommendation["ranking"]) == sorted(ids)
    assert recommendation["reason"]
    assert isinstance(recommendation["all_unsafe"], bool)
    assert isinstance(recommendation["all_clear"], bool)


def test_the_heatmap_has_the_documented_layers_and_sizes() -> None:
    trip = search()
    heatmap = risk(trip["trip_id"]).json()["heatmap"]
    assert heatmap["grid_deg"] == 0.2
    assert heatmap["hours"] == 49
    assert heatmap["start_utc"] == trip["departure"]["utc"]
    cells = len(base64.b64decode(heatmap["cells"])) // 8
    assert cells > 20
    assert set(heatmap["layers"]) == {"risk", "wind", "rain", "snow"}
    assert len(base64.b64decode(heatmap["layers"]["risk"])) == 49 * cells
    assert len(base64.b64decode(heatmap["layers"]["rain"])) == 49 * cells * 2


def test_the_longest_trip_response_fits_the_payload_budget() -> None:
    trip = search(SEATTLE, CHICAGO, departure_local="2026-11-24T12:00")
    response = risk(trip["trip_id"])
    assert response.status_code == 200
    body = json.dumps(response.json()).encode()
    assert len(gzip.compress(body)) < 400_000
    assert response.json()["heatmap"]["grid_deg"] == 0.8


def test_unknown_or_expired_trips_are_gone() -> None:
    response = risk("t_does_not_exist")
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "TRIP_EXPIRED"


@pytest.mark.parametrize(
    "body", [{}, {"trip_id": ""}, {"trip_id": None}, {"trip_id": "t_x", "extra": 1}]
)
def test_a_bad_request_body_is_a_validation_error(body: dict[str, Any]) -> None:
    response = APIClient().post("/api/v1/risk", body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_total_weather_failure_is_a_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        def hourly(self, *args: Any) -> dict[GridPoint, Any]:
            raise ProviderUnavailable("down")

    trip = search()
    monkeypatch.setattr("api.views.weather_provider", lambda: Down())
    response = risk(trip["trip_id"])
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_a_repeat_assessment_makes_no_weather_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Counting(FixtureWeatherProvider):
        calls = 0

        def hourly(self, points: Any, start_utc: Any, end_utc: Any) -> Any:
            Counting.calls += 1
            return super().hourly(points, start_utc, end_utc)

    monkeypatch.setattr("api.views.weather_provider", lambda: Counting())
    trip = search()
    assert risk(trip["trip_id"]).status_code == 200
    first = Counting.calls
    assert first >= 1
    assert risk(trip["trip_id"]).status_code == 200
    assert Counting.calls == first


def test_risk_requests_are_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES", {"risk": "2/hour", "routes": "50/hour"}
    )
    trip = search()
    statuses = [risk(trip["trip_id"]).status_code for _ in range(4)]
    assert statuses == [200, 200, 429, 429]


def test_only_post_is_allowed() -> None:
    assert APIClient().get("/api/v1/risk").status_code == 405
