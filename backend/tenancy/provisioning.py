"""Creating, migrating and dropping tenant databases."""

from __future__ import annotations

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from psycopg import sql

from tenancy.context import use_tenant
from tenancy.db import forget_tenant_database
from tenancy.models import Tenant
from tenancy.reader import grant_reader
from tenancy.router import PLATFORM_ALIAS


def default_db_name(slug: str) -> str:
    return settings.MYERP_TENANT_DB_PREFIX + slug.replace("-", "_")


def _execute_on_platform_server(statement: sql.Composed) -> None:
    # CREATE/DROP DATABASE cannot run inside a transaction; the platform
    # connection is in autocommit mode outside atomic blocks.
    with connections[PLATFORM_ALIAS].cursor() as cursor:
        cursor.execute(statement.as_string(connections[PLATFORM_ALIAS].connection))


def migrate_tenant(tenant: Tenant, verbosity: int = 0) -> None:
    with use_tenant(tenant):
        call_command("migrate", database=tenant.db_alias, interactive=False, verbosity=verbosity)
        grant_reader(tenant.db_alias)


def create_tenant(slug: str, name: str, db_name: str | None = None) -> Tenant:
    """Create the tenant record, its empty database, and run all tenant migrations."""
    tenant = Tenant(slug=slug, name=name, db_name=db_name or default_db_name(slug))
    tenant.full_clean()
    _execute_on_platform_server(
        sql.SQL("CREATE DATABASE {}").format(sql.Identifier(tenant.db_name))
    )
    try:
        tenant.save()
        migrate_tenant(tenant)
    except Exception:
        drop_tenant_database(tenant)
        if tenant.pk:
            tenant.delete()
        raise
    return tenant


def drop_tenant_database(tenant: Tenant) -> None:
    """Irreversible. Used for tests and failed provisioning only."""
    forget_tenant_database(tenant)
    _execute_on_platform_server(
        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(tenant.db_name))
    )
