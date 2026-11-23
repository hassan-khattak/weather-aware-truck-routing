from datetime import UTC, datetime

import pytest

from places.timezones import local_to_utc, utc_to_local, zone_for


@pytest.mark.parametrize(
    ("lat", "lon", "zone"),
    [
        (32.7767, -96.7970, "America/Chicago"),  # Dallas
        (39.7392, -104.9903, "America/Denver"),  # Denver
        (47.6062, -122.3321, "America/Los_Angeles"),  # Seattle
        (40.7128, -74.0060, "America/New_York"),  # New York
        (33.4484, -112.0740, "America/Phoenix"),  # Phoenix: no daylight saving
        (39.7684, -86.1581, "America/Indiana/Indianapolis"),
        (43.6150, -116.2023, "America/Boise"),
    ],
)
def test_zone_is_found_from_coordinates(lat: float, lon: float, zone: str) -> None:
    assert zone_for(lat, lon) == zone


def test_open_water_has_no_time_zone() -> None:
    with pytest.raises(ValueError, match="no time zone"):
        zone_for(0.0, 0.0)


def test_standard_time_conversion() -> None:
    # Chicago is UTC-6 in November.
    assert local_to_utc(datetime(2026, 11, 24, 15, 0), "America/Chicago") == datetime(
        2026, 11, 24, 21, 0, tzinfo=UTC
    )


def test_daylight_time_conversion() -> None:
    # Chicago is UTC-5 in July.
    assert local_to_utc(datetime(2026, 7, 1, 15, 0), "America/Chicago") == datetime(
        2026, 7, 1, 20, 0, tzinfo=UTC
    )


def test_a_zone_without_daylight_saving_keeps_its_offset_all_year() -> None:
    assert local_to_utc(datetime(2026, 7, 1, 12, 0), "America/Phoenix") == datetime(
        2026, 7, 1, 19, 0, tzinfo=UTC
    )
    assert local_to_utc(datetime(2026, 12, 1, 12, 0), "America/Phoenix") == datetime(
        2026, 12, 1, 19, 0, tzinfo=UTC
    )


def test_a_time_skipped_by_spring_forward_lands_on_the_same_instant_as_the_later_hour() -> None:
    # 2026-03-08 02:30 does not exist in Chicago (clocks jump 02:00 -> 03:00).
    skipped = local_to_utc(datetime(2026, 3, 8, 2, 30), "America/Chicago")
    after = local_to_utc(datetime(2026, 3, 8, 3, 30), "America/Chicago")
    assert skipped == after == datetime(2026, 3, 8, 8, 30, tzinfo=UTC)


def test_a_time_repeated_by_fall_back_means_the_first_occurrence() -> None:
    # 2026-11-01 01:30 happens twice in Chicago; the first is still daylight time (UTC-5).
    assert local_to_utc(datetime(2026, 11, 1, 1, 30), "America/Chicago") == datetime(
        2026, 11, 1, 6, 30, tzinfo=UTC
    )


def test_each_us_zone_converts_the_same_wall_clock_to_a_different_instant() -> None:
    wall = datetime(2026, 11, 24, 9, 0)
    instants = [
        local_to_utc(wall, zone)
        for zone in ("America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles")
    ]
    assert instants == sorted(instants)
    assert len(set(instants)) == 4


def test_aware_local_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="naive"):
        local_to_utc(datetime(2026, 11, 24, 15, 0, tzinfo=UTC), "America/Chicago")


def test_unknown_zones_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown time zone"):
        local_to_utc(datetime(2026, 11, 24, 15, 0), "Mars/Olympus")


def test_utc_back_to_local_wall_clock() -> None:
    local = utc_to_local(datetime(2026, 11, 24, 21, 0, tzinfo=UTC), "America/Chicago")
    assert (local.hour, local.minute) == (15, 0)
    assert local.tzname() == "CST"


def test_utc_to_local_needs_an_aware_moment() -> None:
    with pytest.raises(ValueError, match="aware"):
        utc_to_local(datetime(2026, 11, 24, 21, 0), "America/Chicago")
