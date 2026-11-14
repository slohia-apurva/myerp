from django.apps import AppConfig


class BuyingConfig(AppConfig):
    name = "buying"
    verbose_name = "Purchase: orders, goods receipts, purchase invoices"

    def ready(self):
        from buying import locks, reset  # noqa: F401  (register lock and reset hooks)
