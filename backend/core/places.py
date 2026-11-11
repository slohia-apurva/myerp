"""Places as tenants see them: countries and PIN codes, kept centrally in the
platform database (read-only here). A PIN lookup gives the city, the state and
the couriers that deliver there, to fill a party's address as it is typed."""

import re

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
