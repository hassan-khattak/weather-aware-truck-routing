"""The POST /routes response body (plan.md section 7.3)."""

from datetime import datetime
from typing import Any

from api import polyline
from core.rules import Rules
from trips.geometry import simplify
from trips.planner import PlannedRoute, Trip


def iso_z(moment: datetime) -> str:
    """UTC timestamp like 2026-11-24T21:00:00Z."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def route_payload(route: PlannedRoute, rules: Rules) -> dict[str, Any]:
    drawn = simplify(route.raw.points, rules.display.geometry_tolerance_deg)
    return {
        "id": route.id,
        "order": route.order,
        "source": route.source,
        "distance_mi": round(route.length_mi, 1),
        "drive_s": round(route.plan.drive_s),
        "total_s": round(route.plan.total_s),
        "geometry": polyline.encode(drawn),
        "stops": [
            {
                "type": stop.type,
                "mile": round(stop.mile, 1),
                "start_utc": iso_z(stop.start_utc),
                "duration_s": round(stop.duration_s),
            }
            for stop in route.plan.stops
        ],
        # [elapsed seconds, mile] pairs; the mile stays flat while the truck is parked.
        "timeline": [[round(elapsed), round(mile, 1)] for elapsed, mile in route.plan.timeline],
        "long_range_forecast": route.long_range_forecast,
    }


def routes_payload(trip: Trip, trip_id: str, rules: Rules) -> dict[str, Any]:
    departure = trip.request.departure
    return {
        "trip_id": trip_id,
        "departure": {
            "utc": iso_z(departure.utc),
            "tz": departure.tz,
            "local": departure.local.strftime("%Y-%m-%dT%H:%M"),
        },
        "interval_mi": trip.interval_mi,
        "routes": [route_payload(route, rules) for route in trip.routes],
        "notes": list(trip.notes),
        "warnings": list(trip.request.warnings),
    }
