"""Places as tenants see them: countries and PIN codes, kept centrally in the
platform database (read-only here). A PIN lookup gives the city, the state and
the couriers that deliver there, to fill a party's address as it is typed."""

import re

from django.db.models import Q
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import VIEW, Signed, _check
from tenancy.models import Country, PinCode


class CountryListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        rows = Country.objects.filter(is_active=True)
        return Response([{"code": c.code, "name": c.name} for c in rows])


PICK_LIMIT = 30
LIST_LIMIT = 500


class PinCodeListView(APIView):
    """GET ?q=text&limit=pick: PIN codes to search (a PIN's first digits, or words of the
    city or state), 30 rows for the picker, else 500; &pin=, &city= and &state= narrow the list
    by its columns."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        pick = request.query_params.get("limit") == "pick"
        rows = PinCode.objects.select_related("state")
        if pick or request.query_params.get("active") == "1":
            rows = rows.filter(is_active=True)
        q = request.query_params.get("q", "").strip()
        if q.replace(" ", "").isdigit():
            rows = rows.filter(pin__startswith=q.replace(" ", ""))
        else:
            for word in q.split():
                rows = rows.filter(Q(city__icontains=word) | Q(state__name__icontains=word))
        # The search box under each column of the list (Sidharth, 2026-11-15).
        pin = request.query_params.get("pin", "").replace(" ", "")
        if pin:
            rows = rows.filter(pin__startswith=pin)
        for word in request.query_params.get("city", "").split():
            rows = rows.filter(city__icontains=word)
        for word in request.query_params.get("state", "").split():
            rows = rows.filter(state__name__icontains=word)
        return Response(
            {
                "total": PinCode.objects.count(),
                "results": [
                    {
                        "id": p.pk,
                        "pin": p.pin,
                        "city": p.city,
                        "state_code": p.state.code if p.state else "",
                        "state_name": p.state.name if p.state else "",
                        "is_active": p.is_active,
                    }
                    for p in rows.order_by("pin")[: PICK_LIMIT if pick else LIST_LIMIT]
                ],
            }
        )


class PinView(APIView):
    permission_classes = [Signed]

    def get(self, request, pin: str):
        _check(request, VIEW)
        row = None
        if re.fullmatch(r"[1-9][0-9]{5}", pin):
            row = PinCode.objects.select_related("state").filter(pin=pin, is_active=True).first()
        if row is None:
            raise NotFound("This PIN code is not in the list.")
        return Response(
            {
                "pin": row.pin,
                "city": row.city,
                "state_code": row.state.code if row.state else "",
                "state_name": row.state.name if row.state else "",
                "couriers": [
                    {"courier": c.carrier.name, "oda": c.oda}
                    for c in row.couriers.select_related("carrier").order_by("carrier__name")
                ],
            }
        )
