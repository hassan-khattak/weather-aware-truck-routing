from datetime import UTC, datetime


def now() -> datetime:
    """The current UTC time. One place to read the clock, so tests can freeze it."""
    return datetime.now(UTC)
