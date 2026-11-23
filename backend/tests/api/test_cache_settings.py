"""The shared weather cache must not be culled after a few hundred entries (Django's default)."""

from typing import Any, cast

from config import settings


def test_the_cache_keeps_far_more_than_djangos_default_of_300_entries() -> None:
    # Read the real settings module: the test suite swaps in its own cache at runtime.
    default = cast(dict[str, Any], settings.CACHES["default"])
    options = cast(dict[str, Any], default["OPTIONS"])
    # A long trip needs ~250 grid cells x 2 keys; several trips must fit side by side.
    assert options["MAX_ENTRIES"] >= 10_000
