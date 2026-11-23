"""Django settings. Everything environment-specific comes from env vars."""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from providers.mode import validate_providers_mode

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


DEBUG = _env_bool("DEBUG", False)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("SECRET_KEY must be set when DEBUG is off.")
    SECRET_KEY = "dev-only-insecure-key"  # noqa: S105 - only reachable with DEBUG=True

ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# TomTom routing and search. The key stays server-side; the browser never sees it.
TOMTOM_API_KEY = os.environ.get("TOM_TOM_API_KEY", "")

# `live` (real services) or `fixtures` (recorded data; tests only, refused when DEBUG is off).
PROVIDERS_MODE = validate_providers_mode(os.environ.get("PROVIDERS_MODE", "live"), debug=DEBUG)

# Git commit of the running build; reported by /api/v1/health.
GIT_SHA = os.environ.get("GIT_SHA", "dev")

# Thresholds and tunables; validated at startup (see api/apps.py).
RULES_PATH = Path(os.environ.get("RULES_PATH", BASE_DIR / "rules.yaml"))

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "api",
    "places",
    "providers",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# Only needed for the Swagger UI page at /api/docs/.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


def _database_from_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError(f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }


_database_url = os.environ.get("DATABASE_URL", "")
DATABASES = {
    "default": _database_from_url(_database_url)
    if _database_url
    else {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
}

# Database-backed cache (Postgres); moving to Redis later is a settings change.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "api.errors.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Per client IP, counted in the Django cache (plan.md section 5.6).
    "DEFAULT_THROTTLE_RATES": {"places": "300/hour", "routes": "30/hour", "risk": "60/hour"},
    # How many proxies sit in front of Django. 0 = trust only the socket address (dev, CI).
    # In production the real client IP comes via X-Forwarded-For; see docs/phase notes (Phase 8).
    "NUM_PROXIES": int(os.environ.get("NUM_PROXIES", "0")),
}

USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

SPECTACULAR_SETTINGS = {
    "TITLE": "Weather-Aware Truck Routing API",
    "DESCRIPTION": (
        "Two-step API: `POST /routes` returns real truck routes with realistic ETAs (draw them "
        "straight away); `POST /risk` returns weather risk at every checkpoint, the recommendation "
        "and a 48-hour heatmap. Errors always use "
        '`{"error": {"code", "message"}}`.'
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}
