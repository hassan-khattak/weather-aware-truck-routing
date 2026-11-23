from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import clock
from api.errors import TripExpired, message_error
from api.force_error import maybe_force_error
from api.rules import get_rules
from api.schemas import (
    ErrorResponse,
    HealthResponse,
    PlaceOut,
    RiskResponse,
    RoutesResponse,
)
from api.validation import RoutesRequestSerializer, parse_routes_request, zone_if_covered
from places.nearest import lookup_town
from providers.factory import routing_provider, weather_provider
from trips.payload import routes_payload
from trips.planner import plan_trip
from trips.risk import assess
from trips.risk_payload import risk_payload
from trips.store import load_trip, save_trip
from weather_grid.service import WeatherGridService

PLACES_MIN_CHARS = 3
PLACES_LIMIT = 6


@extend_schema(responses=HealthResponse, tags=["system"])
@api_view(["GET"])
@throttle_classes([])
def health(request: Request) -> Response:
    """Liveness probe. Makes no database or external calls."""
    return Response({"status": "ok", "version": settings.GIT_SHA})


class PlacesView(APIView):
    """GET /places?q=<text>: US place autocomplete (cities, addresses, ZIP codes)."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "places"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="At least 3 characters", required=True)],
        responses={
            200: PlaceOut(many=True),
            400: ErrorResponse,
            429: ErrorResponse,
            503: ErrorResponse,
        },
        tags=["search"],
    )
    def get(self, request: Request) -> Response:
        maybe_force_error(request)
        query = " ".join(request.query_params.get("q", "").split())
        if len(query) < PLACES_MIN_CHARS:
            raise message_error("q", f"Type at least {PLACES_MIN_CHARS} characters to search.")
        places = routing_provider().search(query, PLACES_LIMIT)
        # `tz` lets the form label the departure field with the origin's zone before searching.
        return Response(
            [
                {"label": p.label, "lat": p.lat, "lon": p.lon, "tz": zone_if_covered(p)}
                for p in places
            ]
        )


class RoutesView(APIView):
    """POST /routes: real truck routes with ETAs. The map draws them straight away."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "routes"

    @extend_schema(
        request=RoutesRequestSerializer,
        responses={
            200: RoutesResponse,
            400: ErrorResponse,
            422: ErrorResponse,
            429: ErrorResponse,
            503: ErrorResponse,
        },
        tags=["search"],
    )
    def post(self, request: Request) -> Response:
        maybe_force_error(request)
        rules = get_rules()
        now = clock.now()
        trip_request = parse_routes_request(request.data, now=now, rules=rules)
        trip = plan_trip(trip_request, routing_provider(), rules, now)
        return Response(routes_payload(trip, save_trip(trip), rules))


class RiskRequestSerializer(serializers.Serializer[dict[str, str]]):
    trip_id = serializers.CharField(max_length=64)


class RiskView(APIView):
    """POST /risk {trip_id}: checkpoints, risk, recommendation and the 48 h heatmap."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "risk"

    @extend_schema(
        request=RiskRequestSerializer,
        responses={
            200: RiskResponse,
            400: ErrorResponse,
            410: ErrorResponse,
            429: ErrorResponse,
            503: ErrorResponse,
        },
        tags=["search"],
    )
    def post(self, request: Request) -> Response:
        maybe_force_error(request)
        data = request.data
        if isinstance(data, dict) and set(data) - {"trip_id"}:
            raise message_error(sorted(set(data) - {"trip_id"})[0], "This field is not allowed.")
        serializer = RiskRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        trip = load_trip(serializer.validated_data["trip_id"])
        if trip is None:
            raise TripExpired  # the browser silently repeats step 1

        rules = get_rules()
        weather = WeatherGridService(weather_provider(), cache, rules, now=clock.now)
        return Response(risk_payload(assess(trip, weather, rules, town_lookup=lookup_town)))
