import pytest
from django.core.cache import cache
from pytest_django import Settings


@pytest.fixture(autouse=True)
def isolated_settings(settings: Settings) -> None:
    """Tests never call live services and use an in-memory cache (no cache table needed)."""
    settings.PROVIDERS_MODE = "fixtures"
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
