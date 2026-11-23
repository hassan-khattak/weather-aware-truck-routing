import pytest
from django.core.cache import cache
from pytest_django import Settings


@pytest.fixture(autouse=True)
def isolated_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never call live services, use an in-memory cache, and name no towns by default.

    Town names need PostGIS and a seeded table; the API tests must behave the same on SQLite and
    Postgres, so they skip the lookup. Town lookups are tested directly in tests/places/.
    """
    settings.PROVIDERS_MODE = "fixtures"
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    monkeypatch.setattr("api.views.lookup_town", lambda lat, lon: None)
