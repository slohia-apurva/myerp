"""HSN / SAC codes as tenants see them: a central list kept by MyERP in the
platform database, searched as people type an item's HSN. Read-only here;
the list is loaded with `manage.py import_hsn` (tenancy/hsn_import.py)."""

from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import VIEW, Signed, _check
from tenancy.models import HsnCode

PICK_LIMIT = 30
LIST_LIMIT = 500


def search(q: str, active_only: bool, limit: int):
    rows = HsnCode.objects.all()
    if active_only:
        rows = rows.filter(is_active=True)
    q = q.strip()
    if q:
        if q.replace(" ", "").isdigit():
            rows = rows.filter(hsn_code__startswith=q.replace(" ", ""))
        else:
            for word in q.split():
                rows = rows.filter(Q(description__icontains=word) | Q(hsn_code__startswith=word))
    return rows.order_by("hsn_code")[:limit]


class HsnListView(APIView):
    """GET ?q=text&active=1&limit=pick (30 rows for the picker, else 500)."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        pick = request.query_params.get("limit") == "pick"
        rows = search(
            request.query_params.get("q", ""),
            request.query_params.get("active") == "1" or pick,
            PICK_LIMIT if pick else LIST_LIMIT,
        )
        return Response(
            {
                "total": HsnCode.objects.count(),
                "results": [
                    {
                        "id": h.pk,
                        "hsn_code": h.hsn_code,
                        "description": h.description,
                        "is_active": h.is_active,
                    }
                    for h in rows
                ],
            }
        )
