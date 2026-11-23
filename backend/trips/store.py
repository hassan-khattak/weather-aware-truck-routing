"""Short-lived storage of a planned trip between the two API steps (plan.md section 5.2).

/routes stores the full trip (full-resolution geometry, anchors, ETA plans) under a `trip_id`;
/risk loads it again an instant later. Stored compressed: a 2,000 mile trip holds tens of
thousands of coordinates. An unknown or expired id returns None (the API answers TRIP_EXPIRED and
the browser silently searches again).
"""

import pickle
import secrets
import zlib
from typing import Any

from django.core.cache import cache

from trips.planner import Trip

TRIP_TTL_S = 3600
_KEY = "trip:v1:{}"


def new_trip_id() -> str:
    return "t_" + secrets.token_urlsafe(12)


def save_trip(trip: Trip) -> str:
    trip_id = new_trip_id()
    blob = zlib.compress(pickle.dumps(trip, protocol=pickle.HIGHEST_PROTOCOL), level=6)
    cache.set(_KEY.format(trip_id), blob, TRIP_TTL_S)
    return trip_id


def load_trip(trip_id: str) -> Trip | None:
    # The cache is ours (never user-supplied bytes), so unpickling is safe here.
    blob: Any = cache.get(_KEY.format(trip_id))
    if not isinstance(blob, bytes):
        return None
    trip = pickle.loads(zlib.decompress(blob))  # noqa: S301
    return trip if isinstance(trip, Trip) else None
