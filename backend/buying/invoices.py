"""Purchase invoices (Sidharth, 2026-11-15, preview 67): the supplier's bill,
entered against goods receipts.

Each line bills a quantity of a receipt line still to be billed, at the bill's
rate. The bill's grand total is typed in ("Supplier's Bill Total") and Submit
needs ours to match it; a difference under a rupee goes to Round Off.

Submit posts (posting.service):
* Dr "Goods Received but Bills not Received": the receipt value of what is
  billed (goods plus the charges the receipt added to stock cost);
* Dr the item's stock ledger for the rate difference on the stock still on
  hand (its lots are revalued), Dr "Purchase Price Difference" for the rest;
* Dr Input CGST / SGST / IGST; Dr the expense ledger of charges that were not
  added to stock cost; Dr/Cr Round Off;
* Cr the supplier, with due dates from the credit term counted from the bill
  date (Sidharth, 2026-11-15).
It moves no stock: the receipt brought the goods in. Rupee receipts only for
now; an import's bill comes with its bill of entry, later.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import F, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import CANCEL, CREATE, SUBMIT, VIEW, _check, _company, _plain
from buying.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseInvoiceCharge,
    PurchaseInvoiceDue,
    PurchaseInvoiceLine,
)
from buying.receipts import _factor
from core import numbering
from core.api import Signed
from core.companies import visible_companies
from core.credit_terms import summary as term_summary
from core.models import Branch, CreditTerm, FiscalYear, Item, Ledger
from posting import accounts, service
from posting.models import GLEntry, StockLot, StockMove
from posting.service import GLLine, Revalue, Voucher, money
from tenancy.context import tenant_atomic

KIND = "purchase_invoice"
ZERO = Decimal("0")
RUPEE = Decimal("1")


def _text(value):
    """Decimals as strings (never floats) all through a reply."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _text(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_text(v) for v in value]
    return value


def _dmy(d) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def _receipt_rate(rl: GoodsReceiptLine) -> Decimal:
    """The order's rate per unit after discount, before GST."""
    ol = rl.order_line
    return (ol.taxable / ol.qty).quantize(Decimal("0.000001")) if ol.qty else ZERO


def _unbilled(rl: GoodsReceiptLine) -> Decimal:
    return max(rl.accepted_qty - rl.billed_qty, ZERO)


def _gst(taxable: Decimal, rate: Decimal, interstate: bool) -> tuple[Decimal, Decimal, Decimal]:
    tax = money(taxable * rate / 100)
    if interstate:
        return ZERO, ZERO, tax
    cgst = money(tax / 2)
    return cgst, tax - cgst, ZERO


# Reading ---------------------------------------------------------------------


def _invoices(company):
    return (
        PurchaseInvoice.objects.filter(company=company)
        .select_related("supplier__party", "branch", "credit_term", "created_by", "submitted_by")
        .prefetch_related("receipts", "dues")
    )


def _receipt_lines():
    return GoodsReceiptLine.objects.select_related(
        "receipt", "order_line__order", "item", "unit"
    ).filter(receipt__status=GoodsReceipt.SUBMITTED, receipt__currency="INR")


def _line_out(ln: PurchaseInvoiceLine, inv: PurchaseInvoice) -> dict:
    rl = ln.receipt_line
    unbilled = _unbilled(rl) + (ln.qty if inv.status == PurchaseInvoice.SUBMITTED else ZERO)
    return {
        "id": ln.pk,
        "receipt_line": rl.pk,
        "receipt": rl.receipt_id,
        "receipt_number": rl.receipt.number,
        "order_number": rl.order_line.order.number,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "hsn": ln.item.hsn,
        "unit": ln.unit_id,
        "unit_name": ln.unit.short_name or ln.unit.name,
        "unbilled_qty": _plain(unbilled),
        "qty": _plain(ln.qty),
        "receipt_rate": _plain(_receipt_rate(rl)),
        "rate": _plain(ln.rate),
        "taxable": ln.taxable,
        "gst_rate": _plain(ln.gst_rate),
        "cgst": ln.cgst,
        "sgst": ln.sgst,
        "igst": ln.igst,
        "amount": ln.amount,
        "receipt_value": ln.receipt_value,
        "stock_difference": ln.stock_difference,
        "price_difference": ln.price_difference,
    }


