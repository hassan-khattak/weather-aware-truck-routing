import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from api.rules import get_rules
from providers.fixtures_provider import DEFAULT_FIXTURE_DIR
from providers.openmeteo import OpenMeteoWeatherProvider
from providers.recording import record_fixtures
from providers.tomtom import TomTomRoutingProvider


class Command(BaseCommand):
    help = (
        "Call the LIVE TomTom and Open-Meteo APIs for the four sample trips and save the "
        "responses as test fixtures. Needs TOM_TOM_API_KEY; uses 4 routing calls and a few "
        "hundred weather locations."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--out", type=Path, default=DEFAULT_FIXTURE_DIR)

    def handle(self, *args: Any, **options: Any) -> None:
        api_key = os.environ.get("TOM_TOM_API_KEY", "")
        if not api_key:
            raise CommandError("TOM_TOM_API_KEY is not set")
        rules = get_rules()
        summary = record_fixtures(
            TomTomRoutingProvider(api_key),
            OpenMeteoWeatherProvider(batch_size=rules.weather_grid.batch_size),
            options["out"],
            rules,
            datetime.now(UTC),
        )
        for name, count in summary.items():
            self.stdout.write(f"{name}: {count}")
        self.stdout.write(self.style.SUCCESS(f"Fixtures written to {options['out']}"))
