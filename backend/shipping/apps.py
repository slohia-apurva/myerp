from django.apps import AppConfig


class ShippingConfig(AppConfig):
    name = "shipping"
    verbose_name = "Shipments and courier tracking"

    def ready(self):
        from shipping import locks, reset  # noqa: F401  (register lock and reset hooks)
