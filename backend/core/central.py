"""The central admin screen: the tables MyERP keeps once for every customer in
the platform database (HSN codes today; states, countries and PIN codes next),
and the list of customers (tenants). For platform admins only: the people whose
sign-in emails are in MYERP_PLATFORM_ADMINS. A customer's Owner is not one."""

from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import Signed
from tenancy.models import HsnCode, Tenant

# key, label, what it is for, model, screen to open (a hash route) or "".
CENTRAL_TABLES = [
    ("hsn", "HSN codes", "HSN and SAC codes searched on the item form.", HsnCode, "#/hsn"),
    (
        "tenants",
        "Customers (tenants)",
        "Each group of companies, with its own database.",
        Tenant,
        "",
    ),
]


def is_platform_admin(user) -> bool:
    emails = {e.strip().lower() for e in settings.MYERP_PLATFORM_ADMINS.split(",") if e.strip()}
    return bool(user and user.is_authenticated and user.email.lower() in emails)


class CentralView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        if not is_platform_admin(request.user):
            raise PermissionDenied("Only MyERP platform admins can open this.")
        return Response(
            {
                "tables": [
                    {
                        "key": k,
                        "label": label,
                        "about": about,
                        "count": model.objects.count(),
                        "open": link,
                    }
                    for k, label, about, model, link in CENTRAL_TABLES
                ],
                "tenants": [
                    {
                        "slug": t.slug,
                        "name": t.name,
                        "status": t.get_status_display(),
                        "created": t.created_at.date().isoformat(),
                    }
                    for t in Tenant.objects.all()
                ],
            }
        )
