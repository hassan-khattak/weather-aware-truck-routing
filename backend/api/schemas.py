"""Documentation-only serializers describing request and response bodies for the OpenAPI schema.

The real responses are built by trips/payload.py and trips/risk_payload.py; these classes mirror
those shapes so /api/docs/ shows them (plan.md section 7).
"""

from rest_framework import serializers

LEVELS = ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL", "NO_FORECAST"]


class ErrorBody(serializers.Serializer[dict[str, object]]):
    code = serializers.ChoiceField(
        choices=[
            "VALIDATION_ERROR",
            "OUT_OF_COVERAGE",
            "NO_ROUTE",
            "PROVIDER_UNAVAILABLE",
            "RATE_LIMITED",
            "TRIP_EXPIRED",
            "NOT_FOUND",
            "METHOD_NOT_ALLOWED",
            "INTERNAL_ERROR",
        ]
    )
    message = serializers.CharField(help_text="Plain-language message with a next step.")
    fields = serializers.DictField(  # type: ignore[assignment]
        child=serializers.CharField(),
        required=False,
        help_text="Per-field messages (VALIDATION_ERROR only).",
    )


class ErrorResponse(serializers.Serializer[dict[str, object]]):
    error = ErrorBody()


class HealthResponse(serializers.Serializer[dict[str, str]]):
    status = serializers.CharField(help_text="Always `ok`.")
    version = serializers.CharField(help_text="Git commit of the running build.")


class PlaceOut(serializers.Serializer[dict[str, object]]):
    label = serializers.CharField(help_text="e.g. `Dallas, TX`")  # type: ignore[assignment]
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    tz = serializers.CharField(
        allow_null=True,
        help_text="IANA time zone, e.g. `America/Chicago`; null outside the continental US",
    )


class DepartureOut(serializers.Serializer[dict[str, str]]):
    utc = serializers.CharField(help_text="UTC instant, e.g. `2026-11-24T21:00:00Z`")
    tz = serializers.CharField(help_text="IANA zone of the origin, e.g. `America/Chicago`")
    local = serializers.CharField(help_text="Wall-clock time at the origin, `2026-11-24T15:00`")


class StopOut(serializers.Serializer[dict[str, object]]):
    type = serializers.ChoiceField(choices=["break", "rest"])
    mile = serializers.FloatField()
    start_utc = serializers.CharField()
    duration_s = serializers.IntegerField()


class RouteOut(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField(help_text="`A`, `B` or `C`")
    order = serializers.IntegerField()
    source = serializers.ChoiceField(choices=["api", "generated"])  # type: ignore[assignment]
    distance_mi = serializers.FloatField()
    drive_s = serializers.IntegerField(help_text="Driving time without required stops")
    total_s = serializers.IntegerField(help_text="Total time including required stops")
    geometry = serializers.CharField(help_text="Encoded polyline (precision 5), simplified")
    stops = StopOut(many=True)
    timeline = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()),
        help_text="`[elapsed_s, mile]` pairs; the mile stays flat while the truck is parked",
    )
    long_range_forecast = serializers.BooleanField()


class RoutesResponse(serializers.Serializer[dict[str, object]]):
    trip_id = serializers.CharField(help_text="Pass to `POST /risk` within an hour")
    departure = DepartureOut()
    interval_mi = serializers.FloatField(help_text="Checkpoint spacing: 10, 25 or 50 miles")
    routes = RouteOut(many=True)
    notes = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())


class CheckpointOut(serializers.Serializer[dict[str, object]]):
    idx = serializers.IntegerField()
    mile = serializers.FloatField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    eta_utc = serializers.CharField()
    tz = serializers.CharField()
    road = serializers.CharField(allow_null=True)
    town = serializers.CharField(allow_null=True)
    town_dist_mi = serializers.FloatField(allow_null=True)
    town_dir = serializers.CharField(allow_null=True, help_text="Compass direction from the town")
    wind_mph = serializers.FloatField(allow_null=True)
    gust_mph = serializers.FloatField(allow_null=True)
    rain_in_hr = serializers.FloatField(allow_null=True)
    snow_in_hr = serializers.FloatField(allow_null=True)
    level = serializers.ChoiceField(choices=LEVELS)
    reasons = serializers.ListField(child=serializers.CharField())
    forecast = serializers.BooleanField(help_text="False when there is no forecast for the ETA")


class SegmentOut(serializers.Serializer[dict[str, object]]):
    from_mi = serializers.FloatField()
    to_mi = serializers.FloatField()
    level = serializers.ChoiceField(choices=LEVELS)


class SummaryOut(serializers.Serializer[dict[str, object]]):
    miles = serializers.DictField(
        child=serializers.FloatField(), help_text="Miles per level, including NO_FORECAST"
    )
    avg_risk = serializers.FloatField(allow_null=True, help_text="Mile-weighted, 0 (Low) to 4")


class RouteRiskOut(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    checkpoints = CheckpointOut(many=True)
    segments = SegmentOut(many=True)
    summary = SummaryOut()


class RecommendationOut(serializers.Serializer[dict[str, object]]):
    route_id = serializers.CharField()
    ranking = serializers.ListField(child=serializers.CharField())
    reason = serializers.CharField(help_text="e.g. `0 Severe mi vs 25 on Route A; +18 min`")
    all_unsafe = serializers.BooleanField()
    all_clear = serializers.BooleanField()


class HeatmapOut(serializers.Serializer[dict[str, object]]):
    grid_deg = serializers.FloatField(help_text="Cell size: 0.2, 0.4 or 0.8 degrees by trip length")
    start_utc = serializers.CharField(help_text="Hour 0 = the departure time")
    hours = serializers.IntegerField(help_text="49 (hours 0 to 48)")
    cells = serializers.CharField(help_text="Base64 little-endian float32 [lat, lon, ...]")
    layers = serializers.DictField(
        child=serializers.CharField(),
        help_text=(
            "Base64 little-endian arrays, hour-major (`index = hour * cells + cell`): "
            "`risk` uint8 level 0-4, `wind` uint8 mph (255 = no data), "
            "`rain` and `snow` uint16 hundredths of in/hr (65535 = no data)"
        ),
    )


class RiskResponse(serializers.Serializer[dict[str, object]]):
    routes = RouteRiskOut(many=True)
    recommendation = RecommendationOut()
    heatmap = HeatmapOut()
    weather_as_of = serializers.CharField(allow_null=True)
    stale = serializers.BooleanField(help_text="True when cached weather was used after a failure")
