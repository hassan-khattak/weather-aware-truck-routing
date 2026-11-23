"""Step 1 of a search: real truck routes with realistic ETAs (plan.md sections 3.3, 3.8, 5.2).

Calls the routing provider, measures each route along its full geometry, chooses the checkpoint
interval from the longest route, and builds each route's ETA plan (driving time, required stops,
timeline). Nothing here draws or scores anything.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from api.validation import TripRequest
from core.alternatives import evaluate_candidate, via_candidates
from core.checkpoints import choose_interval, route_length_mi
from core.eta import EtaPlan, build_eta_plan
from core.rules import Rules
from providers.base import ProviderError, RawRoute, RoutingProvider, Vehicle, vehicle_for_load

logger = logging.getLogger(__name__)

MAX_ROUTES = 3  # the brief asks for up to three route options


@dataclass(frozen=True)
class PlannedRoute:
    id: str
    order: int
    source: Literal["api", "generated"]
    raw: RawRoute  # full-resolution geometry, anchors, road names
    length_mi: float  # measured along the full geometry (what checkpoints are placed on)
    plan: EtaPlan
    long_range_forecast: bool  # the trip reaches past the reliable part of the forecast


@dataclass(frozen=True)
class Trip:
    request: TripRequest
    interval_mi: float
    routes: tuple[PlannedRoute, ...]
    notes: tuple[str, ...]


def route_id(order: int) -> str:
    return chr(ord("A") + order)


def distinct_routes_note(count: int) -> str | None:
    """Honest wording when fewer than three distinct routes exist."""
    if count >= MAX_ROUTES:
        return None
    if count == 1:
        return "Only 1 truck route found for this trip."
    return f"{count} distinct truck routes found for this trip."


def plan_route(
    order: int,
    raw: RawRoute,
    request: TripRequest,
    rules: Rules,
    now: datetime,
    source: Literal["api", "generated"] = "api",
) -> PlannedRoute:
    length = route_length_mi(raw.points)
    plan = build_eta_plan(raw.anchors, length, request.departure.utc, rules)
    arrival = request.departure.utc + timedelta(seconds=plan.total_s)
    limit = now + timedelta(hours=rules.departure.long_range_note_h)
    return PlannedRoute(
        id=route_id(order),
        order=order,
        source=source,
        raw=raw,
        length_mi=length,
        plan=plan,
        long_range_forecast=arrival > limit,
    )


def _add_generated_alternatives(
    routes: list[PlannedRoute],
    request: TripRequest,
    provider: RoutingProvider,
    vehicle: Vehicle,
    rules: Rules,
    now: datetime,
) -> None:
    """Try to reach three routes by asking for routes through via-points beside the main one.

    A generated route is shown only if the provider returns it as a real truck route AND it is
    clearly different from every route already shown (overlap under the limit) AND not much
    slower than the fastest (plan.md sections 3.8, 4.12). We never draw a route ourselves.
    """
    origin = (request.origin.lat, request.origin.lon)
    destination = (request.destination.lat, request.destination.lon)
    for via in via_candidates(routes[0].raw.points, rules):
        if len(routes) >= MAX_ROUTES:
            return
        try:
            found = provider.routes(origin, destination, request.departure.utc, vehicle, via=(via,))
        except ProviderError as error:
            logger.info("no generated alternative through %s: %s", via, error)
            continue
        if not found:
            continue
        candidate = plan_route(len(routes), found[0], request, rules, now, source="generated")
        verdict = evaluate_candidate(
            candidate.raw.points,
            candidate.plan.total_s,
            [route.raw.points for route in routes],
            min(route.plan.total_s for route in routes),
            rules,
        )
        if verdict.accepted:
            routes.append(candidate)
        else:
            logger.info("generated alternative rejected (%s)", verdict.reason)


def plan_trip(request: TripRequest, provider: RoutingProvider, rules: Rules, now: datetime) -> Trip:
    """Plan the trip. Raises NoRoute / ProviderUnavailable from the provider."""
    vehicle = vehicle_for_load(request.load_lb, rules)
    raw_routes = provider.routes(
        (request.origin.lat, request.origin.lon),
        (request.destination.lat, request.destination.lon),
        request.departure.utc,
        vehicle,
    )[:MAX_ROUTES]
    planned = [plan_route(order, raw, request, rules, now) for order, raw in enumerate(raw_routes)]
    if len(planned) < MAX_ROUTES:
        _add_generated_alternatives(planned, request, provider, vehicle, rules, now)
    routes = tuple(planned)
    note = distinct_routes_note(len(routes))
    return Trip(
        request=request,
        interval_mi=choose_interval(max(r.length_mi for r in routes), rules),
        routes=routes,
        notes=(note,) if note else (),
    )
