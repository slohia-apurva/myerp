from django.apps import AppConfig


class ManufacturingConfig(AppConfig):
    name = "manufacturing"
    verbose_name = "Production: bills of materials"

    def ready(self):
        from manufacturing import attachments, boms, locks, reset  # noqa: F401  (register hooks)