def _charge_out(c: PurchaseInvoiceCharge) -> dict:
    return {
        "id": c.pk,
        "item": c.item_id,
        "item_name": c.item.name,
        "sac": c.item.hsn,
        "amount": c.amount,
        "gst_rate": _plain(c.gst_rate),
        "cgst": c.cgst,
        "sgst": c.sgst,
        "igst": c.igst,
        "in_stock_cost": c.in_stock_cost,
    }


def _invoice_out(inv: PurchaseInvoice, lines: bool = True) -> dict:
    party = inv.supplier.party
    dues = list(inv.dues.all())
    receipts = list(inv.receipts.all())
    data = {
        "id": inv.pk,
        "company": inv.company_id,
        "number": inv.number,
        "status": inv.status,
        "status_label": inv.get_status_display(),
        "supplier": inv.supplier_id,
        "supplier_name": inv.supplier.name,
        "supplier_gstin": party.gstin if party else "",
        "branch": inv.branch_id,
        "branch_name": inv.branch.name,
        "bill_no": inv.bill_no,
        "bill_date": inv.bill_date,
        "posting_date": inv.posting_date,
        "credit_term": inv.credit_term_id,
        "credit_term_name": inv.credit_term.name if inv.credit_term else "",
        "credit_term_summary": term_summary(inv.credit_term) if inv.credit_term else "",
        "bill_total": inv.bill_total,
        "interstate": inv.interstate,
        "taxable_total": inv.taxable_total,
        "cgst_total": inv.cgst_total,
        "sgst_total": inv.sgst_total,
        "igst_total": inv.igst_total,
        "round_off": inv.round_off,
        "total": inv.total,
        "notes": inv.notes,
        "cancel_reason": inv.cancel_reason,
        "receipts": [{"id": r.pk, "number": r.number} for r in receipts],
        "first_due": dues[0].due_date if dues else None,
        "created_by_name": inv.created_by.display_name if inv.created_by else "",
        "created_at": inv.created_at,
        "submitted_at": inv.submitted_at,
        "submitted_by_name": inv.submitted_by.display_name if inv.submitted_by else "",
    }
    if lines:
        rows = inv.lines.select_related(
            "item", "unit", "receipt_line__receipt", "receipt_line__order_line__order"
        )
        data["lines"] = [_line_out(ln, inv) for ln in rows]
        data["charges"] = [_charge_out(c) for c in inv.charges.select_related("item")]
        data["dues"] = [{"due_date": d.due_date, "amount": d.amount} for d in dues] or _due_rows(
            inv
        )
        data["orders"] = sorted({(r["order_number"]) for r in data["lines"] if r["order_number"]})
        data["entries"] = _entries(inv)
    return _text(data)


def _fresh(inv: PurchaseInvoice) -> dict:
    return _invoice_out(_invoices(inv.company).get(pk=inv.pk))


def _entries(inv: PurchaseInvoice) -> list[dict]:
    """The GL lines: as posted for a submitted invoice, else what Submit would post."""
    if inv.status == PurchaseInvoice.SUBMITTED:
        rows = GLEntry.objects.filter(
            voucher_type=KIND, voucher_id=inv.pk, is_reversal=False
        ).select_related("ledger")
        return [
            {"ledger": e.ledger.name, "why": e.remarks, "debit": e.debit, "credit": e.credit}
            for e in rows
        ]
    if inv.status != PurchaseInvoice.DRAFT or not inv.lines.exists():
        return []
    try:
        plan = _plan(inv, preview=True)
    except ValidationError as exc:
        return [{"ledger": "", "why": _first_error(exc), "debit": "", "credit": ""}]
    return [
        {"ledger": g.ledger.name, "why": g.remarks, "debit": g.debit, "credit": g.credit}
        for g in plan.gl
    ]


def _first_error(exc: ValidationError) -> str:
    detail = exc.detail
    while isinstance(detail, list | dict):
        detail = next(iter(detail.values())) if isinstance(detail, dict) else detail[0]
    return str(detail)


# Due dates -------------------------------------------------------------------


