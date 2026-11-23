"""departure_local is the ORIGIN's wall-clock time (plan.md 4.10, trap T1).

The browser can be anywhere; the server resolves the origin's zone from its coordinates and does
everything in UTC. These tests pin that down for every US zone, both daylight-saving edges, and a
server whose own time zone is somewhere else entirely.
"""

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import time_machine
from rest_framework.test import APIClient

from api.rules import get_rules
from api.validation import parse_routes_request

DENVER = {"label": "Denver, CO", "lat": 39.7392, "lon": -104.9903}
CHEYENNE = {"label": "Cheyenne, WY", "lat": 41.14, "lon": -104.8202}


def departure(origin: dict[str, Any], local: str, now: datetime, destination: Any = DENVER) -> Any:
    data = {
        "origin": origin,
        "destination": destination,
        "departure_local": local,
        "load_lb": 20_000,
    }
    return parse_routes_request(data, now=now, rules=get_rules()).departure


# 15:00 local on 2026-11-24 in each zone, and the UTC instant that must produce.
ZONES = [
    ("New York", 40.7128, -74.0060, "America/New_York", "2026-11-24T20:00:00+00:00"),  # EST
    ("Dallas", 32.7767, -96.7970, "America/Chicago", "2026-11-24T21:00:00+00:00"),  # CST
    ("Denver", 39.7392, -104.9903, "America/Denver", "2026-11-24T22:00:00+00:00"),  # MST
    ("Seattle", 47.6062, -122.3321, "America/Los_Angeles", "2026-11-24T23:00:00+00:00"),  # PST
    ("Phoenix", 33.4484, -112.0740, "America/Phoenix", "2026-11-24T22:00:00+00:00"),  # MST all year
    (
        "Indianapolis",
        39.7684,
        -86.1581,
        "America/Indiana/Indianapolis",
        "2026-11-24T20:00:00+00:00",
    ),
    ("Boise", 43.6150, -116.2023, "America/Boise", "2026-11-24T22:00:00+00:00"),  # MST
]


@pytest.mark.parametrize(("city", "lat", "lon", "zone", "utc"), ZONES, ids=[z[0] for z in ZONES])
def test_the_same_wall_clock_means_a_different_instant_in_each_us_zone(
    city: str, lat: float, lon: float, zone: str, utc: str
) -> None:
    origin = {"label": city, "lat": lat, "lon": lon}
    result = departure(
        origin, "2026-11-24T15:00", datetime(2026, 11, 24, 11, 0, tzinfo=UTC), CHEYENNE
    )
    assert result.tz == zone
    assert result.utc == datetime.fromisoformat(utc)
    assert result.local == datetime(2026, 11, 24, 15, 0)


def test_daylight_time_shifts_the_offset() -> None:
    dallas = {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970}
    summer = departure(dallas, "2026-07-01T15:00", datetime(2026, 7, 1, 12, 0, tzinfo=UTC))
    assert summer.utc == datetime(2026, 7, 1, 20, 0, tzinfo=UTC)  # CDT = UTC-5
    winter = departure(dallas, "2026-12-01T15:00", datetime(2026, 12, 1, 12, 0, tzinfo=UTC))
    assert winter.utc == datetime(2026, 12, 1, 21, 0, tzinfo=UTC)  # CST = UTC-6


def test_a_time_skipped_by_spring_forward_resolves_to_the_same_instant_as_the_later_hour() -> None:
    dallas = {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970}
    now = datetime(2027, 3, 13, 20, 0, tzinfo=UTC)  # the day before clocks go forward
    skipped = departure(dallas, "2027-03-14T02:30", now)  # 02:30 does not exist
    after = departure(dallas, "2027-03-14T03:30", now)
    assert skipped.utc == after.utc == datetime(2027, 3, 14, 8, 30, tzinfo=UTC)


def test_a_time_repeated_by_fall_back_means_the_first_occurrence() -> None:
    dallas = {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970}
    now = datetime(2026, 10, 31, 18, 0, tzinfo=UTC)
    first = departure(dallas, "2026-11-01T01:30", now)  # 01:30 happens twice; the first is CDT
    assert first.utc == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def test_the_48_hour_window_is_measured_in_real_time_across_a_clock_change() -> None:
    dallas = {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.7970}
    now = datetime(2026, 10, 31, 18, 0, tzinfo=UTC)  # 13:00 CDT
    # 48 h later is 2026-11-02 18:00 UTC = 12:00 CST (an hour of local clock was repeated).
    assert departure(dallas, "2026-11-02T12:00", now).utc == datetime(
        2026, 11, 2, 18, 0, tzinfo=UTC
    )
    with pytest.raises(Exception, match="48 hours"):
        departure(dallas, "2026-11-02T12:01", now)


@pytest.fixture
def server_time_zone(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run with the process time zone set to `request.param` (as if the server lived there)."""
    name: str = request.param
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    yield name
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    time.tzset()


@pytest.mark.parametrize(
    "server_time_zone", ["Asia/Karachi", "America/New_York", "Pacific/Auckland"], indirect=True
)
def test_results_do_not_depend_on_the_servers_own_time_zone(server_time_zone: str) -> None:
    now = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
    body = {
        "origin": DENVER,
        "destination": CHEYENNE,
        "departure_local": "2026-11-24T14:00",
        "load_lb": 42_000,
    }
    with time_machine.travel(now, tick=False):
        response = APIClient().post("/api/v1/routes", body, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["departure"] == {
        "utc": "2026-11-24T21:00:00Z",
        "tz": "America/Denver",
        "local": "2026-11-24T14:00",
    }
    assert data["routes"][0]["stops"] == []
    assert data["routes"][0]["total_s"] > 0
