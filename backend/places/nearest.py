"""Nearest town to a point, answered offline by PostGIS (plan.md section 3.10).

Used to name places along a route without any extra API calls: "I-40 W near Amarillo, TX", or
"28 mi E of Tucumcari, NM" when the closest town is far away.
"""

from dataclasses import dataclass
from math import atan2, cos, degrees, radians, sin

from django.db import connection

_METERS_PER_MILE = 1609.344
_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
DEFAULT_MIN_POPULATION = 1000

# K-nearest-neighbour search over geography points; the ORDER BY expression matches the GiST
# index created in migration 0001 so PostGIS can use it.
_NEAREST_SQL = """
    SELECT name, state, lat, lon,
           ST_Distance(
               ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
               ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography
           ) / %(meters_per_mile)s AS distance_mi
    FROM places_town
    WHERE population >= %(min_population)s
    ORDER BY ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography
             <-> ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography
    LIMIT 1
"""


@dataclass(frozen=True)
class NearestTown:
    name: str
    state: str
    distance_mi: float
    # Compass direction of the *point* as seen from the town: "28 mi E of Tucumcari" is east.
    direction: str

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}"


def compass(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> str:
    """8-point compass direction from the first point towards the second."""
    lat1, lat2 = radians(from_lat), radians(to_lat)
    d_lon = radians(to_lon - from_lon)
    y = sin(d_lon) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(d_lon)
    bearing = (degrees(atan2(y, x)) + 360) % 360
    return _DIRECTIONS[round(bearing / 45) % 8]


def nearest_town(
    lat: float, lon: float, *, min_population: int = DEFAULT_MIN_POPULATION
) -> NearestTown | None:
    """The closest town with at least `min_population` people, or None if there is none."""
    params = {
        "lat": lat,
        "lon": lon,
        "min_population": min_population,
        "meters_per_mile": _METERS_PER_MILE,
    }
    with connection.cursor() as cursor:
        cursor.execute(_NEAREST_SQL, params)
        row = cursor.fetchone()
    if row is None:
        return None
    name, state, town_lat, town_lon, distance_mi = row
    return NearestTown(
        name=name,
        state=state,
        distance_mi=float(distance_mi),
        direction=compass(town_lat, town_lon, lat, lon),
    )


def lookup_town(lat: float, lon: float) -> NearestTown | None:
    """`nearest_town` that quietly returns None where PostGIS is not available (SQLite in local
    tests), so naming places is always a nice-to-have and never a reason to fail a request."""
    if connection.vendor != "postgresql":
        return None
    return nearest_town(lat, lon)
