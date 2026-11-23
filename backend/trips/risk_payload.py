"""The POST /risk response body (plan.md section 7.4)."""

from typing import Any

from core.models import Level
from trips.payload import iso_z
from trips.risk import Assessment, CheckpointRisk, RouteRisk


def _checkpoint(checkpoint: CheckpointRisk) -> dict[str, Any]:
    weather = checkpoint.weather
    town = checkpoint.town
    return {
        "idx": checkpoint.idx,
        "mile": round(checkpoint.mile, 1),
        "lat": round(checkpoint.lat, 5),
        "lon": round(checkpoint.lon, 5),
        "eta_utc": iso_z(checkpoint.eta_utc),
        "tz": checkpoint.tz,
        "road": checkpoint.road,
        "town": town.label if town else None,
        "town_dist_mi": round(town.distance_mi, 1) if town else None,
        # Where the checkpoint is relative to the town: "28 mi E of Tucumcari, NM".
        "town_dir": town.direction if town else None,
        "wind_mph": weather.wind_mph if weather else None,
        "gust_mph": weather.gust_mph if weather else None,
        "rain_in_hr": weather.rain_in_hr if weather else None,
        "snow_in_hr": weather.snow_in_hr if weather else None,
        "level": checkpoint.level.name,
        "reasons": list(checkpoint.reasons),
        "forecast": weather is not None,
    }


def _route(risk: RouteRisk) -> dict[str, Any]:
    summary = risk.summary
    return {
        "id": risk.route.id,
        "checkpoints": [_checkpoint(c) for c in risk.checkpoints],
        # Stretches of road with one risk level; the map colours the route line with these.
        "segments": [
            {"from_mi": round(s.from_mi, 1), "to_mi": round(s.to_mi, 1), "level": s.level.name}
            for s in risk.segments
        ],
        "summary": {
            "miles": {level.name: round(summary.miles[level], 1) for level in _SUMMARY_ORDER},
            "avg_risk": None if summary.avg_risk is None else round(summary.avg_risk, 3),
        },
    }


_SUMMARY_ORDER = (
    Level.LOW,
    Level.MODERATE,
    Level.HIGH,
    Level.SEVERE,
    Level.NO_TRAVEL,
    Level.NO_FORECAST,
)


def risk_payload(assessment: Assessment) -> dict[str, Any]:
    recommendation = assessment.recommendation
    heatmap = assessment.heatmap
    weather = assessment.weather
    return {
        "routes": [_route(risk) for risk in assessment.routes],
        "recommendation": {
            "route_id": recommendation.route_id,
            "ranking": recommendation.ranking,
            "reason": recommendation.reason,
            "all_unsafe": recommendation.all_unsafe,
            "all_clear": recommendation.all_clear,
        },
        "heatmap": {
            "grid_deg": heatmap.grid_deg,
            "start_utc": iso_z(assessment.heatmap_start_utc),
            "hours": heatmap.hours,
            "cells": heatmap.cells,
            "layers": heatmap.layers,
        },
        "weather_as_of": iso_z(weather.as_of) if weather.as_of else None,
        "stale": weather.stale,
    }
