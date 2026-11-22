from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from core.rules import Rules, RulesError, load_rules


class ApiConfig(AppConfig):
    name = "api"
    rules: Rules

    def ready(self) -> None:
        """Validate rules.yaml once at startup; an invalid file stops the app."""
        try:
            self.rules = load_rules(settings.RULES_PATH)
        except RulesError as error:
            raise ImproperlyConfigured(str(error)) from error