def _due_rows(inv: PurchaseInvoice) -> list[dict]:
    """The credit term's parts as due dates, each counted from the bill date
    (Sidharth, 2026-11-15); the last part takes what is left."""
    total = inv.total or ZERO
    day = inv.bill_date or inv.posting_date
    if not total or day is None:
        return []
    parts = list(inv.credit_term.parts.all()) if inv.credit_term else []
    if not parts:
        return [{"due_date": day, "amount": total}]
    rows, left = [], total
    for n, p in enumerate(parts):
        amount = left if n == len(parts) - 1 else money(total * p.percent / 100)
        left -= amount
        rows.append({"due_date": day + datetime.timedelta(days=p.days), "amount": amount})
    return rows


# Saving ----------------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    receipt_line = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))
    rate = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))
    gst_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100")
    )


class ChargeSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0"))
    gst_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100")
    )
    in_stock_cost = serializers.BooleanField(default=False)


class InvoiceSerializer(serializers.Serializer):
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
    charges = ChargeSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _save(inv: PurchaseInvoice, data: dict) -> None:
    company = inv.company
    supplier = Ledger.objects.filter(
        pk=data["supplier"], company=company, party_side="supplier", party__isnull=False
    ).first()
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

    rows, errors, seen = [], [], set()
    interstate = None
    for n, line in enumerate(data.get("lines") or [], start=1):
        rl = _receipt_lines().filter(pk=line["receipt_line"], receipt__company=company).first()
        if rl is None:
            errors.append(f"Line {n}: pick a line of a submitted goods receipt in rupees.")
            continue
        if rl.receipt.supplier_id != supplier.pk or rl.receipt.branch_id != branch.pk:
            errors.append(f"Line {n}: {rl.receipt.number} is of another supplier or branch.")
            continue
        if rl.pk in seen:
            errors.append(f"Line {n}: {rl.item.name} of {rl.receipt.number} is billed twice.")
            continue
        seen.add(rl.pk)
        if line["qty"] <= 0:
            errors.append(f"Line {n}: give the quantity billed.")
            continue
        if line["qty"] > _unbilled(rl):
            errors.append(
                f"Line {n}: only {_plain(_unbilled(rl))} {rl.unit.short_name} of {rl.item.name} "
                f"on {rl.receipt.number} is still to be billed."
            )
            continue
        order = rl.order_line.order
        interstate = order.interstate if interstate is None else interstate
        taxable = money(line["qty"] * line["rate"])
        cgst, sgst, igst = _gst(taxable, line["gst_rate"], interstate)
        rows.append(
            PurchaseInvoiceLine(
                position=n,
                receipt_line=rl,
                item=rl.item,
                unit=rl.unit,
                qty=line["qty"],
                rate=line["rate"],
                taxable=taxable,
                gst_rate=line["gst_rate"],
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                amount=taxable + cgst + sgst + igst,
            )
        )
    if errors:
        raise ValidationError({"lines": errors})
    if interstate is None:
        party = supplier.party
        interstate = bool(party and party.state_code and party.state_code != branch.state_code)
    charges = []
    for n, c in enumerate(data.get("charges") or [], start=1):
        item = Item.objects.filter(pk=c["item"]).first()
        if item is None:
            raise ValidationError({"charges": [f"Charge {n}: pick a charge from the list."]})
        if not c["amount"]:
            continue
        cgst, sgst, igst = _gst(c["amount"], c["gst_rate"], interstate)
        charges.append(
            PurchaseInvoiceCharge(
                position=n,
                item=item,
                amount=c["amount"],
                gst_rate=c["gst_rate"],
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                in_stock_cost=c["in_stock_cost"],
            )
        )

    inv.supplier, inv.branch, inv.credit_term = supplier, branch, term
    inv.bill_no = data.get("bill_no", "").strip()
    inv.bill_date = data.get("bill_date")
    inv.posting_date = data.get("posting_date") or inv.bill_date
    inv.bill_total = data.get("bill_total")
    inv.notes = data.get("notes", "").strip()
    inv.interstate = interstate
    both = [*rows, *charges]
    inv.taxable_total = sum((r.taxable for r in rows), ZERO) + sum(
        (c.amount for c in charges), ZERO
    )
    inv.cgst_total = sum((r.cgst for r in both), ZERO)
    inv.sgst_total = sum((r.sgst for r in both), ZERO)
    inv.igst_total = sum((r.igst for r in both), ZERO)
    exact = inv.taxable_total + inv.cgst_total + inv.sgst_total + inv.igst_total
    inv.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    # The supplier's own rounding wins when it is within a rupee of ours.
    if inv.bill_total is not None and abs(inv.bill_total - exact) < RUPEE:
        inv.total = inv.bill_total
    inv.round_off = inv.total - exact
    inv.save()
    inv.lines.all().delete()
    for r in rows:
        r.invoice = inv
    PurchaseInvoiceLine.objects.bulk_create(rows)
    inv.charges.all().delete()
    for c in charges:
        c.invoice = inv
    PurchaseInvoiceCharge.objects.bulk_create(charges)
    inv.receipts.set({r.receipt_line.receipt_id for r in rows})


