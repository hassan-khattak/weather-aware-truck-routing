"""Pick the providers for the current PROVIDERS_MODE (live services or recorded fixtures)."""

from django.conf import settings
from django.core.cache import cache

from api.rules import get_rules
from providers.base import RoutingProvider, WeatherProvider


def routing_provider() -> RoutingProvider:
    if settings.PROVIDERS_MODE == "fixtures":
        from providers.fixtures_provider import FixtureRoutingProvider

        return FixtureRoutingProvider()
    from providers.tomtom import TomTomRoutingProvider

    return TomTomRoutingProvider(settings.TOMTOM_API_KEY, cache=cache)


def weather_provider() -> WeatherProvider:
    if settings.PROVIDERS_MODE == "fixtures":
        from providers.fixtures_provider import FixtureWeatherProvider

        return FixtureWeatherProvider()
    from providers.openmeteo import OpenMeteoWeatherProvider

    return OpenMeteoWeatherProvider(batch_size=get_rules().weather_grid.batch_size)
