from django.conf import settings
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.errors import message_error
from providers.factory import routing_provider

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
