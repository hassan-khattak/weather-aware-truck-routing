from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from places.seeding import TownCsvError, read_towns, seed_towns

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "us_towns.csv"


class Command(BaseCommand):
    help = "Load US towns (GeoNames cities1000) from CSV. Idempotent: safe to run on every deploy."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="path to the towns CSV")

    def handle(self, *args: Any, **options: Any) -> None:
        path: Path = options["csv"]
        if not path.exists():
            raise CommandError(f"towns CSV not found: {path}")
        try:
            count = seed_towns(read_towns(path))
        except TownCsvError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} towns from {path.name}"))
