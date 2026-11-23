"""Mile attribution, averages, ranking and the recommendation (plan.md sections 3.6, 3.7)."""

from itertools import permutations
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.models import Level
from core.rules import load_rules
from core.scoring import (
    RouteScore,
    Segment,
    attribute_miles,
    rank_routes,
    recommend,
    summarize,
    summarize_miles,
)

RULES = load_rules(Path(__file__).resolve().parents[2] / "rules.yaml")

LOW, MOD, HIGH, SEV, NT, NF = (
    Level.LOW,
    Level.MODERATE,
    Level.HIGH,
    Level.SEVERE,
    Level.NO_TRAVEL,
    Level.NO_FORECAST,
)


def route(
    id: str,
    order: int = 0,
    minutes: float = 600,
    distance: float = 500,
    **miles: float,
) -> RouteScore:
    """A route whose per-level miles are given by name; the rest of the distance is LOW."""
    by_level = {Level[name]: value for name, value in miles.items()}
    by_level.setdefault(LOW, distance - sum(by_level.values()))
    return RouteScore(
        id=id,
        order=order,
        distance_mi=distance,
        total_s=minutes * 60,
        summary=summarize_miles(by_level, RULES),
    )


# --- mile attribution ---


def test_each_mile_takes_the_risk_of_its_closest_checkpoint() -> None:
    segments = attribute_miles([0, 25, 50, 60], [LOW, HIGH, SEV, LOW], 60)
    assert segments == [
        Segment(0, 12.5, LOW),
        Segment(12.5, 37.5, HIGH),
        Segment(37.5, 55, SEV),
        Segment(55, 60, LOW),
    ]


def test_adjacent_stretches_with_the_same_level_are_merged() -> None:
    segments = attribute_miles([0, 25, 50, 75], [LOW, LOW, HIGH, HIGH], 75)
    assert segments == [Segment(0, 37.5, LOW), Segment(37.5, 75, HIGH)]


def test_a_single_checkpoint_covers_the_whole_route() -> None:
    assert attribute_miles([0], [MOD], 10) == [Segment(0, 10, MOD)]


def test_mismatched_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="same length"):
        attribute_miles([0, 10], [LOW], 10)


def test_checkpoints_must_be_in_route_order() -> None:
    with pytest.raises(ValueError, match="order"):
        attribute_miles([0, 30, 20], [LOW, LOW, LOW], 40)


# --- summary ---


def test_summary_counts_miles_per_level_and_always_has_all_six_keys() -> None:
    summary = summarize([Segment(0, 40, LOW), Segment(40, 100, HIGH)], RULES)
    assert summary.miles[LOW] == 40
    assert summary.miles[HIGH] == 60
    assert set(summary.miles) == {LOW, MOD, HIGH, SEV, NT, NF}
    assert summary.miles[NF] == 0


def test_average_risk_is_mile_weighted() -> None:
    summary = summarize([Segment(0, 50, LOW), Segment(50, 100, HIGH)], RULES)
    assert summary.avg_risk == pytest.approx(1.0)  # (0 * 50 + 2 * 50) / 100


def test_no_forecast_miles_are_excluded_from_the_average_and_reported_separately() -> None:
    summary = summarize([Segment(0, 50, LOW), Segment(50, 100, NF)], RULES)
    assert summary.avg_risk == 0.0
    assert summary.miles[NF] == 50


def test_a_route_with_no_forecast_at_all_has_no_average() -> None:
    summary = summarize([Segment(0, 100, NF)], RULES)
    assert summary.avg_risk is None


@given(
    cuts=st.lists(st.floats(0.01, 1), min_size=1, max_size=30, unique=True),
    levels=st.lists(st.sampled_from(list(Level)), min_size=2, max_size=31),
    route_mi=st.floats(1, 3000),
)
def test_property_risk_miles_add_up_to_the_route_distance(
    cuts: list[float], levels: list[Level], route_mi: float
) -> None:
    miles = [0.0, *sorted(c * route_mi for c in cuts)]
    levels = levels[: len(miles)]
    miles = miles[: len(levels)]
    summary = summarize(attribute_miles(miles, levels, route_mi), RULES)
    assert sum(summary.miles.values()) == pytest.approx(route_mi, abs=0.01)


# --- ranking ---


def test_no_travel_miles_rank_worse_than_any_amount_of_severe() -> None:
    risky = route("A", NO_TRAVEL=1)
    slow_but_severe = route("B", order=1, SEVERE=200)
    assert rank_routes([risky, slow_but_severe], RULES) == ["B", "A"]


def test_fewer_severe_miles_win() -> None:
    assert rank_routes([route("A", SEVERE=25), route("B", order=1, SEVERE=0)], RULES) == ["B", "A"]


def test_high_miles_break_a_severe_tie() -> None:
    a = route("A", HIGH=50)
    b = route("B", order=1, HIGH=10)
    assert rank_routes([a, b], RULES) == ["B", "A"]


def test_average_risk_breaks_a_tie_on_severe_and_high_miles() -> None:
    a = route("A", MODERATE=100)
    b = route("B", order=1, MODERATE=20)
    assert rank_routes([a, b], RULES) == ["B", "A"]


