"""Runtime registry of tenant database connections.

Django's DATABASES only lists the platform database. Each tenant's database is
added the first time that tenant is used, by copying the platform connection
settings and swapping in the tenant's database name (and host/port if the
tenant has been moved to its own server).
"""

from __future__ import annotations

import copy
import threading
from typing import TYPE_CHECKING

from django.db import connections

if TYPE_CHECKING:
    from tenancy.models import Tenant

_lock = threading.Lock()


def tenant_database_settings(tenant: Tenant) -> dict:
    config = copy.deepcopy(connections.settings["default"])
    config["NAME"] = tenant.db_name
    if tenant.db_host:
        config["HOST"] = tenant.db_host
    if tenant.db_port:
        config["PORT"] = str(tenant.db_port)
    return config


def register_tenant_database(tenant: Tenant) -> str:
    """Make `tenant.db_alias` usable with Django's connections. Idempotent."""
    alias = tenant.db_alias
    wanted = tenant_database_settings(tenant)
    with _lock:
        existing = connections.settings.get(alias)
        if existing is None or existing["NAME"] != wanted["NAME"]:
            if existing is not None:
                connections[alias].close()
            connections.settings[alias] = wanted
    return alias


def forget_tenant_database(tenant: Tenant) -> None:
    alias = tenant.db_alias
    with _lock:
        if alias in connections.settings:
            connections[alias].close()
            del connections.settings[alias]
            if hasattr(connections._connections, alias):
                delattr(connections._connections, alias)
