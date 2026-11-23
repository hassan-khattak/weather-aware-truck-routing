"""Offline time-zone lookup and local wall-clock to UTC conversion (plan.md section 4.10).

The browser sends the departure as the origin's wall-clock time with no offset. The server finds
the origin's IANA zone from its coordinates, converts to UTC once, and does everything else in
UTC, so results never depend on the viewer's browser time zone.
"""

from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from timezonefinder import TimezoneFinder


@lru_cache(maxsize=1)
def _finder() -> TimezoneFinder:
    return TimezoneFinder()


def zone_for(lat: float, lon: float) -> str:
    """IANA zone name (e.g. "America/Chicago") for a point on land."""
    name = _finder().timezone_at(lat=lat, lng=lon)
    # Open water comes back as an "Etc/GMT±N" band (or None); there is no local time there.
    if name is None or name.startswith("Etc/"):
        raise ValueError(f"no time zone for ({lat}, {lon})")
    return name


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown time zone: {name}") from None


def local_to_utc(local: datetime, zone_name: str) -> datetime:
    """Convert a naive wall-clock time in `zone_name` to UTC.

    Daylight-saving edges are resolved deterministically:
    - a time that does not exist (spring forward, e.g. 02:30) is read with the offset in force
      before the change, which lands on the same instant as 03:30 afterwards;
    - a time that happens twice (fall back, e.g. 01:30) means the first occurrence (daylight time).
    """
    if local.tzinfo is not None:
        raise ValueError("local time must be naive (no timezone)")
    return local.replace(tzinfo=_zone(zone_name), fold=0).astimezone(UTC)


def utc_to_local(moment: datetime, zone_name: str) -> datetime:
    """A UTC instant as wall-clock time in `zone_name` (timezone-aware)."""
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    return moment.astimezone(_zone(zone_name))
