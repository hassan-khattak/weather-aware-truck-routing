"""Pick the providers for the current PROVIDERS_MODE (live services or recorded fixtures).

Providers are created once per configuration and reused, so HTTP connections are pooled.
"""

from functools import lru_cache

from django.conf import settings
from django.core.cache import cache

from api.rules import get_rules
from providers.base import RoutingProvider, WeatherProvider


@lru_cache(maxsize=4)
def _routing(mode: str, api_key: str) -> RoutingProvider:
    if mode == "fixtures":
        from providers.fixtures_provider import FixtureRoutingProvider

        return FixtureRoutingProvider()
    from providers.tomtom import TomTomRoutingProvider

    return TomTomRoutingProvider(api_key, cache=cache)


@lru_cache(maxsize=4)
def _weather(mode: str, batch_size: int) -> WeatherProvider:
    if mode == "fixtures":
        from providers.fixtures_provider import FixtureWeatherProvider

        return FixtureWeatherProvider()
    from providers.openmeteo import OpenMeteoWeatherProvider

    return OpenMeteoWeatherProvider(batch_size=batch_size)


def routing_provider() -> RoutingProvider:
    return _routing(settings.PROVIDERS_MODE, settings.TOMTOM_API_KEY)


def weather_provider() -> WeatherProvider:
    return _weather(settings.PROVIDERS_MODE, get_rules().weather_grid.batch_size)
