"""Purchase bills without goods receipt (Sidharth, 2026-11-16, preview 82):
services, and goods not kept in stock. A purchase invoice of kind "direct",
numbered and listed with the purchase invoices.

Each line is an item (a service, or goods with "Maintain stock" off), booked to
the item's own "Expense Account" for the company (Masters > Items) or else its
item group's COGS/Expense ledger; or an expense ledger, booked to itself. Fixed
assets are not bought on this bill.

Submit posts: Dr each line's ledger, Dr Input GST, Round Off, Cr the supplier,
with due dates from the credit term counted from the bill date. No stock moves.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import CREATE, SUBMIT, VIEW, _check, _company, _plain
from buying.invoices import (
    _due_rows,
    _first_error,
    _fresh,
    _gst,
    _invoice,
    _side,
    bill_clash,
    system_ledger,
)
from buying.models import PurchaseInvoice, PurchaseInvoiceDue, PurchaseInvoiceExpenseLine
from core import attachments, numbering
from core.api import Signed
from core.items import gst_rate_on
from core.models import Branch, CreditTerm, Item, Ledger, Unit
from posting import accounts, service
from posting.service import GLLine, Voucher, money
from tenancy.context import tenant_atomic

KIND = "purchase_invoice"
ZERO = Decimal("0")
RUPEE = Decimal("1")


def _items():
    """Items a bill without goods receipt may carry: bought, and not kept in stock."""
    return Item.objects.filter(allow_purchase=True, maintain_stock=False, is_active=True)


def _expense_ledgers(company):
    return Ledger.objects.filter(
        company=company, group__nature="expense", party__isnull=True, is_active=True
    )


def _booked_to(company, item: Item | None, ledger: Ledger | None) -> Ledger | None:
    """The ledger a line is booked to, or None when the item has no account yet
    (Submit then says what to set)."""
    if ledger is not None:
        return ledger
    try:
        return accounts.expense_ledger(company, item)
    except ValidationError:
        return None


def line_out(ln: PurchaseInvoiceExpenseLine) -> dict:
    return {
        "id": ln.pk,
        "item": ln.item_id,
        "ledger": ln.ledger_id,
        "name": ln.item.name if ln.item_id else ln.ledger.name,
        "what": (
            ("Service item" if ln.item.item_type == Item.SERVICE else "Item not kept in stock")
            if ln.item_id
            else "Ledger (expense)"
        ),
        "description": ln.description,
        "hsn": ln.hsn,
        "unit": ln.unit_id,
        "unit_name": (ln.unit.short_name or ln.unit.name) if ln.unit_id else "",
        "qty": _plain(ln.qty),
        "rate": _plain(ln.rate),
        "taxable": ln.taxable,
        "gst_rate": _plain(ln.gst_rate),
        "cgst": ln.cgst,
        "sgst": ln.sgst,
        "igst": ln.igst,
        "amount": ln.amount,
        "booked_to": ln.booked_to_id,
        "booked_to_name": ln.booked_to.name if ln.booked_to_id else "",
    }


def lines_of(inv: PurchaseInvoice) -> list[dict]:
    return [
        line_out(ln)
        for ln in inv.expense_lines.select_related("item", "ledger", "unit", "booked_to")
    ]


class LineSerializer(serializers.Serializer):
    item = serializers.IntegerField(required=False, allow_null=True)
    ledger = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    hsn = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    unit = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))
    rate = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))
    gst_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100")
    )


class BillSerializer(serializers.Serializer):
    supplier = serializers.IntegerField()
    branch = serializers.IntegerField()
    bill_no = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    bill_date = serializers.DateField(required=False, allow_null=True)
    posting_date = serializers.DateField(required=False, allow_null=True)
    credit_term = serializers.IntegerField(required=False, allow_null=True)
    bill_total = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _save(inv: PurchaseInvoice, data: dict) -> None:
    company = inv.company
    supplier = (
        Ledger.objects.filter(
            pk=data["supplier"], company=company, party_side="supplier", party__isnull=False
        )
        .select_related("party")
        .first()
    )
    if supplier is None:
        raise ValidationError({"supplier": ["Pick a supplier of this company."]})
    branch = Branch.objects.filter(pk=data["branch"], company=company).first()
    if branch is None:
        raise ValidationError({"branch": ["Pick a branch of this company."]})
    term = None
    if data.get("credit_term"):
        term = CreditTerm.objects.filter(pk=data["credit_term"]).first()
        if term is None:
            raise ValidationError({"credit_term": ["Pick a credit term from the list."]})
    party = supplier.party
    interstate = bool(party and party.state_code and party.state_code != branch.state_code)

    rows, errors = [], []
    for n, line in enumerate(data.get("lines") or [], start=1):
        item = ledger = unit = None
        if line.get("item"):
            item = _items().filter(pk=line["item"]).first()
            if item is None:
                errors.append(
                    f"Line {n}: pick a service or an item not kept in stock. Items kept in "
                    "stock are billed against their goods receipt."
                )
                continue
        elif line.get("ledger"):
            ledger = _expense_ledgers(company).filter(pk=line["ledger"]).first()
            if ledger is None:
                errors.append(f"Line {n}: pick an expense ledger of this company.")
                continue
        else:
            continue  # an empty row
        if line.get("unit"):
            unit = Unit.objects.filter(pk=line["unit"]).first()
        elif item is not None:
            unit = item.purchase_unit or item.stock_unit
        if line["qty"] <= 0:
            errors.append(f"Line {n}: give the quantity.")
            continue
        taxable = money(line["qty"] * line["rate"])
        cgst, sgst, igst = _gst(taxable, line["gst_rate"], interstate)
        rows.append(
            PurchaseInvoiceExpenseLine(
                position=len(rows) + 1,
                item=item,
                ledger=ledger,
                description=line.get("description", "").strip(),
                hsn=item.hsn if item else line.get("hsn", "").strip(),
                unit=unit,
                qty=line["qty"],
                rate=line["rate"],
                taxable=taxable,
                gst_rate=line["gst_rate"],
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                amount=taxable + cgst + sgst + igst,
                booked_to=_booked_to(company, item, ledger),
            )
        )
    if errors:
        raise ValidationError({"lines": errors})

    inv.kind = PurchaseInvoice.DIRECT
    inv.supplier, inv.branch, inv.credit_term = supplier, branch, term
    inv.bill_no = data.get("bill_no", "").strip()
    inv.bill_date = data.get("bill_date")
    inv.posting_date = data.get("posting_date") or inv.bill_date
    inv.bill_total = data.get("bill_total")
    inv.notes = data.get("notes", "").strip()
    inv.interstate = interstate
    inv.taxable_total = sum((r.taxable for r in rows), ZERO)
    inv.cgst_total = sum((r.cgst for r in rows), ZERO)
    inv.sgst_total = sum((r.sgst for r in rows), ZERO)
    inv.igst_total = sum((r.igst for r in rows), ZERO)
    exact = inv.taxable_total + inv.cgst_total + inv.sgst_total + inv.igst_total
    # The supplier's own rounding wins when it is within a rupee of ours.
    if inv.bill_total is not None and abs(inv.bill_total - exact) < RUPEE:
        inv.total = inv.bill_total
    else:
        inv.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    inv.round_off = inv.total - exact
    inv.save()
    inv.expense_lines.all().delete()
    for r in rows:
        r.invoice = inv
    PurchaseInvoiceExpenseLine.objects.bulk_create(rows)


def plan(inv: PurchaseInvoice, preview: bool = False) -> list[GLLine]:
    company = inv.company
    gl: list[GLLine] = []
    for ln in inv.expense_lines.select_related("item", "ledger"):
        led = ln.ledger or accounts.expense_ledger(company, ln.item)
        name = ln.item.name if ln.item_id else ""
        why = " · ".join(x for x in (name, ln.description) if x)
        gl.append(GLLine(led, debit=ln.taxable, remarks=why))
    for code, value in (
        (accounts.INPUT_CGST, inv.cgst_total),
        (accounts.INPUT_SGST, inv.sgst_total),
        (accounts.INPUT_IGST, inv.igst_total),
    ):
        if value:
            gl.append(GLLine(system_ledger(company, code, preview), debit=value))
    if inv.round_off:
        gl.append(_side(system_ledger(company, accounts.ROUND_OFF, preview), inv.round_off, ""))
    gl.append(GLLine(inv.supplier, credit=inv.total, remarks=f"Bill {inv.bill_no}".strip()))
    return gl


def entries(inv: PurchaseInvoice) -> list[dict]:
    if not inv.expense_lines.exists():
        return []
    try:
        gl = plan(inv, preview=True)
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
    lines = list(inv.expense_lines.select_related("item", "ledger"))
    if not lines:
        errors["lines"] = ["Add what is billed."]
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
    bill_clash(inv)
    # Fix where each line is booked, as posted.
    for ln in lines:
        ln.booked_to = ln.ledger or accounts.expense_ledger(inv.company, ln.item)
        ln.save(update_fields=["booked_to"])
    inv.number = numbering.next_document_number(inv.company, KIND, inv.posting_date, inv.branch)
    inv.save(update_fields=["number", "posting_date"])
    voucher = Voucher(inv.company, inv.branch, inv.posting_date, KIND, inv.pk, inv.number, user)
    service.post(voucher, gl=plan(inv))
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
    """POST makes a draft bill without goods receipt (or, with "submit": true,
    submits it). They are listed with the purchase invoices."""

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
    """PATCH a draft; GET it through purchase-invoices/<pk>/."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        inv = _invoice(request, pk, lock=True)
        if inv.kind != PurchaseInvoice.DIRECT:
            raise ValidationError({"detail": "This is not a bill without goods receipt."})
        if inv.status != PurchaseInvoice.DRAFT:
            raise ValidationError(
                {"detail": "A submitted bill cannot be changed. Cancel it and make a new one."}
            )
        if refused := _apply(request, inv):
            return refused
        return Response(_fresh(inv))


class BillSetupView(APIView):
    """GET: the items and expense ledgers a line may pick, with GST rates today
    and where each item is booked in this company."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        today = timezone.localdate()
        items = []
        for i in _items().select_related("purchase_unit", "stock_unit").order_by("name"):
            unit = i.purchase_unit or i.stock_unit
            booked = _booked_to(company, i, None)
            rate = gst_rate_on(i, today)
            items.append(
                {
                    "id": i.pk,
                    "name": i.name,
                    "service": i.item_type == Item.SERVICE,
                    "hsn": i.hsn,
                    "unit": unit.pk,
                    "unit_name": unit.short_name or unit.name,
                    "gst_rate": _plain(rate) if rate is not None else None,
                    "booked_to_name": booked.name if booked else "",
                }
            )
        ledgers = [
            {"id": led.pk, "name": led.name} for led in _expense_ledgers(company).order_by("name")
        ]
        units = [
            {"id": u.pk, "name": u.short_name or u.name}
            for u in Unit.objects.filter(is_active=True).order_by("name")
        ]
        return Response({"items": items, "ledgers": ledgers, "units": units})
