"""OpenAPI schema and Swagger UI (plan.md section 7.5)."""

from pathlib import Path
from typing import Any

import yaml
from django.core.management import call_command
from rest_framework.test import APIClient


def schema() -> dict[str, Any]:
    response = APIClient().get("/api/schema/", {"format": "json"})
    assert response.status_code == 200
    data: dict[str, Any] = response.json()
    return data


def test_the_schema_lists_all_four_endpoints() -> None:
    paths = schema()["paths"]
    assert set(paths) == {
        "/api/v1/health",
        "/api/v1/places",
        "/api/v1/routes",
        "/api/v1/risk",
    }
    assert "get" in paths["/api/v1/places"]
    assert "post" in paths["/api/v1/routes"]
    assert "post" in paths["/api/v1/risk"]


def test_responses_document_the_error_format_and_status_codes() -> None:
    paths = schema()["paths"]
    assert set(paths["/api/v1/routes"]["post"]["responses"]) == {"200", "400", "422", "429", "503"}
    assert set(paths["/api/v1/risk"]["post"]["responses"]) == {"200", "400", "410", "429", "503"}
    # The error code list is documented as an enum component.
    enums = [
        spec["enum"]
        for spec in schema()["components"]["schemas"].values()
        if isinstance(spec, dict) and "enum" in spec
    ]
    documented = {code for values in enums for code in values}
    assert {"VALIDATION_ERROR", "OUT_OF_COVERAGE", "NO_ROUTE", "PROVIDER_UNAVAILABLE"} <= documented
    assert {"RATE_LIMITED", "TRIP_EXPIRED"} <= documented


def test_request_and_response_bodies_are_described() -> None:
    document = schema()
    components = document["components"]["schemas"]

    def body_ref(path: str) -> str:
        content = document["paths"][path]["post"]["requestBody"]["content"]["application/json"]
        return str(content["schema"]["$ref"]).rsplit("/", 1)[-1]

    routes_request = components[body_ref("/api/v1/routes")]
    assert {"origin", "destination", "departure_local", "load_lb"} <= set(
        routes_request["properties"]
    )
    risk_request = components[body_ref("/api/v1/risk")]
    assert "trip_id" in risk_request["properties"]
    assert {"trip_id", "departure", "interval_mi", "routes", "notes", "warnings"} <= set(
        components["RoutesResponse"]["properties"]
    )
    assert {"routes", "recommendation", "heatmap", "weather_as_of", "stale"} <= set(
        components["RiskResponse"]["properties"]
    )
    assert "layers" in components["HeatmapOut"]["properties"]


def test_the_schema_is_valid_openapi_without_warnings(tmp_path: Path) -> None:
    target = tmp_path / "schema.yml"
    call_command("spectacular", "--validate", "--fail-on-warn", file=str(target))
    assert yaml.safe_load(target.read_text())["openapi"].startswith("3.")


def test_swagger_ui_is_served() -> None:
    response = APIClient().get("/api/docs/")
    assert response.status_code == 200
    assert b"swagger" in response.content.lower()
