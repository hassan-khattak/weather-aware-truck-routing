"""The four one-click sample trips (plan.md section 3.13), also used to record fixtures."""

from dataclasses import dataclass

from providers.base import Place


@dataclass(frozen=True)
class SampleTrip:
    slug: str
    origin: Place
    destination: Place


SAMPLE_TRIPS: tuple[SampleTrip, ...] = (
    SampleTrip(
        slug="denver-cheyenne",
        origin=Place("Denver, CO", 39.7392, -104.9903),
        destination=Place("Cheyenne, WY", 41.1400, -104.8202),
    ),
    SampleTrip(
        slug="saltlake-denver",
        origin=Place("Salt Lake City, UT", 40.7608, -111.8910),
        destination=Place("Denver, CO", 39.7392, -104.9903),
    ),
    SampleTrip(
        slug="chicago-dallas",
        origin=Place("Chicago, IL", 41.8781, -87.6298),
        destination=Place("Dallas, TX", 32.7767, -96.7970),
    ),
    SampleTrip(
        slug="seattle-chicago",
        origin=Place("Seattle, WA", 47.6062, -122.3321),
        destination=Place("Chicago, IL", 41.8781, -87.6298),
    ),
)
