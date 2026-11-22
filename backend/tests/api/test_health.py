import pytest
from pytest_django import Settings
from rest_framework.test import APIClient


def test_health_returns_ok_and_version(settings: Settings) -> None:
    settings.GIT_SHA = "abc123"
    response = APIClient().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "abc123"}


def test_health_makes_no_db_or_external_calls() -> None:
    # No `db` fixture: pytest-django raises if the view touches the database.
    assert APIClient().get("/api/v1/health").status_code == 200


def test_health_rejects_non_get() -> None:
    assert APIClient().post("/api/v1/health").status_code == 405


@pytest.mark.parametrize("path", ["/api/v1/health/", "/health"])
def test_other_paths_are_404(path: str) -> None:
    assert APIClient().get(path).status_code == 404
