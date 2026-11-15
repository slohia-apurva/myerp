"""What a document posted: its GL entries and stock moves, for the
"Postings" panel of a submitted entry."""

from django.db.models import Sum
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import VIEW, Signed, _check
from core.companies import visible_companies
from core.models import Package, WarehouseLocation
from posting.models import GLEntry, StockMove


class PostingsView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        kind = request.query_params.get("voucher_type", "")
        try:
            pk = int(request.query_params.get("voucher_id", ""))
        except ValueError:
            return Response({"gl": [], "stock": []})
        gl = GLEntry.objects.filter(voucher_type=kind, voucher_id=pk).select_related("ledger")
        stock = StockMove.objects.filter(voucher_type=kind, voucher_id=pk).select_related(
            "item", "location__parent", "batch"
        )
        return Response(
            {
                "gl": [
                    {
                        "date": e.date,
                        "ledger": e.ledger_id,
                        "ledger_name": e.ledger.name,
                        "debit": e.debit,
                        "credit": e.credit,
                        "is_reversal": e.is_reversal,
                    }
                    for e in gl
                ],
                "stock": [
                    {
                        "date": m.date,
                        "item_number": m.item.item_number,
                        "item_name": m.item.name,
                        "location": str(m.location),
                        "batch": m.batch.number if m.batch_id else "",
                        "qty": m.qty,
                        "rate": m.rate,
                        "value": m.value,
                        "is_reversal": m.is_reversal,
                    }
                    for m in stock
                ],
            }
        )


class BinContentsView(APIView):
    """What is in a bin, rack or area now: each item and batch with its quantity, and
    the bags or boxes kept there. Opened by scanning the QR code on a bin label
    (Sidharth, 2026-11-15)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        place = (
            WarehouseLocation.objects.filter(
                pk=pk, branch__company__in=visible_companies(request.user)
            )
            .select_related("branch__company", "parent")
            .first()
        )
        if place is None:
            raise NotFound("No such bin.")
        places = [place, *place.children.all()]  # a rack shows its bins
        stock = (
            StockMove.objects.filter(location__in=places)
            .values(
                "location",
                "item",
                "item__name",
                "item__item_number",
                "item__stock_unit__short_name",
                "batch",
                "batch__number",
                "batch__expiry_date",
                "batch__status",
            )
            .annotate(qty=Sum("qty"))
            .exclude(qty=0)
            .order_by("item__name", "batch__number")
        )
        names = {p.pk: str(p) for p in places}
        bags = Package.objects.filter(
            location__in=places, status__in=(Package.IN_STOCK, Package.PART_USED)
        ).select_related("item", "batch", "item__stock_unit")
        return Response(
            {
                "id": place.pk,
                "code": f"LOC-{place.pk:06d}",
                "name": str(place),
                "kind": place.kind,
                "kind_label": place.get_kind_display(),
                "purpose_label": place.get_purpose_display() if place.purpose else "",
                "branch_name": place.branch.name,
                "company": place.branch.company_id,
                "company_name": place.branch.company.name,
                "stock": [
                    {
                        "location_name": names[s["location"]],
                        "item_name": s["item__name"],
                        "item_number": s["item__item_number"],
                        "batch": s["batch__number"] or "",
                        "expiry_date": s["batch__expiry_date"],
                        "batch_status": s["batch__status"] or "",
                        "qty": str(s["qty"]),
                        "unit_name": s["item__stock_unit__short_name"],
                    }
                    for s in stock
                ],
                "packages": [
                    {
                        "number": k.number,
                        "kind_label": k.get_kind_display(),
                        "location_name": names[k.location_id],
                        "item_name": k.item.name,
                        "batch": k.batch.number if k.batch_id else "",
                        "left_qty": str(k.left_qty),
                        "unit_name": k.item.stock_unit.short_name,
                        "status_label": k.get_status_display(),
                        "voucher_number": k.voucher_number,
                    }
                    for k in bags
                ],
            }
        )