def test_travel_time_breaks_a_tie_on_risk() -> None:
    slow = route("A", minutes=700)
    fast = route("B", order=1, minutes=600)
    assert rank_routes([slow, fast], RULES) == ["B", "A"]


def test_distance_then_original_order_break_remaining_ties() -> None:
    long_ = route("A", distance=520)
    short = route("B", order=1, distance=500)
    assert rank_routes([long_, short], RULES) == ["B", "A"]
    first = route("A", order=0)
    second = route("B", order=1)
    assert rank_routes([second, first], RULES) == ["A", "B"]


def test_comparisons_use_rounded_values_to_avoid_float_noise() -> None:
    # 10.04 and 10.0 severe miles are the same at one decimal, so time decides.
    noisy = route("A", minutes=590, SEVERE=10.04)
    clean = route("B", order=1, minutes=600, SEVERE=10.0)
    assert rank_routes([clean, noisy], RULES) == ["A", "B"]


def test_a_route_with_no_forecast_at_all_ranks_last_on_average_risk() -> None:
    blind = RouteScore(
        id="A", order=0, distance_mi=500, total_s=36000, summary=summarize_miles({NF: 500}, RULES)
    )
    known = route("B", order=1, minutes=700)
    assert rank_routes([blind, known], RULES) == ["B", "A"]


route_strategy = st.builds(
    lambda total, distance, severe, high, moderate: (total, distance, severe, high, moderate),
    st.integers(300, 900),
    st.sampled_from([480.0, 500.0, 520.0]),
    st.sampled_from([0.0, 10.0, 25.0]),
    st.sampled_from([0.0, 10.0, 25.0]),
    st.sampled_from([0.0, 50.0]),
)


@given(specs=st.lists(route_strategy, min_size=2, max_size=4))
def test_property_ranking_does_not_depend_on_input_order(
    specs: list[tuple[int, float, float, float, float]],
) -> None:
    routes = [
        route(chr(65 + i), order=i, minutes=t, distance=d, SEVERE=s, HIGH=h, MODERATE=m)
        for i, (t, d, s, h, m) in enumerate(specs)
    ]
    expected = rank_routes(routes, RULES)
    for shuffled in permutations(routes):
        assert rank_routes(list(shuffled), RULES) == expected


# --- recommendation and explanation ---


def test_explanation_matches_the_spec_format() -> None:
    a = route("A", order=0, minutes=600, SEVERE=25)
    b = route("B", order=1, minutes=618, SEVERE=0)
    result = recommend([a, b], RULES)
    assert result.route_id == "B"
    assert result.ranking == ["B", "A"]
    assert result.reason == "0 Severe mi vs 25 on Route A; +18 min"


def test_explanation_names_the_deciding_metric() -> None:
    a = route("A", order=0, minutes=600, NO_TRAVEL=5)
    b = route("B", order=1, minutes=610)
    assert recommend([a, b], RULES).reason == "0 No-Travel mi vs 5 on Route A; +10 min"

    c = route("C", order=0, minutes=600, HIGH=40)
    d = route("D", order=1, minutes=605, HIGH=12.5)
    assert recommend([c, d], RULES).reason == "12.5 High mi vs 40 on Route C; +5 min"


def test_explanation_uses_average_risk_when_miles_tie() -> None:
    a = route("A", order=0, minutes=600, MODERATE=100)
    b = route("B", order=1, minutes=600, MODERATE=20)
    assert recommend([a, b], RULES).reason == "avg risk 0.04 vs 0.20 on Route A; same time"


def test_when_the_winner_is_also_the_fastest_it_is_compared_with_the_runner_up() -> None:
    a = route("A", order=0, minutes=600, SEVERE=0)
    b = route("B", order=1, minutes=650, SEVERE=30)
    assert recommend([a, b], RULES).reason == "0 Severe mi vs 30 on Route B; 50 min faster"


def test_equal_risk_is_explained_by_time() -> None:
    a = route("A", order=0, minutes=600)
    b = route("B", order=1, minutes=630)
    assert recommend([a, b], RULES).reason == "Same risk as Route B; 30 min faster"


def test_a_single_route_is_recommended_without_a_comparison() -> None:
    result = recommend([route("A")], RULES)
    assert result.route_id == "A"
    assert result.ranking == ["A"]
    assert result.reason == "Only one route available"


def test_all_unsafe_when_every_route_has_no_travel_miles() -> None:
    result = recommend([route("A", NO_TRAVEL=3), route("B", order=1, NO_TRAVEL=1)], RULES)
    assert result.all_unsafe is True
    assert result.route_id == "B"  # still the least-bad route


def test_not_all_unsafe_when_one_route_avoids_no_travel() -> None:
    result = recommend([route("A", NO_TRAVEL=3), route("B", order=1)], RULES)
    assert result.all_unsafe is False


def test_all_clear_only_when_every_route_is_entirely_low() -> None:
    assert recommend([route("A"), route("B", order=1)], RULES).all_clear is True
    assert recommend([route("A"), route("B", order=1, MODERATE=1)], RULES).all_clear is False
    assert recommend([route("A"), route("B", order=1, NO_FORECAST=1)], RULES).all_clear is False


def test_recommending_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match="route"):
        recommend([], RULES)
