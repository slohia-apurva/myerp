"""GST rates as tenants see them: a central list kept by MyERP in the platform
database (like HSN codes), read-only here. An item's dated rate history picks
its rates from this list."""

from decimal import Decimal

from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import VIEW, Signed, _check
from core.tds_sections import current_sections, label
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
    """A new or changed row of an item's rate history must use a rate from the
    central list. A disabled rate (12% and 28% after September 2025) is taken
    only as history: on a row followed by a later row with an active rate, as
    an ERPNext item's "12%, then 5% from 22-09-2025" (Sidharth, 2026-11-23).
    A row the item already had stays as it is, even if the rate has since been
    disabled. `new` is sorted by date."""
    from rest_framework.exceptions import ValidationError

    rows = dict(GstRate.objects.values_list("rate", "is_active"))
    active = {rate for rate, on in rows.items() if on}
    for i, r in enumerate(new):
        if (r["valid_from"], r["rate"]) in kept:
            continue
        rate = Decimal(r["rate"])
        later_active = any(Decimal(x["rate"]) in active for x in new[i + 1 :])
        if rate not in active and not (rate in rows and later_active):
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
                    "new_code": s.new_code,
                    "label": label(s),
                    "for_goods": s.for_goods,
                }
                for s in current_sections()
            ]
        )
