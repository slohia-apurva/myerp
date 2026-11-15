"""What a document posted: its GL entries and stock moves, for the
"Postings" panel of a submitted entry."""

from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import VIEW, Signed, _check
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
