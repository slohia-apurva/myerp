from django.apps import AppConfig


class SellingConfig(AppConfig):
    name = "selling"
    verbose_name = "Sales: orders"

    def ready(self):
        from selling import attachments, locks, reset  # noqa: F401  (register hooks)
