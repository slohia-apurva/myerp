"""Supplementary bills (Sidharth, 2026-11-16, preview 79): the supplier
charges more for goods already billed. A purchase invoice of kind
"supplementary" against the original bill, numbered with the purchase
invoices; its lines are rate lines (buying/rates.py).

Submit posts: Dr the stock still on hand (its lots are revalued) and
"Purchase Price Difference" for what is used; Dr Input GST on the extra; Round
Off; Cr the supplier, with due dates from the original's credit term counted
from this bill's date. No quantity moves.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying import rates, tds
from buying.api import CREATE, SUBMIT, VIEW, _check, _company, _plain
from buying.invoices import (
    _due_rows,
    _fresh,
    _invoice,
    _side,
    _text,
    bill_clash,
    system_ledger,
)
from buying.models import PurchaseInvoice, PurchaseInvoiceDue, PurchaseInvoiceRateLine
from core import attachments, numbering
from core.api import Signed
from posting import accounts, service
from posting.service import Voucher
from tenancy.context import tenant_atomic

KIND = "purchase_invoice"
ZERO = Decimal("0")
RUPEE = Decimal("1")


def rate_line_out(ln: PurchaseInvoiceRateLine) -> dict:
    il = ln.original_line
    kept = rates.kept_qty(il)
    return {
        "id": ln.pk,
        "invoice_line": il.pk,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "hsn": ln.item.hsn,
        "unit_name": ln.unit.short_name or ln.unit.name,
        "billed_qty": _plain(il.qty),
        "left_qty": _plain(kept),
        "in_stock": _plain(min(rates.in_stock(il), kept)),
        "qty": _plain(ln.qty),
        "rate": _plain(ln.rate),
        "new_rate": _plain(ln.new_rate),
        "gst_rate": _plain(ln.gst_rate),
        "taxable": ln.taxable,
        "cgst": ln.cgst,
        "sgst": ln.sgst,
        "igst": ln.igst,
        "amount": ln.amount,
        "stock_difference": ln.stock_difference,
        "price_difference": ln.price_difference,
    }


class LineSerializer(serializers.Serializer):
    invoice_line = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))
    new_rate = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))


class BillSerializer(serializers.Serializer):
    original = serializers.IntegerField()
    bill_no = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    bill_date = serializers.DateField(required=False, allow_null=True)
    posting_date = serializers.DateField(required=False, allow_null=True)
    bill_total = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _save(inv: PurchaseInvoice, data: dict) -> None:
    original = rates.regular_bill(
        PurchaseInvoice.objects.filter(pk=data["original"], company=inv.company)
        .select_related("supplier", "branch", "credit_term")
        .first(),
        "original",
    )
    rows = rates.checked_lines(original, data.get("lines") or [], rates.UP)
    inv.kind = PurchaseInvoice.SUPPLEMENTARY
    inv.original = original
    inv.supplier, inv.branch = original.supplier, original.branch
    inv.credit_term, inv.interstate = original.credit_term, original.interstate
    inv.bill_no = data.get("bill_no", "").strip()
    inv.bill_date = data.get("bill_date")
    inv.posting_date = data.get("posting_date") or inv.bill_date
    inv.bill_total = data.get("bill_total")
    inv.notes = data.get("notes", "").strip()
    inv.taxable_total = sum((r["taxable"] for r in rows), ZERO)
    inv.cgst_total = sum((r["cgst"] for r in rows), ZERO)
    inv.sgst_total = sum((r["sgst"] for r in rows), ZERO)
    inv.igst_total = sum((r["igst"] for r in rows), ZERO)
    exact = inv.taxable_total + inv.cgst_total + inv.sgst_total + inv.igst_total
    # A total within a rupee of the supplier's is taken as theirs, as on a bill.
    if inv.bill_total is not None and abs(inv.bill_total - exact) < RUPEE:
        inv.total = inv.bill_total
    else:
        inv.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    inv.round_off = inv.total - exact
    inv.save()
    inv.rate_lines.all().delete()
    PurchaseInvoiceRateLine.objects.bulk_create(
        [
            PurchaseInvoiceRateLine(
                invoice=inv,
                position=n,
                original_line=r["il"],
                item=r["il"].item,
                unit=r["il"].unit,
                qty=r["qty"],
                rate=r["il"].rate,
                new_rate=r["new_rate"],
                taxable=r["taxable"],
                gst_rate=r["il"].gst_rate,
                cgst=r["cgst"],
                sgst=r["sgst"],
                igst=r["igst"],
                amount=r["amount"],
            )
            for n, r in enumerate(rows, start=1)
        ]
    )
    tds.refresh(inv)


def plan(inv: PurchaseInvoice, preview: bool = False):
    lines = list(
        inv.rate_lines.select_related("item", "original_line__receipt_line", "original_line__item")
    )
    split, revalue, per_line = rates.plan(inv, lines, rates.UP, preview)
    gl = [*split, *rates.gst_lines(inv, rates.UP, preview)]
    if inv.round_off:
        gl.append(_side(system_ledger(inv.company, accounts.ROUND_OFF, preview), inv.round_off, ""))
    gl += tds.bill_lines(inv, preview)
    gl.append(tds.supplier_line(inv, f"Supplementary bill {inv.bill_no}".strip()))
    return gl, revalue, per_line


def entries(inv: PurchaseInvoice) -> list[dict]:
    from buying.invoices import _first_error

    if not inv.rate_lines.exists():
        return []
    try:
        gl = plan(inv, preview=True)[0]
    except ValidationError as exc:
        return [{"ledger": "", "why": _first_error(exc), "debit": "", "credit": ""}]
    return [
        {"ledger": g.ledger.name, "why": g.remarks, "debit": g.debit, "credit": g.credit}
        for g in gl
    ]


def submit(inv: PurchaseInvoice, user) -> None:
    attachments.require_file(inv, KIND)
    errors = {}
    if not inv.bill_no:
        errors["bill_no"] = ["Give the supplier's invoice number."]
    if inv.bill_date is None:
        errors["bill_date"] = ["Give the supplier's invoice date."]
    if inv.bill_total is None:
        errors["bill_total"] = ["Type the grand total printed on the supplier's bill."]
    lines = list(inv.rate_lines.select_related("item", "original_line"))
    if not lines:
        errors["lines"] = ["Type the revised rate on at least one line."]
    if errors:
        raise ValidationError(errors)
    if inv.bill_total != inv.total:
        raise ValidationError(
            {
                "bill_total": [
                    f"Our total {inv.total} does not match the supplier's bill total "
                    f"{inv.bill_total}. Check the rates, quantities and GST."
                ]
            }
        )
    if inv.posting_date < (inv.original.posting_date or inv.posting_date):
        raise ValidationError(
            {
                "posting_date": [
                    f"The original bill was posted on {inv.original.posting_date:%d-%m-%Y}."
                ]
            }
        )
    bill_clash(inv)
    for ln in lines:
        kept = rates.kept_qty(ln.original_line)
        if ln.qty > kept:
            raise ValidationError(
                {"lines": [f"{ln.item.name}: only {_plain(kept)} was billed and kept."]}
            )
    inv.number = numbering.next_document_number(inv.company, KIND, inv.posting_date, inv.branch)
    inv.save(update_fields=["number", "posting_date"])
    tds.refresh(inv)
    gl, revalue, per_line = plan(inv)
    voucher = Voucher(inv.company, inv.branch, inv.posting_date, KIND, inv.pk, inv.number, user)
    service.post(voucher, gl=gl, revalue=revalue)
    for ln in lines:
        ln.stock_difference, ln.price_difference = per_line[ln.pk]
        ln.save(update_fields=["stock_difference", "price_difference"])
    inv.dues.all().delete()
    PurchaseInvoiceDue.objects.bulk_create(
        [
            PurchaseInvoiceDue(invoice=inv, position=n, due_date=d["due_date"], amount=d["amount"])
            for n, d in enumerate(_due_rows(inv), start=1)
        ]
    )
    inv.status = PurchaseInvoice.SUBMITTED
    inv.submitted_at = timezone.now()
    inv.submitted_by = user
    inv.save()


def draft_from(original: PurchaseInvoice) -> dict:
    rates.regular_bill(original)
    lines = rates.draft_lines(original)
    if not lines:
        raise ValidationError({"detail": "Nothing on this bill is left to change the rate of."})
    return _text(
        {
            "original": original.pk,
            "original_number": original.number,
            "original_bill_no": original.bill_no,
            "original_bill_date": original.bill_date,
            "supplier": original.supplier_id,
            "supplier_name": original.supplier.name,
            "branch_name": original.branch.name,
            "credit_term_name": original.credit_term.name if original.credit_term else "",
            "interstate": original.interstate,
            "lines": lines,
        }
    )


# Views -----------------------------------------------------------------------


def _apply(request, inv: PurchaseInvoice):
    serializer = BillSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    _save(inv, data)
    if data.get("submit"):
        _check(request, SUBMIT)
        if refused := attachments.refuse_submit(inv, KIND):
            return refused
        submit(inv, request.user)
    return None


class BillListView(APIView):
    """POST makes a draft supplementary bill (or, with "submit": true, submits
    it). They are listed with the purchase invoices."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        inv = PurchaseInvoice(company=company, created_by=request.user)
        if refused := _apply(request, inv):
            return refused
        return Response(_fresh(inv), status=status.HTTP_201_CREATED)


class BillDetailView(APIView):
    """PATCH a draft supplementary bill; GET it through purchase-invoices/<pk>/."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        inv = _invoice(request, pk, lock=True)
        if inv.kind != PurchaseInvoice.SUPPLEMENTARY:
            raise ValidationError({"detail": "This is not a supplementary bill."})
        if inv.status != PurchaseInvoice.DRAFT:
            raise ValidationError(
                {"detail": "A submitted bill cannot be changed. Cancel it and make a new one."}
            )
        if refused := _apply(request, inv):
            return refused
        return Response(_fresh(inv))


class BillDraftFromView(APIView):
    """GET ?invoice=ID: a new supplementary bill's lines, for "Create ▾"."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        value = request.query_params.get("invoice", "")
        if not value.isdigit():
            raise ValidationError({"invoice": ["Name the original purchase invoice."]})
        inv = PurchaseInvoice.objects.filter(pk=int(value), company=company).first()
        return Response(draft_from(rates.regular_bill(inv)))