# Posting ---------------------------------------------------------------------


@dataclass
class _Plan:
    gl: list[GLLine]
    revalue: list[Revalue]
    per_line: dict[int, tuple[Decimal, Decimal, Decimal]]  # receipt value, stock, price diff


def _side(ledger: Ledger, value: Decimal, remarks: str) -> GLLine:
    """A signed amount as a debit (positive) or a credit (negative)."""
    if value >= 0:
        return GLLine(ledger, debit=value, remarks=remarks)
    return GLLine(ledger, credit=-value, remarks=remarks)


def _receipt_value(rl: GoodsReceiptLine, qty: Decimal) -> Decimal:
    """The share of the receipt line's stock value this quantity clears; the
    last bill takes exactly what is left, so no paisa stays behind."""
    if rl.billed_qty + qty >= rl.accepted_qty:
        return rl.value - rl.billed_value
    return money(rl.value * qty / rl.accepted_qty)


def _lots(rl: GoodsReceiptLine) -> list[StockLot]:
    moves = StockMove.objects.filter(
        voucher_type="goods_receipt",
        voucher_id=rl.receipt_id,
        item_id=rl.item_id,
        is_reversal=False,
        qty__gt=0,
    )
    return list(StockLot.objects.filter(move__in=moves, qty_left__gt=0).order_by("id"))


def _plan(inv: PurchaseInvoice, preview: bool = False) -> _Plan:
    company = inv.company
    lines = list(
        inv.lines.select_related("item", "receipt_line__receipt", "receipt_line__item").all()
    )
    charges = list(inv.charges.select_related("item"))
    values = {ln.pk: _receipt_value(ln.receipt_line, ln.qty) for ln in lines}
    total_value = sum(values.values(), ZERO)
    stock_charges = sum((c.amount for c in charges if c.in_stock_cost), ZERO)

    gl: list[GLLine] = []
    revalue: list[Revalue] = []
    per_line = {}
    stock_by_ledger: dict[int, list] = {}
    price_diff = ZERO
    left_charges = stock_charges
    for n, ln in enumerate(lines):
        # The bill's goods plus its share of the stock-cost charges, against
        # what the receipt put into stock for them.
        if n == len(lines) - 1:
            share = left_charges
        else:
            share = money(stock_charges * values[ln.pk] / total_value) if total_value else ZERO
        left_charges -= share
        diff = ln.taxable + share - values[ln.pk]
        on_hand_value = ZERO
        if diff:
            lots = _lots(ln.receipt_line)
            billed = ln.qty * _factor(ln.item, ln.unit_id)
            on_hand = min(sum((lot.qty_left for lot in lots), ZERO), billed)
            on_hand_value = money(diff * on_hand / billed) if billed else ZERO
            left = on_hand_value
            spread = sum((lot.qty_left for lot in lots), ZERO)
            for i, lot in enumerate(lots):
                if not left:
                    break
                part = left if i == len(lots) - 1 else money(on_hand_value * lot.qty_left / spread)
                revalue.append(Revalue(lot, part))
                left -= part
        line_price = diff - on_hand_value
        price_diff += line_price
        per_line[ln.pk] = (values[ln.pk], on_hand_value, line_price)
        if on_hand_value:
            led = accounts.stock_ledger(company, ln.item)
            stock_by_ledger.setdefault(led.pk, [led, ZERO])[1] += on_hand_value

    def ledger(code):
        if preview:
            from posting.accounts import SYSTEM_LEDGERS

            found = Ledger.objects.filter(company=company, system_code=code).first()
            return found or Ledger(company=company, name=SYSTEM_LEDGERS[code][0])
        return accounts.system_ledger(company, code)

    receipts = ", ".join(sorted({ln.receipt_line.receipt.number for ln in lines}))
    gl.append(GLLine(ledger(accounts.GRNI), debit=total_value, remarks=f"Clears {receipts}"))
    for led, value in stock_by_ledger.values():
        gl.append(_side(led, value, "Bill rate differs: stock still on hand"))
    if price_diff:
        gl.append(
            _side(ledger(accounts.PRICE_DIFFERENCE), price_diff, "Bill rate differs: stock used")
        )
    for c in charges:
        if not c.in_stock_cost:
            gl.append(GLLine(accounts.cogs_ledger(company, c.item), debit=c.amount,
                             remarks=c.item.name))  # fmt: skip
    for code, value in (
        (accounts.INPUT_CGST, inv.cgst_total),
        (accounts.INPUT_SGST, inv.sgst_total),
        (accounts.INPUT_IGST, inv.igst_total),
    ):
        if value:
            gl.append(GLLine(ledger(code), debit=value))
    if inv.round_off:
        gl.append(_side(ledger(accounts.ROUND_OFF), inv.round_off, ""))
    gl.append(GLLine(inv.supplier, credit=inv.total, remarks=f"Bill {inv.bill_no}".strip()))
    return _Plan(gl, revalue, per_line)


