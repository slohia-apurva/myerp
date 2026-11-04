"""Helpers for background jobs that run inside one tenant."""

import functools

from tenancy.context import use_tenant
from tenancy.models import Tenant


def tenant_task(func):
    """Wrap a Celery task body so its first argument is a tenant slug.

    The task then runs inside that tenant only:

        @shared_task
        @tenant_task
        def rebuild_stock(item_id): ...

        rebuild_stock.delay("apurvam", item_id)
    """

    @functools.wraps(func)
    def wrapper(tenant_slug: str, *args, **kwargs):
        tenant = Tenant.objects.get(slug=tenant_slug, status=Tenant.Status.ACTIVE)
        with use_tenant(tenant):
            return func(*args, **kwargs)

    return wrapper
