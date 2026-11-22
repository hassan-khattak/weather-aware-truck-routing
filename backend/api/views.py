from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
def health(request: Request) -> Response:
    """Liveness probe. Makes no database or external calls."""
    return Response({"status": "ok", "version": settings.GIT_SHA})
