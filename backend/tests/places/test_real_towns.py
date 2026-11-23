"""The committed GeoNames subset: contents, seeding and a real nearest-town answer."""

import pytest
from django.core.management import call_command
from django.db import connection

from places.management.commands.seed_towns import DEFAULT_CSV
from places.models import Town
from places.nearest import nearest_town
from places.seeding import read_towns

needs_postgis = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="needs PostGIS (set DATABASE_URL)"
)


def test_the_committed_csv_covers_the_continental_us_only() -> None:
    towns = read_towns(DEFAULT_CSV)
    states = {t.state for t in towns}
    assert len(towns) > 15_000
    assert {"TX", "NM", "WY", "WA", "ME", "FL"} <= states
    assert not states & {"AK", "HI", "PR"}
    assert all(t.population >= 1000 for t in towns)
    assert any(t.name == "Amarillo" and t.state == "TX" for t in towns)


@pytest.mark.django_db
def test_the_seed_command_defaults_to_the_committed_csv() -> None:
    call_command("seed_towns")
    first = Town.objects.count()
    call_command("seed_towns")
    assert first > 15_000
    assert Town.objects.count() == first  # idempotent


@needs_postgis
@pytest.mark.django_db
def test_a_point_on_i_40_near_amarillo_is_named_amarillo() -> None:
    call_command("seed_towns")
    town = nearest_town(35.19, -101.83)
    assert town is not None
    assert town.label == "Amarillo, TX"
    assert town.distance_mi < 5


@needs_postgis
@pytest.mark.django_db
def test_open_country_reports_a_distance_and_direction() -> None:
    call_command("seed_towns")
    town = nearest_town(35.17, -103.2)  # on I-40 in eastern New Mexico
    assert town is not None
    assert town.state == "NM"
    assert 5 < town.distance_mi < 45
    assert town.direction in {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}
