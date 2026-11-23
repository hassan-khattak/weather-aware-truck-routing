"""PROVIDERS_MODE: `live` calls real services; `fixtures` replays recordings (tests only)."""

VALID_MODES = ("live", "fixtures")


def validate_providers_mode(mode: str, *, debug: bool) -> str:
    """Return the mode, or raise if it is unknown or if fixtures would run in production."""
    if mode not in VALID_MODES:
        raise RuntimeError(f"PROVIDERS_MODE must be one of {VALID_MODES}, got {mode!r}")
    if mode == "fixtures" and not debug:
        raise RuntimeError(
            "PROVIDERS_MODE=fixtures is for tests only and cannot run with DEBUG off"
        )
    return mode
