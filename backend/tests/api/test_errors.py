"""Every failure uses one body shape and the agreed codes (plan.md section 7.6)."""

from typing import Any

import pytest
from django.http import Http404
from django.urls import path
from rest_framework import exceptions, serializers
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient

from api.errors import (
    NoRouteFound,
    OutOfCoverage,
    ProviderDown,
    TripExpired,
    message_error,
)
from providers.base import NoRoute, ProviderError, ProviderUnavailable

LOAD_MESSAGE = "Load must be between 1,000 and 80,000 lb."


class Body(serializers.Serializer[Any]):
    name = serializers.CharField()
    age = serializers.IntegerField(min_value=0)


def raises(exc: Exception) -> Any:
    @api_view(["GET"])
    def view(request: Request) -> Response:
        raise exc

    return view


@api_view(["POST"])
def needs_body(request: Request) -> Response:
    serializer = Body(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response({})


@api_view(["GET"])
def post_only_target(request: Request) -> Response:
    return Response({})


urlpatterns = [
    path("out-of-coverage", raises(OutOfCoverage())),
    path("no-route", raises(NoRouteFound())),
    path("provider-down", raises(ProviderDown())),
    path("expired", raises(TripExpired())),
    path("provider-no-route", raises(NoRoute("x"))),
    path("provider-unavailable", raises(ProviderUnavailable("secret details"))),
    path("provider-error", raises(ProviderError("bad provider request"))),
    path("throttled", raises(exceptions.Throttled(wait=30))),
    path("not-found", raises(Http404())),
    path(
        "custom-message",
        raises(message_error("load_lb", "Load must be between 1,000 and 80,000 lb.")),
    ),
    path("boom", raises(RuntimeError("database password is hunter2"))),
    path("body", needs_body),
    path("get-only", post_only_target),
]

pytestmark = pytest.mark.urls("tests.api.test_errors")


def get(url: str) -> Any:
    return APIClient().get(url)


@pytest.mark.parametrize(
    ("url", "status", "code", "message"),
    [
        (
            "/out-of-coverage",
            422,
            "OUT_OF_COVERAGE",
            "Currently supports routes within the continental US.",
        ),
        (
            "/no-route",
            422,
            "NO_ROUTE",
            "No truck route found between these places. Try a nearby city.",
        ),
        (
            "/provider-no-route",
            422,
            "NO_ROUTE",
            "No truck route found between these places. Try a nearby city.",
        ),
        (
            "/provider-down",
            503,
            "PROVIDER_UNAVAILABLE",
            "Weather/route data is temporarily unavailable, try again in a minute.",
        ),
        (
            "/provider-unavailable",
            503,
            "PROVIDER_UNAVAILABLE",
            "Weather/route data is temporarily unavailable, try again in a minute.",
        ),
        (
            "/provider-error",
            503,
            "PROVIDER_UNAVAILABLE",
            "Weather/route data is temporarily unavailable, try again in a minute.",
        ),
        ("/expired", 410, "TRIP_EXPIRED", "This trip has expired. Searching again."),
        ("/throttled", 429, "RATE_LIMITED", "Too many searches; please wait a few minutes."),
        ("/not-found", 404, "NOT_FOUND", "Not found."),
    ],
)
def test_each_error_has_its_status_code_and_plain_language_message(
    url: str, status: int, code: str, message: str
) -> None:
    response = get(url)
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}


def test_rate_limit_responses_say_when_to_retry() -> None:
    assert get("/throttled")["Retry-After"] == "31"


def test_internal_details_are_never_leaked() -> None:
    response = get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in str(body)
    assert "secret details" not in str(get("/provider-unavailable").json())


def test_hand_written_validation_messages_are_shown_as_written() -> None:
    response = get("/custom-message")
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": LOAD_MESSAGE,
            "fields": {"load_lb": LOAD_MESSAGE},
        }
    }


def test_stock_field_errors_name_the_field() -> None:
    response = APIClient().post("/body", {"age": -1}, format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["fields"]["name"] == "name: This field is required."
    assert error["fields"]["age"].startswith("age: Ensure this value is greater than or equal to 0")
    assert error["message"] in error["fields"].values()


def test_malformed_json_is_a_validation_error() -> None:
    response = APIClient().post("/body", "{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_wrong_method_has_a_code_too() -> None:
    response = APIClient().post("/get-only")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
