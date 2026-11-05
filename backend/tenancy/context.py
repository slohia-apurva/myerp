"""The current tenant for this request, job or command.

Design rule 16: every request, job and file belongs to exactly one tenant and
opens only that tenant's database. Code never picks a database itself; it runs
inside `use_tenant(...)` and the database router does the rest.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenancy.models import Tenant

_current_tenant: ContextVar[Tenant | None] = ContextVar("myerp_current_tenant", default=None)


class NoTenantSelected(RuntimeError):
    """Tenant data was touched outside `use_tenant(...)`."""


def current_tenant() -> Tenant | None:
    return _current_tenant.get()


def require_tenant() -> Tenant:
    tenant = _current_tenant.get()
    if tenant is None:
        raise NoTenantSelected(
            "Tenant data accessed with no tenant selected. "
            "Wrap the code in tenancy.context.use_tenant(tenant)."
        )
    return tenant


@contextmanager
def use_tenant(tenant: Tenant) -> Iterator[Tenant]:
    from tenancy.db import register_tenant_database

    register_tenant_database(tenant)
    token = _current_tenant.set(tenant)
    try:
        yield tenant
    finally:
        _current_tenant.reset(token)


@contextmanager
def tenant_atomic() -> Iterator[None]:
    """A transaction on the current tenant's database.

    Use this instead of `django.db.transaction.atomic`, which with no `using`
    opens the transaction on the platform database: tenant writes inside it
    would not be atomic, and `select_for_update()` fails.
    Works as a decorator too (`@tenant_atomic()`).
    """
    from django.db import transaction

    with transaction.atomic(using=require_tenant().db_alias):
        yield