def _fiscal_year(company, day):
    return FiscalYear.objects.filter(
        company=company, start_date__lte=day, end_date__gte=day
    ).first()


def _submit(inv: PurchaseInvoice, user) -> None:
    errors = {}
    if not inv.bill_no:
        errors["bill_no"] = ["Give the supplier's invoice number."]
    if inv.bill_date is None:
        errors["bill_date"] = ["Give the supplier's invoice date."]
    if inv.bill_total is None:
        errors["bill_total"] = ["Type the grand total printed on the supplier's bill."]
    lines = list(inv.lines.select_related("receipt_line", "item"))
    if not lines:
        errors["lines"] = ["Add the goods billed."]
    if errors:
        raise ValidationError(errors)
    if inv.posting_date is None:
        inv.posting_date = inv.bill_date
    if inv.bill_total != inv.total:
        raise ValidationError(
            {
                "bill_total": [
                    f"Our total {inv.total} does not match the supplier's bill total "
                    f"{inv.bill_total}. Check the rates, quantities, GST and charges."
                ]
            }
        )
    year = _fiscal_year(inv.company, inv.bill_date)
    same = PurchaseInvoice.objects.filter(
        company=inv.company,
        supplier=inv.supplier,
        bill_no__iexact=inv.bill_no,
        status=PurchaseInvoice.SUBMITTED,
    ).exclude(pk=inv.pk)
    if year is not None:
        same = same.filter(bill_date__gte=year.start_date, bill_date__lte=year.end_date)
    if clash := same.first():
        raise ValidationError(
            {
                "bill_no": [
                    f"{inv.supplier.name}'s bill {inv.bill_no} is already entered "
                    f"as {clash.number}."
                ]
            }
        )
    # Lock the receipt lines and check again what is still to be billed.
    for ln in lines:
        rl = GoodsReceiptLine.objects.select_for_update().get(pk=ln.receipt_line_id)
        ln.receipt_line = rl
        if ln.qty > _unbilled(rl):
            raise ValidationError(
                {"lines": [f"{ln.item.name}: only {_plain(_unbilled(rl))} is still to be billed."]}
            )

    inv.number = numbering.next_document_number(inv.company, KIND, inv.posting_date, inv.branch)
    inv.save(update_fields=["number", "posting_date"])
    plan = _plan(inv)
    voucher = Voucher(inv.company, inv.branch, inv.posting_date, KIND, inv.pk, inv.number, user)
    service.post(voucher, gl=plan.gl, revalue=plan.revalue)
    for ln in lines:
        value, stock, price = plan.per_line[ln.pk]
        ln.receipt_value, ln.stock_difference, ln.price_difference = value, stock, price
        ln.save(update_fields=["receipt_value", "stock_difference", "price_difference"])
        GoodsReceiptLine.objects.filter(pk=ln.receipt_line_id).update(
            billed_qty=F("billed_qty") + ln.qty, billed_value=F("billed_value") + value
        )
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


