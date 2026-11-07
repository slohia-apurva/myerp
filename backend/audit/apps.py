from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "audit"
    verbose_name = "Audit log (tenant database)"

    def ready(self):
        from audit import recorder

        recorder.connect()
