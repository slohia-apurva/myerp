"""The words of the mails "Email Supplier" sends from a purchase order, taken
from the Mail Templates master (core/mail_templates.py; Sidharth 2026-11-27:
one "Email Supplier" button with a Template picker).

`offered` lists the templates that fit an order now; `chosen` picks the one
asked for (else the default of that use); `order_values` and `receipt_values`
fill the fields."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import SUBMIT, _check, _order
from buying.models import GoodsReceipt, PurchaseOrder
from core.api import Signed
from core.mail_templates import fill, templates_for
from core.models import MailTemplate


def _dmy(d) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def order_values(o: PurchaseOrder, contact: str = "") -> dict[str, str]:
    today = timezone.localdate()
    late = (today - o.expected_date).days if o.expected_date else 0
    return {
        "PO No": o.number or "",
        "PO Date": _dmy(o.order_date),
        "Supplier": o.supplier.name,
        "Contact Name": contact or "Sir/Madam",
        "Expected Delivery": _dmy(o.expected_date),
        "Days Late": str(max(late, 0)),
        "Our Company": o.company.name,
        "Purchaser": o.purchaser.name if o.purchaser_id else "",
        # Filled on the screen from the ticked lines.
        "Short or Excess": "{Short or Excess}",
    }


def receipt_values(r: GoodsReceipt | None) -> dict[str, str]:
    if r is None:
        return {"GRN No": "", "GRN Date": "", "Challan No": ""}
    return {"GRN No": r.number, "GRN Date": _dmy(r.receipt_date), "Challan No": r.challan_no}


def offered(o: PurchaseOrder) -> list[MailTemplate]:
    """The active templates that fit the order as it stands, by use."""
    from buying.po_reminder import pending_lines
    from buying.supplier_mail import differing_lines

    if not o.number or o.status == PurchaseOrder.CANCELLED:
        return []
    uses = [MailTemplate.PURCHASE_ORDER]
    if differing_lines(o) and o.receipts.filter(status=GoodsReceipt.SUBMITTED).exists():
        uses.append(MailTemplate.SHORT_EXCESS)
    if o.status in PurchaseOrder.OPEN and pending_lines(o):
        uses.append(MailTemplate.REMINDER)
    return [t for use in uses for t in templates_for(use)]


def chosen(request, used_for: str) -> MailTemplate | None:
    """?template=ID (or "template" in a POST), which must be an active template
    of this use; else the use's default; None when the group has none."""
    raw = request.query_params.get("template") or (
        request.data.get("template") if hasattr(request.data, "get") else None
    )
    if raw:
        t = MailTemplate.objects.filter(pk=raw, used_for=used_for, is_active=True).first()
        if t is None:
            raise ValidationError({"template": ["That mail template cannot be used here."]})
        return t
    found = templates_for(used_for)
    return found[0] if found else None


def words(t: MailTemplate, values: dict[str, str]) -> dict[str, str]:
    return {
        "subject": fill(t.subject, values),
        "opening": fill(t.opening, values),
        "closing": fill(t.closing, values),
    }


class OfferedView(APIView):
    """GET: the templates "Email Supplier" offers for this order, by use."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, SUBMIT)
        o = _order(request, pk)
        return Response(
            [
                {
                    "id": t.pk,
                    "name": t.name,
                    "used_for": t.used_for,
                    "used_for_label": t.get_used_for_display(),
                    "is_default": t.is_default,
                }
                for t in offered(o)
            ]
        )