def _cancel(inv: PurchaseInvoice, user, reason: str) -> None:
    if inv.status == PurchaseInvoice.SUBMITTED:
        service.cancel(KIND, inv.pk, user)
        for ln in inv.lines.all():
            GoodsReceiptLine.objects.filter(pk=ln.receipt_line_id).update(
                billed_qty=F("billed_qty") - ln.qty,
                billed_value=F("billed_value") - ln.receipt_value,
            )
    inv.status = PurchaseInvoice.CANCELLED
    inv.cancel_reason = reason[:200]
    inv.save()


# A new invoice from receipts or an order ---------------------------------------


def _draft_from(company, receipt_lines: list[GoodsReceiptLine]) -> dict:
    """A ready-to-fill form: the lines still to be billed at the order's rate
    and GST, and the order's charges in proportion to what is billed."""
    if not receipt_lines:
        raise ValidationError({"detail": "Everything received here has been billed."})
    first = receipt_lines[0]
    order = first.order_line.order
    lines = [
        {
            "receipt_line": rl.pk,
            "receipt": rl.receipt_id,
            "receipt_number": rl.receipt.number,
            "order_number": rl.order_line.order.number,
            "item": rl.item_id,
            "item_name": rl.item.name,
            "hsn": rl.item.hsn,
            "unit": rl.unit_id,
            "unit_name": rl.unit.short_name or rl.unit.name,
            "unbilled_qty": _plain(_unbilled(rl)),
            "qty": _plain(_unbilled(rl)),
            "receipt_rate": _plain(_receipt_rate(rl)),
            "rate": _plain(_receipt_rate(rl)),
            "gst_rate": _plain(rl.order_line.gst_rate),
        }
        for rl in receipt_lines
    ]
    charges = []
    by_order: dict[int, Decimal] = defaultdict(lambda: ZERO)
    orders = {}
    for rl in receipt_lines:
        o = rl.order_line.order
        orders[o.pk] = o
        by_order[o.pk] += _receipt_rate(rl) * _unbilled(rl)
    for oid, billed in by_order.items():
        o = orders[oid]
        goods = sum((ln.taxable for ln in o.lines.all()), ZERO)
        for c in o.charges.select_related("item"):
            amount = money(c.amount * billed / goods) if goods else ZERO
            if amount:
                charges.append(
                    {
                        "item": c.item_id,
                        "item_name": c.item.name,
                        "sac": c.item.hsn,
                        "amount": str(amount),
                        "gst_rate": _plain(c.gst_rate),
                        "in_stock_cost": c.add_to_stock != Item.NO_STOCK_COST,
                    }
                )
    term = order.credit_term
    return {
        "supplier": first.receipt.supplier_id,
        "supplier_name": first.receipt.supplier.name,
        "branch": first.receipt.branch_id,
        "branch_name": first.receipt.branch.name,
        "credit_term": term.pk if term else None,
        "interstate": order.interstate,
        "lines": lines,
        "charges": charges,
    }


def _open_receipt_lines(company, **where) -> list[GoodsReceiptLine]:
    rows = _receipt_lines().filter(receipt__company=company, **where)
    return [
        rl
        for rl in rows.filter(accepted_qty__gt=F("billed_qty")).order_by("receipt_id", "position")
    ]


# Views -----------------------------------------------------------------------


def _invoice(request, pk: int, lock: bool = False) -> PurchaseInvoice:
    rows = PurchaseInvoice.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    inv = rows.select_related("company").first()
    if inv is None or "purchase" not in inv.company.modules:
        raise NotFound("No such purchase invoice.")
    return inv


