"""Turn checkpoint levels into risk miles, rank routes and explain the recommendation.

Plan.md sections 3.6 and 3.7. Every mile of road takes the level of its closest checkpoint;
routes are ranked lexicographically (No-Travel miles, Severe miles, High miles, mile-weighted
average risk, total time, distance, original order), so the result is deterministic.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import inf

from core.models import RANKED_LEVELS, Level
from core.rules import Rules


@dataclass(frozen=True)
class Segment:
    """A stretch of road [from_mi, to_mi] that carries one risk level."""

    from_mi: float
    to_mi: float
    level: Level


@dataclass(frozen=True)
class RouteSummary:
    """Miles per level (all six keys, including NO_FORECAST) and the mile-weighted average."""

    miles: dict[Level, float]
    # None when no mile has a forecast. NO_FORECAST miles never count towards the average.
    avg_risk: float | None


@dataclass(frozen=True)
class RouteScore:
    """What ranking needs to know about one route."""

    id: str
    order: int  # position in the original list of routes (final tie-break)
    distance_mi: float
    total_s: float  # travel time including required stops
    summary: RouteSummary


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    ranking: list[str]
    reason: str
    all_unsafe: bool  # every route has No-Travel miles: show the red banner
    all_clear: bool  # every mile of every route is Low: show the green note


def attribute_miles(
    checkpoint_miles: Sequence[float], levels: Sequence[Level], route_mi: float
) -> list[Segment]:
    """Split the route at the midpoints between checkpoints; each stretch takes its checkpoint's
    level. Neighbouring stretches with the same level are merged."""
    if len(checkpoint_miles) != len(levels):
        raise ValueError("checkpoint miles and levels must have the same length")
    if not levels:
        raise ValueError("need at least one checkpoint")
    if any(b < a for a, b in zip(checkpoint_miles, checkpoint_miles[1:], strict=False)):
        raise ValueError("checkpoints must be in route order")

    segments: list[Segment] = []
    start = 0.0
    for i, level in enumerate(levels):
        last = i == len(levels) - 1
        end = route_mi if last else (checkpoint_miles[i] + checkpoint_miles[i + 1]) / 2
        if segments and segments[-1].level == level:
            segments[-1] = Segment(segments[-1].from_mi, end, level)
        else:
            segments.append(Segment(start, end, level))
        start = end
    return segments


def summarize_miles(miles: Mapping[Level, float], rules: Rules) -> RouteSummary:
    """Per-level miles to a summary with the mile-weighted average risk."""
    full = {level: float(miles.get(level, 0.0)) for level in Level}
    ranked_miles = sum(full[level] for level in RANKED_LEVELS)
    if ranked_miles <= 0:
        return RouteSummary(miles=full, avg_risk=None)
    weights = {Level.from_name(name): w for name, w in rules.scoring.level_weights.items()}
    weighted = sum(weights[level] * full[level] for level in RANKED_LEVELS)
    return RouteSummary(miles=full, avg_risk=weighted / ranked_miles)


def summarize(segments: Sequence[Segment], rules: Rules) -> RouteSummary:
    miles = dict.fromkeys(Level, 0.0)
    for segment in segments:
        miles[segment.level] += segment.to_mi - segment.from_mi
    return summarize_miles(miles, rules)


def _safety_key(route: RouteScore, rules: Rules) -> tuple[float, float, float, float]:
    """(No-Travel, Severe, High, average risk), rounded so float noise cannot flip a ranking."""
    digits = rules.scoring.rounding
    miles = route.summary.miles
    avg = route.summary.avg_risk
    return (
        round(miles[Level.NO_TRAVEL], digits.miles),
        round(miles[Level.SEVERE], digits.miles),
        round(miles[Level.HIGH], digits.miles),
        # No forecast at all must never look safe, so it sorts after every known average.
        inf if avg is None else round(avg, digits.avg_risk),
    )


def _rank_key(route: RouteScore, rules: Rules) -> tuple[float, ...]:
    return (
        *_safety_key(route, rules),
        round(route.total_s),
        round(route.distance_mi, rules.scoring.rounding.miles),
        route.order,
    )


def rank_routes(routes: Sequence[RouteScore], rules: Rules) -> list[str]:
    """Route ids, best first. The result does not depend on the order of `routes`."""
    return [r.id for r in sorted(routes, key=lambda r: _rank_key(r, rules))]


def _minutes_text(delta_s: float) -> str:
    minutes = round(delta_s / 60)
    if minutes > 0:
        return f"+{minutes} min"
    if minutes < 0:
        return f"{-minutes} min faster"
    return "same time"


def _explain(winner: RouteScore, ranked: list[RouteScore], rules: Rules) -> str:
    """One line: where the winner is safer than the fastest route (or the runner-up when the
    winner is itself the fastest), and what that costs in time."""
    fastest = min(ranked, key=lambda r: (r.total_s, r.order))
    reference = fastest if fastest.id != winner.id else ranked[1]
    time_text = _minutes_text(winner.total_s - reference.total_s)

    digits = rules.scoring.rounding.miles
    won, ref = _safety_key(winner, rules), _safety_key(reference, rules)
    labels = ("No-Travel mi", "Severe mi", "High mi")
    for label, mine, theirs in zip(labels, won[:3], ref[:3], strict=True):
        if mine < theirs:
            return (
                f"{round(mine, digits):g} {label} vs {round(theirs, digits):g} "
                f"on Route {reference.id}; {time_text}"
            )
    if won[3] < ref[3]:
        return f"avg risk {won[3]:.2f} vs {ref[3]:.2f} on Route {reference.id}; {time_text}"
    return f"Same risk as Route {reference.id}; {time_text}"


def recommend(routes: Sequence[RouteScore], rules: Rules) -> Recommendation:
    """Pick the best route and say why."""
    if not routes:
        raise ValueError("need at least one route to recommend")
    ranking = rank_routes(routes, rules)
    by_id = {r.id: r for r in routes}
    ranked = [by_id[route_id] for route_id in ranking]
    winner = ranked[0]

    digits = rules.scoring.rounding.miles
    reason = "Only one route available" if len(ranked) == 1 else _explain(winner, ranked, rules)
    non_low = [level for level in Level if level != Level.LOW]
    return Recommendation(
        route_id=winner.id,
        ranking=ranking,
        reason=reason,
        all_unsafe=all(round(r.summary.miles[Level.NO_TRAVEL], digits) > 0 for r in routes),
        all_clear=all(round(r.summary.miles[lv], digits) == 0 for r in routes for lv in non_low),
    )
