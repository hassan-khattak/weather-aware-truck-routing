"""Test-only: make an endpoint fail on demand so every error path can be exercised end to end.

Only works when `PROVIDERS_MODE=fixtures`, which settings refuse to start with DEBUG off, so this
cannot exist in production. Send `X-Force-Error: <CODE>` to get that error's normal response.
"""

from django.conf import settings
from rest_framework import exceptions
from rest_framework.request import Request

from api.errors import (
    ApiError,
    NoRouteFound,
    OutOfCoverage,
    ProviderDown,
    TripExpired,
    message_error,
)

HEADER = "X-Force-Error"
_API_ERRORS: dict[str, type[ApiError]] = {
    "NO_ROUTE": NoRouteFound,
    "OUT_OF_COVERAGE": OutOfCoverage,
    "PROVIDER_UNAVAILABLE": ProviderDown,
    "TRIP_EXPIRED": TripExpired,
}
FORCEABLE = (*sorted(_API_ERRORS), "RATE_LIMITED")


def maybe_force_error(request: Request) -> None:
    """Raise the requested error if the header is present and fixture mode is on."""
    code = request.headers.get(HEADER)
    if not code or settings.PROVIDERS_MODE != "fixtures":
        return
    if code == "RATE_LIMITED":
        raise exceptions.Throttled(wait=60)
    error = _API_ERRORS.get(code)
    if error is None:
        raise message_error(HEADER, f"Unknown error code. Use one of: {', '.join(FORCEABLE)}.")
    raise error