class InvoiceListView(APIView):
    """GET ?view=submitted|draft|cancelled|all&q=text. POST makes a draft (or,
    with "submit": true, submits it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = _invoices(company)
        view = request.query_params.get("view", "submitted")
        if view in (PurchaseInvoice.DRAFT, PurchaseInvoice.SUBMITTED, PurchaseInvoice.CANCELLED):
            rows = rows.filter(status=view)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(supplier__name__icontains=word)
                | Q(bill_no__icontains=word)
                | Q(receipts__number__icontains=word)
            ).distinct()
        return Response([_invoice_out(inv, lines=False) for inv in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        serializer = InvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        inv = PurchaseInvoice(company=company, created_by=request.user)
        _save(inv, data)
        if data.get("submit"):
            _check(request, SUBMIT)
            _submit(inv, request.user)
        return Response(_fresh(inv), status=status.HTTP_201_CREATED)


class InvoiceDetailView(APIView):
    """GET one invoice; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(_fresh(_invoice(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        inv = _invoice(request, pk, lock=True)
        if inv.status != PurchaseInvoice.DRAFT:
            raise ValidationError(
                {"detail": "A submitted invoice cannot be changed. Cancel it and make a new one."}
            )
        serializer = InvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(inv, data)
        if data.get("submit"):
            _check(request, SUBMIT)
            _submit(inv, request.user)
        return Response(_fresh(inv))


class InvoiceCancelView(APIView):
    """POST {reason}. Reverses the entries; refused if revalued stock has since been used."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CANCEL)
        inv = _invoice(request, pk, lock=True)
        if inv.status == PurchaseInvoice.CANCELLED:
            raise ValidationError({"detail": "This invoice is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(inv, request.user, reason)
        return Response(_fresh(inv))


class InvoiceDraftFromView(APIView):
    """GET ?receipt=ID or ?order=ID (or ?supplier=ID&branch=ID): the lines still to
    be billed, for "Create ▾ › Purchase Invoice"."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        q = request.query_params
        where = {}
        for key, field in (
            ("receipt", "receipt_id"),
            ("order", "order_line__order_id"),
            ("supplier", "receipt__supplier_id"),
            ("branch", "receipt__branch_id"),
        ):
            if value := q.get(key):
                if not value.isdigit():
                    raise ValidationError({key: ["Give a number."]})
                where[field] = int(value)
        if not where:
            raise ValidationError({"detail": "Name a receipt, an order or a supplier."})
        lines = _open_receipt_lines(company, **where)
        if not lines and "receipt_id" in where:
            r = GoodsReceipt.objects.filter(pk=where["receipt_id"], company=company).first()
            if r is not None and r.currency != "INR":
                raise ValidationError(
                    {
                        "detail": "An import's bill is entered with its bill of entry, "
                        "which comes later."
                    }
                )
        if lines:
            first = lines[0]
            lines = [
                rl
                for rl in lines
                if rl.receipt.supplier_id == first.receipt.supplier_id
                and rl.receipt.branch_id == first.receipt.branch_id
            ]
        return Response(_text(_draft_from(company, lines)))


class UnbilledView(APIView):
    """GET: "Goods received, not billed": submitted rupee receipts with lines still to bill."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        by_receipt: dict[int, dict] = {}
        for rl in _open_receipt_lines(company):
            r = rl.receipt
            row = by_receipt.setdefault(
                r.pk,
                {
                    "receipt": r.pk,
                    "receipt_number": r.number,
                    "receipt_date": r.receipt_date,
                    "supplier_name": r.supplier.name,
                    "branch_name": r.branch.name,
                    "orders": set(),
                    "lines": 0,
                    "value": ZERO,
                },
            )
            row["orders"].add(rl.order_line.order.number)
            row["lines"] += 1
            row["value"] += rl.value - rl.billed_value
        rows = []
        for row in by_receipt.values():
            row["orders"] = ", ".join(sorted(row["orders"]))
            rows.append(row)
        return Response(_text(rows))


# Something else may not change once billed ------------------------------------


def receipt_billed(r: GoodsReceipt) -> str:
    """Why a receipt cannot be cancelled: the invoices that billed it."""
    numbers = (
        PurchaseInvoice.objects.filter(receipts=r, status=PurchaseInvoice.SUBMITTED)
        .values_list("number", flat=True)
        .distinct()
    )
    return ", ".join(numbers)
