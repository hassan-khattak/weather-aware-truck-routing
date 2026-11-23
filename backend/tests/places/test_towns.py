"""Town seeding and PostGIS nearest-town lookup.

The nearest-town tests need PostGIS, so they only run when DATABASE_URL points at Postgres
(docker compose up db; CI uses a PostGIS service). Everything else runs on any database.
"""

from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from places.models import Town
from places.nearest import compass, nearest_town
from places.seeding import TownCsvError, read_towns, seed_towns

needs_postgis = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="needs PostGIS (set DATABASE_URL)"
)

CSV_HEADER = "name,state,population,lat,lon\n"
TOWNS_CSV = (
    CSV_HEADER
    + "Amarillo,TX,200000,35.2220,-101.8313\n"
    + "Canyon,TX,15000,34.9803,-101.9187\n"
    + "Tucumcari,NM,5000,35.1717,-103.7249\n"
    + "Vega,TX,900,35.2423,-102.4291\n"
)


@pytest.fixture
def towns_csv(tmp_path: Path) -> Path:
    path = tmp_path / "towns.csv"
    path.write_text(TOWNS_CSV)
    return path


# --- compass (pure) ---


@pytest.mark.parametrize(
    ("to_lat", "to_lon", "expected"),
    [
        (36.0, -100.0, "N"),
        (35.0, -99.0, "E"),
        (34.0, -100.0, "S"),
        (35.0, -101.0, "W"),
        (36.0, -99.0, "NE"),
        (34.0, -99.0, "SE"),
        (34.0, -101.0, "SW"),
        (36.0, -101.0, "NW"),
    ],
)
def test_compass_direction(to_lat: float, to_lon: float, expected: str) -> None:
    assert compass(35.0, -100.0, to_lat, to_lon) == expected


# --- CSV parsing ---


def test_read_towns_parses_rows(towns_csv: Path) -> None:
    towns = read_towns(towns_csv)
    assert [t.name for t in towns] == ["Amarillo", "Canyon", "Tucumcari", "Vega"]
    assert towns[0].state == "TX"
    assert towns[0].population == 200000
    assert towns[0].lat == pytest.approx(35.2220)


def test_missing_columns_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("name,state\nAmarillo,TX\n")
    with pytest.raises(TownCsvError, match="missing columns: population, lat, lon"):
        read_towns(path)


def test_a_bad_row_names_its_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(CSV_HEADER + "Amarillo,TX,lots,35.2,-101.8\n")
    with pytest.raises(TownCsvError, match="line 2"):
        read_towns(path)


# --- seeding ---


@pytest.mark.django_db
def test_seeding_is_idempotent(towns_csv: Path) -> None:
    assert seed_towns(read_towns(towns_csv)) == 4
    seed_towns(read_towns(towns_csv))
    assert Town.objects.count() == 4


@pytest.mark.django_db
def test_seeding_again_refreshes_populations(tmp_path: Path, towns_csv: Path) -> None:
    seed_towns(read_towns(towns_csv))
    updated = tmp_path / "updated.csv"
    updated.write_text(CSV_HEADER + "Amarillo,TX,250000,35.2220,-101.8313\n")
    seed_towns(read_towns(updated))
    assert Town.objects.get(name="Amarillo").population == 250000
    assert Town.objects.count() == 4


@pytest.mark.django_db
def test_the_seed_command_loads_a_csv(towns_csv: Path) -> None:
    call_command("seed_towns", csv=towns_csv)
    call_command("seed_towns", csv=towns_csv)
    assert Town.objects.count() == 4


def test_the_seed_command_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="not found"):
        call_command("seed_towns", csv=tmp_path / "nope.csv")


# --- nearest town (PostGIS) ---


@pytest.fixture
def seeded(db: None, towns_csv: Path) -> None:
    seed_towns(read_towns(towns_csv))


@needs_postgis
def test_a_point_on_i_40_near_amarillo_finds_amarillo(seeded: None) -> None:
    town = nearest_town(35.19, -101.83)
    assert town is not None
    assert town.label == "Amarillo, TX"
    assert town.distance_mi < 4
    assert town.direction == "S"


@needs_postgis
def test_a_far_point_reports_the_distance_and_direction_from_the_town(seeded: None) -> None:
    town = nearest_town(35.17, -103.2)  # open country east of Tucumcari
    assert town is not None
    assert town.label == "Tucumcari, NM"
    assert 29 < town.distance_mi < 31
    assert town.direction == "E"


@needs_postgis
def test_tiny_places_are_ignored_by_default(seeded: None) -> None:
    near_vega = (35.24, -102.43)
    default = nearest_town(*near_vega)
    assert default is not None
    assert default.name != "Vega"  # population 900 < 1,000
    small_ok = nearest_town(*near_vega, min_population=500)
    assert small_ok is not None
    assert small_ok.name == "Vega"


@needs_postgis
@pytest.mark.django_db
def test_no_towns_means_no_answer() -> None:
    assert nearest_town(35.19, -101.83) is None


@needs_postgis
@pytest.mark.django_db
def test_the_spatial_index_exists() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'places_town_geog_gist'")
        row = cursor.fetchone()
    assert row is not None
    assert "gist" in row[0].lower()
