"""JSON (de)serialisation of recorded provider data. Test-only data; see providers/fixtures/."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.models import HourlySeries
from providers.base import GridPoint, Place, RawRoute, RoadMark
from providers.sample_trips import SampleTrip


def route_to_dict(route: RawRoute) -> dict[str, Any]:
    return {
        "points": [[round(lat, 5), round(lon, 5)] for lat, lon in route.points],
        "distance_mi": round(route.distance_mi, 3),
        "drive_s": route.drive_s,
        "anchors": [[round(mi, 4), s] for mi, s in route.anchors],
        "roads": [[round(m.mile, 3), m.road] for m in route.roads],
    }


def route_from_dict(data: dict[str, Any]) -> RawRoute:
    return RawRoute(
        points=tuple((lat, lon) for lat, lon in data["points"]),
        distance_mi=float(data["distance_mi"]),
        drive_s=float(data["drive_s"]),
        anchors=tuple((float(mi), float(s)) for mi, s in data["anchors"]),
        roads=tuple(RoadMark(mile=float(m), road=name) for m, name in data["roads"]),
    )


def save_trip(path: Path, trip: SampleTrip, routes: list[RawRoute]) -> None:
    payload = {
        "slug": trip.slug,
        "origin": {"label": trip.origin.label, "lat": trip.origin.lat, "lon": trip.origin.lon},
        "destination": {
            "label": trip.destination.label,
            "lat": trip.destination.lat,
            "lon": trip.destination.lon,
        },
        "routes": [route_to_dict(r) for r in routes],
    }
    path.write_text(json.dumps(payload, separators=(",", ":")))


def load_trip(path: Path) -> tuple[SampleTrip, list[RawRoute]]:
    data = json.loads(path.read_text())
    o, d = data["origin"], data["destination"]
    trip = SampleTrip(
        slug=data["slug"],
        origin=Place(o["label"], o["lat"], o["lon"]),
        destination=Place(d["label"], d["lat"], d["lon"]),
    )
    return trip, [route_from_dict(r) for r in data["routes"]]


def save_weather(path: Path, recorded_at: datetime, nodes: dict[GridPoint, HourlySeries]) -> None:
    def values(series: tuple[float | None, ...]) -> list[float | None]:
        return list(series)

    payload = {
        "recorded_at": recorded_at.astimezone(UTC).isoformat(),
        "nodes": [
            {
                "lat": point.lat,
                "lon": point.lon,
                "start_utc": s.start_utc.astimezone(UTC).isoformat(),
                "wind": values(s.wind_mph),
                "gust": values(s.gust_mph),
                "rain": values(s.rain_in_hr),
                "snow": values(s.snow_in_hr),
            }
            for point, s in sorted(nodes.items())
        ],
    }
    path.write_text(json.dumps(payload, separators=(",", ":")))


def load_weather(path: Path) -> list[tuple[GridPoint, HourlySeries]]:
    data = json.loads(path.read_text())
    return [
        (
            GridPoint(node["lat"], node["lon"]),
            HourlySeries(
                start_utc=datetime.fromisoformat(node["start_utc"]),
                wind_mph=tuple(node["wind"]),
                gust_mph=tuple(node["gust"]),
                rain_in_hr=tuple(node["rain"]),
                snow_in_hr=tuple(node["snow"]),
            ),
        )
        for node in data["nodes"]
    ]
