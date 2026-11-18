from django.apps import AppConfig


class InsuranceConfig(AppConfig):
    name = "insurance"
    verbose_name = "Insurance policies"

    def ready(self):
        from insurance import api, locks  # noqa: F401  (register import/export and lock hooks)
