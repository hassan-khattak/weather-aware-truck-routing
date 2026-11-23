"""One error format for every failure: {"error": {"code", "message"[, "fields"]}} (plan.md 7.6).

Messages are plain language with a next step; the frontend shows them as written.
"""

import logging
from typing import Any

from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler  # noqa: F401

from providers.base import NoRoute, ProviderError, ProviderUnavailable

logger = logging.getLogger(__name__)

# Error code used for hand-written, user-facing validation sentences (no field-name prefix added).
MESSAGE_CODE = "message"


class ApiError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    default_message = "Something went wrong. Please try again."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class OutOfCoverage(ApiError):  # noqa: N818
    status_code = 422
    code = "OUT_OF_COVERAGE"
    default_message = "Currently supports routes within the continental US."


class NoRouteFound(ApiError):  # noqa: N818
    status_code = 422
    code = "NO_ROUTE"
    default_message = "No truck route found between these places. Try a nearby city."


class ProviderDown(ApiError):  # noqa: N818
    status_code = 503
    code = "PROVIDER_UNAVAILABLE"
    default_message = "Weather/route data is temporarily unavailable, try again in a minute."


class TripExpired(ApiError):  # noqa: N818
    status_code = 410
    code = "TRIP_EXPIRED"
    default_message = "This trip has expired. Searching again."


def message_error(field: str, message: str) -> exceptions.ValidationError:
    """A validation error whose sentence is shown to the user exactly as written."""
    return exceptions.ValidationError({field: [exceptions.ErrorDetail(message, code=MESSAGE_CODE)]})


def _body(code: str, message: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}


def _flatten(detail: Any, path: str = "") -> list[tuple[str, str, str]]:
    """Walk DRF's nested error structure into (dotted field path, message, error code)."""
    if isinstance(detail, dict):
        found: list[tuple[str, str, str]] = []
        for key, value in detail.items():
            found += _flatten(value, f"{path}.{key}" if path else str(key))
        return found
    if isinstance(detail, list):
        found = []
        for item in detail:
            found += _flatten(item, path)
        return found
    code = getattr(detail, "code", "invalid")
    return [(path or "request", str(detail), code)]


def _validation_body(exc: exceptions.ValidationError) -> dict[str, Any]:
    entries = _flatten(exc.detail)
    fields: dict[str, str] = {}
    messages: list[str] = []
    for path, text, code in entries:
        # DRF's stock messages ("This field is required.") need the field name to make sense.
        sentence = text if code == MESSAGE_CODE else f"{path.replace('_', ' ')}: {text}"
        fields.setdefault(path, sentence)
        messages.append(sentence)
    return _body("VALIDATION_ERROR", messages[0] if messages else "Invalid request.", fields)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, ApiError):
        return Response(_body(exc.code, exc.message), status=exc.status_code)
    if isinstance(exc, NoRoute):
        return Response(_body(NoRouteFound.code, NoRouteFound.default_message), status=422)
    if isinstance(exc, ProviderUnavailable):
        return Response(_body(ProviderDown.code, ProviderDown.default_message), status=503)
    if isinstance(exc, ProviderError):
        logger.error("provider rejected a request: %s", exc)
        return Response(_body(ProviderDown.code, ProviderDown.default_message), status=503)
    if isinstance(exc, exceptions.ValidationError):
        return Response(_validation_body(exc), status=400)
    if isinstance(exc, exceptions.ParseError):
        return Response(
            _body("VALIDATION_ERROR", "The request body is not valid JSON."), status=400
        )
    if isinstance(exc, exceptions.Throttled):
        response = Response(
            _body("RATE_LIMITED", "Too many searches; please wait a few minutes."), status=429
        )
        wait = getattr(exc, "wait", None)
        if wait is not None:
            response["Retry-After"] = str(int(wait) + 1)
        return response
    if isinstance(exc, exceptions.MethodNotAllowed):
        return Response(_body("METHOD_NOT_ALLOWED", "This method is not allowed here."), status=405)
    if isinstance(exc, exceptions.UnsupportedMediaType):
        return Response(_body("VALIDATION_ERROR", "Send the request body as JSON."), status=415)
    if isinstance(exc, exceptions.NotFound | Http404):
        return Response(_body("NOT_FOUND", "Not found."), status=404)
    if isinstance(exc, exceptions.APIException):
        return Response(_body("REQUEST_ERROR", str(exc.detail)), status=exc.status_code)
    logger.exception("unhandled error in %s", context.get("view"))
    return Response(_body(ApiError.code, ApiError.default_message), status=500)
