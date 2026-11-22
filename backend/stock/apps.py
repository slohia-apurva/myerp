from django.apps import AppConfig


class StockConfig(AppConfig):
    name = "stock"
    verbose_name = "Stock: entries"

    def ready(self):
        from stock import attachments, locks, reset  # noqa: F401  (register hooks)
