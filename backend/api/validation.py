"""Request validation for POST /routes (plan.md sections 3.2, 3.13, 4.10, 4.11).

Field-level checks live in the serializer; this module holds the rules that need the rules.yaml
limits, the clock or the origin's time zone.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from rest_framework import serializers

from api.errors import OutOfCoverage, message_error
from core.checkpoints import haversine_mi
from core.rules import Rules
from places.timezones import local_to_utc, zone_for
from providers.base import Place

# Continental US bounding box (lat/lon degrees).
_LAT_RANGE = (24.0, 50.0)
_LON_RANGE = (-125.0, -66.5)
# The box also covers parts of Canada and Mexico, so the IANA zone must be a US zone too.
_US_ZONES = frozenset(
    {
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Phoenix",
        "America/Boise",
        "America/Detroit",
        "America/Menominee",
    }
)
_US_ZONE_PREFIXES = ("America/Indiana/", "America/Kentucky/", "America/North_Dakota/")
_MIN_TRIP_SEPARATION_MI = 0.5
LOAD_WARNING = (
    "Exceeds typical legal cargo for a 5-axle tractor-trailer; truck routes may be restricted."
)


@dataclass(frozen=True)
class Departure:
    utc: datetime
    tz: str
    local: datetime  # naive wall-clock time at the origin


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: Departure
    load_lb: float
    warnings: tuple[str, ...]


def is_us_zone(zone: str) -> bool:
    return zone in _US_ZONES or zone.startswith(_US_ZONE_PREFIXES)


def check_coverage(place: Place) -> str:
    """Raise OutOfCoverage unless the place is in the continental US. Returns its IANA zone."""
    inside_box = _LAT_RANGE[0] <= place.lat <= _LAT_RANGE[1] and (
        _LON_RANGE[0] <= place.lon <= _LON_RANGE[1]
    )
    if not inside_box:
        raise OutOfCoverage
    try:
        zone = zone_for(place.lat, place.lon)
    except ValueError:  # open water
        raise OutOfCoverage from None
    if not is_us_zone(zone):
        raise OutOfCoverage
    return zone


def zone_if_covered(place: Place) -> str | None:
    """The place's IANA zone if it is in the continental US, otherwise None."""
    try:
        return check_coverage(place)
    except OutOfCoverage:
        return None


def parse_local_departure(text: str) -> datetime:
    """A wall-clock time such as "2026-11-24T15:00", with no UTC offset."""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise message_error(
            "departure_local", "Departure must look like 2026-11-24T15:00."
        ) from None
    if parsed.tzinfo is not None:
        raise message_error(
            "departure_local", "Departure must be local time at the origin, without a UTC offset."
        )
    return parsed


def resolve_departure(local: datetime, zone: str, now: datetime, rules: Rules) -> Departure:
    """Convert the origin's wall-clock departure to UTC and enforce the allowed window."""
    utc = local_to_utc(local, zone)
    earliest = now - timedelta(minutes=rules.departure.past_grace_min)
    latest = now + timedelta(hours=rules.departure.max_ahead_h)
    if utc < earliest:
        raise message_error("departure_local", "Departure can't be in the past.")
    if utc > latest:
        raise message_error(
            "departure_local",
            f"Departure must be within the next {rules.departure.max_ahead_h:g} hours.",
        )
    return Departure(utc=utc.astimezone(UTC), tz=zone, local=local.replace(tzinfo=None))


def validate_load(load_lb: float, rules: Rules) -> tuple[str, ...]:
    """Check the cargo weight; returns warnings (soft limit) or raises (hard limit)."""
    low, high = rules.truck.load_min_lb, rules.truck.load_max_lb
    if not low <= load_lb <= high:
        raise message_error("load_lb", f"Load must be between {low:,.0f} and {high:,.0f} lb.")
    return (LOAD_WARNING,) if load_lb > rules.truck.load_warning_lb else ()


class PlaceSerializer(serializers.Serializer[Place]):
    label = serializers.CharField(max_length=160)  # type: ignore[assignment]
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)

    def to_internal_value(self, data: object) -> Place:
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise message_error(sorted(unknown)[0], "This field is not allowed.")
        values = super().to_internal_value(data)
        return Place(label=values["label"].strip(), lat=values["lat"], lon=values["lon"])


class RoutesRequestSerializer(serializers.Serializer[TripRequest]):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_local = serializers.CharField()
    load_lb = serializers.FloatField()


def parse_routes_request(data: object, *, now: datetime, rules: Rules) -> TripRequest:
    """Validate a POST /routes body. Raises DRF ValidationError or OutOfCoverage."""
    if isinstance(data, dict):
        unknown = set(data) - set(RoutesRequestSerializer().fields)
        if unknown:
            raise message_error(sorted(unknown)[0], "This field is not allowed.")
    serializer = RoutesRequestSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data

    origin: Place = values["origin"]
    destination: Place = values["destination"]
    if haversine_mi((origin.lat, origin.lon), (destination.lat, destination.lon)) < (
        _MIN_TRIP_SEPARATION_MI
    ):
        raise message_error("destination", "Choose a destination different from the origin.")

    origin_zone = check_coverage(origin)
    check_coverage(destination)
    warnings = validate_load(values["load_lb"], rules)
    departure = resolve_departure(
        parse_local_departure(values["departure_local"]), origin_zone, now, rules
    )
    return TripRequest(
        origin=origin,
        destination=destination,
        departure=departure,
        load_lb=values["load_lb"],
        warnings=warnings,
    )
