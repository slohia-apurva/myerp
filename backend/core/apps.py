from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Core (tenant database)"

    def ready(self):
        from core import duplicates

        duplicates.connect()
