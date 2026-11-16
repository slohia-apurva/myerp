"""Rate changes on a bill already entered (Sidharth, 2026-11-16, previews
78/79): a Debit Note "Rate charged higher" when the price comes down, a
Supplementary Bill when it goes up. Neither moves quantity: the difference
goes onto the receipt's stock still on hand (its lots are revalued) and the
part already used to "Purchase Price Difference", as a bill at a different
rate than its receipt does (buying/invoices.py). GST follows the bill line's
rate.

This module holds what both share: how much of a bill line a rate change can
cover, the draft lines, the saving checks and the GL lines.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from buying.api import _plain
from buying.invoices import _gst, _lots, _side, rate_split, system_ledger
from buying.models import DebitNote, DebitNoteLine, PurchaseInvoice, PurchaseInvoiceLine
from buying.receipts import _factor
from posting import accounts
from posting.service import GLLine, money

ZERO = Decimal("0")
DOWN, UP = -1, 1


def kept_qty(il: PurchaseInvoiceLine) -> Decimal:
    """What of a bill line we kept: billed less what debit notes took back as returned."""
    back = (
        DebitNoteLine.objects.filter(
            invoice_line=il, note__status=DebitNote.SUBMITTED, return_line__isnull=False
        ).aggregate(q=Sum("qty"))["q"]
        or ZERO
    )
    return max(il.qty - back, ZERO)


def in_stock(il: PurchaseInvoiceLine) -> Decimal:
    """How much of the receipt's goods is still on hand, in the bill's unit."""
    factor = _factor(il.item, il.unit_id)
    left = sum((lot.qty_left for lot in _lots(il.receipt_line)), ZERO)
    return left / factor if factor else ZERO


def regular_bill(inv: PurchaseInvoice | None, field: str = "invoice") -> PurchaseInvoice:
    if inv is None or inv.status != PurchaseInvoice.SUBMITTED:
        raise ValidationError({field: ["Pick a submitted purchase invoice of this company."]})
    if inv.kind != PurchaseInvoice.REGULAR:
        raise ValidationError(
            {field: ["Pick the original purchase invoice, not a supplementary bill."]}
        )
    return inv


def draft_lines(inv: PurchaseInvoice) -> list[dict]:
    """Every line of the bill at the quantity kept and the bill's rate, for
    the new rate to be typed in."""
    out = []
    for il in inv.lines.select_related("item", "unit", "receipt_line"):
        kept = kept_qty(il)
        if kept <= 0:
            continue
        out.append(
            {
                "invoice_line": il.pk,
                "item": il.item_id,
                "item_name": il.item.name,
                "hsn": il.item.hsn,
                "unit_name": il.unit.short_name or il.unit.name,
                "billed_qty": _plain(il.qty),
                "left_qty": _plain(kept),
                "in_stock": _plain(min(in_stock(il), kept)),
                "qty": _plain(kept),
                "rate": _plain(il.rate),
                "new_rate": _plain(il.rate),
                "gst_rate": _plain(il.gst_rate),
            }
        )
    return out


def checked_lines(inv: PurchaseInvoice, lines: list[dict], way: int) -> list[dict]:
    """The lines whose rate moved the right way, checked, with their tax."""
    rows, errors = [], []
    for n, line in enumerate(lines, start=1):
        qty, new_rate = line.get("qty") or ZERO, line.get("new_rate")
        il = (
            inv.lines.select_related("item", "unit", "receipt_line")
            .filter(pk=line["invoice_line"])
            .first()
        )
        if il is None:
            errors.append(f"Line {n}: pick a line of {inv.number}.")
            continue
        if not qty or new_rate is None or new_rate == il.rate:
            continue
        if way == DOWN and new_rate > il.rate:
            errors.append(
                f"Line {n}: {il.item.name} was billed at {_plain(il.rate)}; a higher rate "
                "needs a Supplementary Bill, not a debit note."
            )
            continue
        if way == UP and new_rate < il.rate:
            errors.append(
                f"Line {n}: {il.item.name} was billed at {_plain(il.rate)}; a lower rate "
                "needs a Debit Note (rate charged higher)."
            )
            continue
        kept = kept_qty(il)
        if qty > kept:
            errors.append(
                f"Line {n}: only {_plain(kept)} {il.unit.short_name} of {il.item.name} "
                "was billed and kept."
            )
            continue
        taxable = money(qty * abs(il.rate - new_rate))
        cgst, sgst, igst = _gst(taxable, il.gst_rate, inv.interstate)
        rows.append(
            {
                "il": il,
                "qty": qty,
                "new_rate": new_rate,
                "taxable": taxable,
                "cgst": cgst,
                "sgst": sgst,
                "igst": igst,
                "amount": taxable + cgst + sgst + igst,
            }
        )
    if errors:
        raise ValidationError({"lines": errors})
    return rows


def plan(doc, lines, way: int, preview: bool = False):
    """The stock and price-difference GL lines (signed by `way`), the
    revaluations and each line's split. `lines` have invoice_line, qty and
    taxable."""
    company = doc.company
    gl, revalue, per_line, by_ledger, used_total = [], [], {}, {}, ZERO
    for ln in lines:
        il = ln.invoice_line if hasattr(ln, "invoice_line") else ln.original_line
        on_hand, used, parts = rate_split(il, ln.qty, way * ln.taxable)
        revalue += parts
        per_line[ln.pk] = (on_hand, used)
        used_total += used
        if on_hand:
            led = accounts.stock_ledger(company, il.item)
            by_ledger.setdefault(led.pk, [led, ZERO])[1] += on_hand
    word = "less" if way == DOWN else "more"
    for led, value in by_ledger.values():
        gl.append(_side(led, value, f"Stock still on hand now costs {word}"))
    if used_total:
        gl.append(
            _side(
                system_ledger(company, accounts.PRICE_DIFFERENCE, preview),
                used_total,
                "Goods already used or sold",
            )
        )
    return gl, revalue, per_line


def gst_lines(doc, way: int, preview: bool) -> list[GLLine]:
    out = []
    why = "Input GST reversed" if way == DOWN else "Input GST on the extra charge"
    for code, value in (
        (accounts.INPUT_CGST, doc.cgst_total),
        (accounts.INPUT_SGST, doc.sgst_total),
        (accounts.INPUT_IGST, doc.igst_total),
    ):
        if value:
            out.append(_side(system_ledger(doc.company, code, preview), way * value, why))
    return out
