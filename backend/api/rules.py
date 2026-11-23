from django.apps import apps

from api.apps import ApiConfig
from core.rules import Rules


def get_rules() -> Rules:
    """The validated rules.yaml loaded at startup."""
    config = apps.get_app_config("api")
    assert isinstance(config, ApiConfig)
    return config.rules
