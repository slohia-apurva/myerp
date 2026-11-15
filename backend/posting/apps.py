from django.apps import AppConfig


class PostingConfig(AppConfig):
    name = "posting"
    verbose_name = "Posting: the GL and the stock ledger"

    def ready(self):
        from posting import locks, reset  # noqa: F401  (register lock and reset hooks)
