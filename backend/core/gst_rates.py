"""GST rates as tenants see them: a central list kept by MyERP in the platform
database (like HSN codes), read-only here. An item's dated rate history picks
its rates from this list."""

from decimal import Decimal

from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import VIEW, Signed, _check
from core.tds_sections import current_sections
from tenancy.models import GstRate


def rate_row(r: GstRate) -> dict:
    return {"id": r.pk, "rate": f"{r.rate:.2f}", "label": r.label, "is_active": r.is_active}


class GstRateListView(APIView):
    """GET: the active rates (the item form's dropdown)."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response([rate_row(r) for r in GstRate.objects.filter(is_active=True)])


def refuse_unlisted_rates(new: list[dict], kept: set[tuple]) -> None:
    """A new or changed row of an item's rate history must use an active rate
    from the central list. A row the item already had stays as it is, even if
    the rate has since been disabled."""
    from rest_framework.exceptions import ValidationError

    active = set(GstRate.objects.filter(is_active=True).values_list("rate", flat=True))
    for r in new:
        if (r["valid_from"], r["rate"]) in kept:
            continue
        if Decimal(r["rate"]) not in active:
            raise ValidationError(
                {
                    "gst_rates": [
                        f"{Decimal(r['rate']).normalize():f}% is not in the GST rates list."
                    ]
                }
            )


class TdsSectionListView(APIView):
    """GET: the TDS sections as in force today (core/tds_sections.py), for the
    pickers on suppliers, items, ledgers and bills."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(
            [
                {
                    "code": s.code,
                    "name": s.name,
                    "label": f"{s.code} {s.name}",
                    "for_goods": s.for_goods,
                }
                for s in current_sections()
            ]
        )
