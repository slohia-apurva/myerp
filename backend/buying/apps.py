from django.apps import AppConfig


class BuyingConfig(AppConfig):
    name = "buying"
    verbose_name = "Purchase: orders, goods receipts, purchase invoices"

    def ready(self):
        from buying import attachments, locks, reset  # noqa: F401  (register hooks)
