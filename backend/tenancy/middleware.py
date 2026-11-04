from django.conf import settings
from django.http import JsonResponse

from tenancy.context import use_tenant
from tenancy.models import Tenant


def tenant_slug_from_host(host: str, base_domain: str) -> str | None:
    """apurvam.myerp.in -> "apurvam"; myerp.in or a.b.myerp.in -> None."""
    host = host.split(":", 1)[0].lower()
    suffix = "." + base_domain.lower()
    if not host.endswith(suffix):
        return None
    slug = host[: -len(suffix)]
    if not slug or "." in slug:
        return None
    return slug


class TenantMiddleware:
    """Selects the tenant from the subdomain for the whole request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(settings.MYERP_TENANT_EXEMPT_PATHS):
            return self.get_response(request)

        slug = tenant_slug_from_host(request.get_host(), settings.MYERP_BASE_DOMAIN)
        tenant = (
            Tenant.objects.filter(slug=slug, status=Tenant.Status.ACTIVE).first() if slug else None
        )
        if tenant is None:
            return JsonResponse({"detail": "Unknown or inactive tenant."}, status=404)

        request.tenant = tenant
        with use_tenant(tenant):
            return self.get_response(request)
