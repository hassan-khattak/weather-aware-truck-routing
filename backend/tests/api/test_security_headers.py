"""Hardening headers on API responses (plan.md section 14, security)."""

from rest_framework.test import APIClient


def test_api_responses_carry_the_basic_security_headers() -> None:
    response = APIClient().get("/api/v1/health")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


def test_error_responses_carry_them_too_and_never_leak_internals() -> None:
    response = APIClient().post("/api/v1/routes", "{bad json", content_type="application/json")
    assert response.status_code == 400
    assert response["X-Content-Type-Options"] == "nosniff"
    body = response.content.decode()
    assert "Traceback" not in body
    assert "settings" not in body.lower()
