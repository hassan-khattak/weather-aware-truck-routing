"""ETAs from timing anchors plus hours of service (plan.md sections 3.3, 4.7)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.eta import build_eta_plan
from core.rules import HoursOfService, load_rules

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")
DEP = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
HOUR = 3600


def steady(miles: float, mph: float = 60.0) -> list[tuple[float, float]]:
    """Anchors for a constant-speed drive."""
    return [(0.0, 0.0), (miles, miles / mph * HOUR)]


def has_point(timeline: list[tuple[float, float]], elapsed: float, mile: float) -> bool:
    return any(e == pytest.approx(elapsed) and m == pytest.approx(mile) for e, m in timeline)


def test_driving_time_interpolates_linearly_between_anchors() -> None:
    plan = build_eta_plan([(0, 0), (10, 600), (100, 3000)], 100, DEP, RULES)
    assert plan.drive_s_at_mile(10) == pytest.approx(600)
    assert plan.drive_s_at_mile(55) == pytest.approx(1800)  # halfway through the slow-then-fast leg
    assert plan.drive_s_at_mile(100) == pytest.approx(3000)


def test_anchor_distances_are_rescaled_to_the_measured_route_length() -> None:
    # The routing engine says 100 mi; our haversine length is 110 mi.
    plan = build_eta_plan([(0, 0), (100, 6000)], 110, DEP, RULES)
    assert plan.drive_s_at_mile(110) == pytest.approx(6000)
    assert plan.drive_s_at_mile(55) == pytest.approx(3000)


def test_a_missing_origin_anchor_is_added() -> None:
    plan = build_eta_plan([(50, 3000), (100, 6000)], 100, DEP, RULES)
    assert plan.drive_s_at_mile(25) == pytest.approx(1500)
    assert plan.drive_s_at_mile(0) == 0


def test_a_short_drive_has_no_stops_and_eta_is_departure_plus_driving() -> None:
    plan = build_eta_plan(steady(300), 300, DEP, RULES)
    assert plan.stops == ()
    assert plan.drive_s == pytest.approx(5 * HOUR)
    assert plan.total_s == pytest.approx(5 * HOUR)
    assert plan.eta_at_mile(120) == DEP + timedelta(hours=2)


def test_twelve_hour_drive_has_a_break_at_8h_and_a_rest_at_11h() -> None:
    plan = build_eta_plan(steady(720), 720, DEP, RULES)
    assert [stop.type for stop in plan.stops] == ["break", "rest"]

    brk, rest = plan.stops
    assert brk.mile == pytest.approx(480)
    assert brk.start_utc == DEP + timedelta(hours=8)
    assert brk.duration_s == 30 * 60

    assert rest.mile == pytest.approx(660)
    assert rest.start_utc == DEP + timedelta(hours=11, minutes=30)  # after the earlier break
    assert rest.duration_s == 10 * HOUR

    assert plan.drive_s == pytest.approx(12 * HOUR)
    assert plan.total_s == pytest.approx(12 * HOUR + 30 * 60 + 10 * HOUR)


def test_etas_after_a_stop_are_shifted_by_its_duration() -> None:
    plan = build_eta_plan(steady(720), 720, DEP, RULES)
    # 481 mi = 8h01m of driving, plus the 30 min break.
    assert plan.eta_at_mile(481) == DEP + timedelta(hours=8, minutes=1 + 30)


def test_a_checkpoint_exactly_at_a_stop_gets_the_arrival_time() -> None:
    plan = build_eta_plan(steady(720), 720, DEP, RULES)
    assert plan.eta_at_mile(480) == DEP + timedelta(hours=8)  # before the break
    assert plan.eta_at_mile(660) == DEP + timedelta(hours=11, minutes=30)  # before the rest


def test_eta_after_the_rest_includes_break_and_rest() -> None:
    plan = build_eta_plan(steady(720), 720, DEP, RULES)
    expected = DEP + timedelta(hours=11, minutes=1) + timedelta(minutes=30) + timedelta(hours=10)
    assert plan.eta_at_mile(661) == expected


def test_driving_exactly_8_hours_needs_no_break() -> None:
    plan = build_eta_plan(steady(480), 480, DEP, RULES)
    assert plan.stops == ()
    assert plan.total_s == pytest.approx(8 * HOUR)


def test_driving_exactly_11_hours_needs_only_the_break() -> None:
    plan = build_eta_plan(steady(660), 660, DEP, RULES)
    assert [stop.type for stop in plan.stops] == ["break"]
    assert plan.total_s == pytest.approx(11 * HOUR + 30 * 60)


def test_multi_day_trip_repeats_breaks_and_rests() -> None:
    plan = build_eta_plan(steady(1500), 1500, DEP, RULES)  # 25 h of driving
    assert [stop.type for stop in plan.stops] == ["break", "rest", "break", "rest"]
    assert [round(stop.mile) for stop in plan.stops] == [480, 660, 1140, 1320]


def test_the_driver_may_drive_the_full_11_hours_again_after_a_rest() -> None:
    plan = build_eta_plan(steady(1500), 1500, DEP, RULES)
    first_rest, second_rest = (s for s in plan.stops if s.type == "rest")
    assert second_rest.mile - first_rest.mile == pytest.approx(660)  # 11 h at 60 mph


def test_timeline_has_flat_segments_for_stops() -> None:
    plan = build_eta_plan(steady(720), 720, DEP, RULES)
    timeline = list(plan.timeline)
    assert timeline[0] == (0.0, 0.0)
    assert timeline[-1][0] == pytest.approx(plan.total_s)
    assert timeline[-1][1] == pytest.approx(720)

    break_start = 8 * HOUR
    assert has_point(timeline, break_start, 480)
    assert has_point(timeline, break_start + 1800, 480)


def test_timeline_never_goes_backwards() -> None:
    plan = build_eta_plan(steady(1500), 1500, DEP, RULES)
    elapsed = [point[0] for point in plan.timeline]
    miles = [point[1] for point in plan.timeline]
    assert elapsed == sorted(elapsed)
    assert miles == sorted(miles)


def test_naive_departure_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        build_eta_plan(steady(100), 100, datetime(2026, 11, 24, 12, 0), RULES)  # noqa: DTZ001


@pytest.mark.parametrize(
    "anchors",
    [[], [(0, 0)], [(0, 0), (50, 100), (40, 200)], [(0, 0), (50, 200), (80, 100)]],
)
def test_bad_anchors_are_rejected(anchors: list[tuple[float, float]]) -> None:
    with pytest.raises(ValueError, match="anchor"):
        build_eta_plan(anchors, 100, DEP, RULES)


def test_route_length_must_be_positive() -> None:
    with pytest.raises(ValueError, match="length"):
        build_eta_plan(steady(100), 0, DEP, RULES)


def test_non_positive_limits_are_rejected_to_avoid_endless_loops() -> None:
    broken = RULES.model_copy(
        update={
            "hours_of_service": HoursOfService(
                break_after_driving_h=0,
                break_duration_min=30,
                max_driving_h=11,
                rest_duration_h=10,
            )
        }
    )
    with pytest.raises(ValueError, match="hours"):
        build_eta_plan(steady(100), 100, DEP, broken)


@given(
    legs=st.lists(
        st.tuples(st.floats(0.1, 60), st.floats(1, 4000)),
        min_size=1,
        max_size=30,
    ),
    stretch=st.floats(0.9, 1.1),
    fractions=st.lists(st.floats(0, 1), min_size=2, max_size=25),
)
def test_property_etas_never_decrease_along_a_route(
    legs: list[tuple[float, float]], stretch: float, fractions: list[float]
) -> None:
    anchors = [(0.0, 0.0)]
    for miles, seconds in legs:
        anchors.append((anchors[-1][0] + miles, anchors[-1][1] + seconds))
    route_mi = anchors[-1][0] * stretch
    plan = build_eta_plan(anchors, route_mi, DEP, RULES)

    etas = [plan.eta_at_mile(f * route_mi) for f in sorted(fractions)]
    assert etas == sorted(etas)
    assert plan.eta_at_mile(0) == DEP
    assert plan.total_s >= plan.drive_s
