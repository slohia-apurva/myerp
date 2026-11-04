"""Sends platform models to the platform database and everything else to the
current tenant's database.

There is deliberately no fallback: tenant data read or written with no tenant
selected raises NoTenantSelected instead of silently using some database.
"""

from django.conf import settings

from tenancy.context import require_tenant

PLATFORM_APPS = frozenset({"tenancy"})
PLATFORM_ALIAS = "default"


def is_platform_app(app_label: str) -> bool:
    return app_label in PLATFORM_APPS


class TenantRouter:
    def _db_for(self, model) -> str:
        if is_platform_app(model._meta.app_label):
            return PLATFORM_ALIAS
        return require_tenant().db_alias

    def db_for_read(self, model, **hints):
        return self._db_for(model)

    def db_for_write(self, model, **hints):
        return self._db_for(model)

    def allow_relation(self, obj1, obj2, **hints):
        # Never relate a platform row to a tenant row.
        return is_platform_app(obj1._meta.app_label) == is_platform_app(obj2._meta.app_label)

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == PLATFORM_ALIAS:
            return is_platform_app(app_label)
        if db.startswith("tenant_") or db in getattr(settings, "MYERP_EXTRA_TENANT_ALIASES", ()):
            return not is_platform_app(app_label)
        return False
