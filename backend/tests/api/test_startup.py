import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from pytest_django import Settings

from api.apps import ApiConfig

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _api_config() -> ApiConfig:
    config = apps.get_app_config("api")
    assert isinstance(config, ApiConfig)
    return config


def test_valid_rules_are_loaded_at_startup() -> None:
    assert _api_config().rules.version == 1


def test_invalid_rules_aborts_startup(settings: Settings, tmp_path: Path) -> None:
    bad = tmp_path / "rules.yaml"
    bad.write_text("version: 1\n")
    settings.RULES_PATH = bad
    with pytest.raises(ImproperlyConfigured, match="thresholds"):
        _api_config().ready()


def test_manage_check_fails_with_a_readable_error(tmp_path: Path) -> None:
    bad = tmp_path / "rules.yaml"
    bad.write_text("version: 1\n")
    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DEBUG": "True", "RULES_PATH": str(bad)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Invalid rules.yaml" in result.stderr
    assert "thresholds" in result.stderr
