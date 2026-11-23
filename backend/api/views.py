from django.conf import settings
from django.core.cache import cache
from rest_framework import serializers
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import clock
from api.errors import TripExpired, message_error
from api.rules import get_rules
from api.validation import parse_routes_request
from providers.factory import routing_provider, weather_provider
from trips.payload import routes_payload
from trips.planner import plan_trip
from trips.risk import assess
from trips.risk_payload import risk_payload
from trips.store import load_trip, save_trip
from weather_grid.service import WeatherGridService

PLACES_MIN_CHARS = 3
PLACES_LIMIT = 6


@api_view(["GET"])
@throttle_classes([])
def health(request: Request) -> Response:
    """Liveness probe. Makes no database or external calls."""
    return Response({"status": "ok", "version": settings.GIT_SHA})


class PlacesView(APIView):
    """GET /places?q=<text>: US place autocomplete (cities, addresses, ZIP codes)."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "places"

    def get(self, request: Request) -> Response:
        query = " ".join(request.query_params.get("q", "").split())
        if len(query) < PLACES_MIN_CHARS:
            raise message_error("q", f"Type at least {PLACES_MIN_CHARS} characters to search.")
        places = routing_provider().search(query, PLACES_LIMIT)
        return Response([{"label": p.label, "lat": p.lat, "lon": p.lon} for p in places])


class RoutesView(APIView):
    """POST /routes: real truck routes with ETAs. The map draws them straight away."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "routes"

    def post(self, request: Request) -> Response:
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

    def post(self, request: Request) -> Response:
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
        return Response(risk_payload(assess(trip, weather, rules)))
