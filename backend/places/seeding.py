"""Load towns from a CSV into the database (idempotent)."""

import csv
from collections.abc import Iterable
from pathlib import Path

from places.models import Town

COLUMNS = ("name", "state", "population", "lat", "lon")


class TownCsvError(Exception):
    """The towns CSV is missing columns or has an unreadable row."""


def read_towns(path: Path) -> list[Town]:
    """Parse the CSV (header: name,state,population,lat,lon) into unsaved Town objects."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise TownCsvError(f"{path.name} is missing columns: {', '.join(missing)}")
        towns = []
        for number, row in enumerate(reader, start=2):
            try:
                towns.append(
                    Town(
                        name=row["name"].strip(),
                        state=row["state"].strip().upper(),
                        population=int(row["population"]),
                        lat=float(row["lat"]),
                        lon=float(row["lon"]),
                    )
                )
            except (ValueError, KeyError, AttributeError) as error:
                raise TownCsvError(f"{path.name} line {number}: {error}") from error
    return towns


def seed_towns(towns: Iterable[Town]) -> int:
    """Insert new towns and refresh populations of existing ones. Safe to run repeatedly."""
    batch = list(towns)
    Town.objects.bulk_create(
        batch,
        update_conflicts=True,
        unique_fields=["name", "state", "lat", "lon"],
        update_fields=["population"],
        batch_size=2000,
    )
    return len(batch)
