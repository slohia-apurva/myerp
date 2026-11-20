"""Credit notes (Entry > Sales > Credit Note): a GST credit note against a
submitted sales invoice (Sidharth, 2026-11-21, previews 18a/18b/18c in
mockups/sales). Made from the invoice ("Create ▾ › Credit Note"), with a Type:

* "Sales Return – goods come back": a quantity per batch that went out, at the
  invoice's rate and GST, into a bin of the invoice's Despatch From branch.
  Submit puts the goods back in that batch at the cost they left at (FIFO cost
  of the delivery note): Dr Stock, Cr Cost of Goods Sold.
* "Sales Return – goods not coming back": the same credit with no stock: the
  goods stay with the customer and their cost stays in Cost of Goods Sold.
* "Rate Difference": the billed quantity (less what was returned) at a lower
  rate: only the sale value and its GST come down.

Every type posts Dr each item group's "Sales Ledger" and Output CGST / SGST /
IGST, Cr the customer, with the rounding to Round Off. The invoice's due dates
come down by the note ("Invoice Due After This Note"), the latest first.

A return never takes more than was billed less what earlier notes returned
(per batch, what went out of it); a rate difference starts from the rate left
after earlier rate differences. Only submitted notes count; Submit checks again
with the invoice locked. Returns do not change the sales order's delivered
quantity (as on the purchase side). The e-invoice (document type CRN) is made
from the JSON on the portal, and its IRN typed in or read from the portal's file.

Who may do what: sales rights (sales.view, create, submit, cancel).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import _branch_address, _letterhead, _money, _plain
from core import attachments, india, numbering, words
from core.api import Signed
from core.companies import visible_companies
from core.models import Ledger, WarehouseLocation
from posting import accounts, service
from posting import api as posting_api
from posting.service import GLLine, StockLine, Voucher
from selling import invoices as inv_api
from selling.api import _company, _split
from selling.models import CreditNote, CreditNoteLine, DeliveryNoteBin, SalesInvoice
from selling.picking import factor as unit_factor
from tenancy.context import tenant_atomic

KIND = "credit_note"
ZERO = Decimal("0")
RUPEE = Decimal("1")
RETURNS = (CreditNote.GOODS_BACK, CreditNote.GOODS_KEPT)
RATE_CENTS = Decimal("0.000001")


def may(user, action: str) -> bool:
    return user.can(f"sales.{action}")


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with credit notes.")


# What is left to credit ----------------------------------------------------------


def _submitted_lines(**where):
    return CreditNoteLine.objects.filter(note__status=CreditNote.SUBMITTED, **where)


def returned(il, note: CreditNote | None = None) -> Decimal:
    """What submitted notes (other than this one) returned of an invoice line."""
    rows = _submitted_lines(invoice_line=il, note__kind__in=RETURNS)
    if note is not None and note.pk:
        rows = rows.exclude(note=note)
    return rows.aggregate(q=Sum("qty"))["q"] or ZERO


def rate_left(il, note: CreditNote | None = None) -> Decimal:
    """The line's rate after earlier rate differences."""
    rows = _submitted_lines(invoice_line=il, note__kind=CreditNote.RATE)
    if note is not None and note.pk:
        rows = rows.exclude(note=note)
    return il.rate - (rows.aggregate(r=Sum("rate"))["r"] or ZERO)


def batches_sent(il) -> list[dict]:
    """The batches an invoice line's goods went out in (from its delivery note
    line's bins): quantity in the line's unit, its cost, and the first bin."""
    f = unit_factor(il.note_line.order_line)
    found: dict = {}
    bins = DeliveryNoteBin.objects.filter(line=il.note_line, qty__gt=0).select_related(
        "batch", "location"
    )
    for b in bins.order_by("id"):
        row = found.setdefault(
            b.batch_id,
            {"batch": b.batch, "stock_qty": ZERO, "cost": ZERO, "location": b.location},
        )
        row["stock_qty"] += b.qty
        row["cost"] += b.cost
    out = []
    for row in found.values():
        row["qty"] = row["stock_qty"] / f
        row["factor"] = f
        out.append(row)
    return out


def _sent_of(ln: CreditNoteLine) -> dict | None:
    return next((b for b in batches_sent(ln.invoice_line) if b["batch"] == ln.batch), None)


def back_of_batch(il, batch, note: CreditNote | None = None) -> Decimal:
    rows = _submitted_lines(invoice_line=il, batch=batch, note__kind=CreditNote.GOODS_BACK)
    if note is not None and note.pk:
        rows = rows.exclude(note=note)
    return rows.aggregate(q=Sum("qty"))["q"] or ZERO


def _stock_item(ln) -> bool:
    return ln.item.maintain_stock


def most(ln: CreditNoteLine) -> Decimal:
    """The most this line can return now."""
    note, il = ln.note, ln.invoice_line
    left = il.qty - returned(il, note)
    if note.kind == CreditNote.GOODS_BACK and _stock_item(ln):
        sent = _sent_of(ln)
        if sent is None:
            return ZERO
        left = min(left, sent["qty"] - back_of_batch(il, ln.batch, note))
    return max(left, ZERO)


# Reading ---------------------------------------------------------------------------


def _notes(company):
    return CreditNote.objects.filter(company=company).select_related(
        "company",
        "customer__party",
        "invoice",
        "branch",
        "bill_from",
        "created_by",
        "submitted_by",
    )


def _line_out(ln: CreditNoteLine) -> dict:
    il = ln.invoice_line
    note = ln.note
    row = {
        "id": ln.pk,
        "position": ln.position,
        "invoice_line": il.pk,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "hsn": ln.item.hsn,
        "unit_name": inv_api._unit_name(ln.unit),
        "billed_qty": _plain(il.qty),
        "bill_rate": _plain(il.rate),
        "batch": ln.batch_id,
        "batch_number": ln.batch.number if ln.batch_id else "",
        "location": ln.location_id,
        "location_name": str(ln.location) if ln.location_id else "",
        "keeps_stock": _stock_item(ln),
        "qty": _plain(ln.qty),
        "rate": _plain(ln.rate),
        "new_rate": _plain(ln.new_rate),
        "taxable": str(ln.taxable),
        "gst_rate": _plain(ln.gst_rate),
        "cgst": str(ln.cgst),
        "sgst": str(ln.sgst),
        "igst": str(ln.igst),
        "amount": str(ln.amount),
        "cost": str(ln.cost),
    }
    if note.status == CreditNote.DRAFT:
        row["returned"] = _plain(returned(il, note))
        row["most"] = _plain(most(ln))
        row["rate_left"] = _plain(rate_left(il, note))
        if note.kind == CreditNote.GOODS_BACK and _stock_item(ln):
            sent = _sent_of(ln)
            row["sent"] = _plain(sent["qty"]) if sent else "0"
            row["sent_from"] = str(sent["location"]) if sent else ""
            row["cost_rate"] = (
                _plain((sent["cost"] / sent["qty"]).quantize(Decimal("0.01")))
                if sent and sent["qty"]
                else ""
            )
    return row


def _dues_after(note: CreditNote) -> list[dict]:
    """The invoice's due dates less its credit notes (this one included), taken
    off the latest due first."""
    inv = note.invoice
    others = (
        CreditNote.objects.filter(invoice=inv, status=CreditNote.SUBMITTED)
        .exclude(pk=note.pk)
        .aggregate(t=Sum("total"))["t"]
        or ZERO
    )
    mine = note.total if note.status != CreditNote.CANCELLED else ZERO
    less = others + mine
    rows = [{"due_date": d.due_date, "invoice": d.amount, "less": ZERO} for d in inv.dues.all()]
    for row in reversed(rows):
        take = min(row["invoice"], less)
        row["less"] = take
        less -= take
    return [
        {
            "due_date": r["due_date"],
            "invoice": str(r["invoice"]),
            "less": str(r["less"]),
            "now_due": str(r["invoice"] - r["less"]),
        }
        for r in rows
    ]


def _places(note: CreditNote) -> list[dict]:
    rows = WarehouseLocation.objects.filter(branch=note.branch, is_active=True).select_related(
        "parent__parent"
    )
    return [
        {"id": p.pk, "name": str(p), "is_default": p.is_default}
        for p in rows
        if p.kind != WarehouseLocation.RACK
    ]


def note_out(note: CreditNote, lines: bool = True) -> dict:
    inv = note.invoice
    party = note.customer.party
    data = {
        "id": note.pk,
        "company": note.company_id,
        "number": note.number,
        "status": note.status,
        "status_label": note.get_status_display(),
        "kind": note.kind,
        "kind_label": note.get_kind_display(),
        "reason": note.reason,
        "reason_label": note.get_reason_display(),
        "customer": note.customer_id,
        "customer_name": note.customer.name,
        "customer_gstin": (inv.bill_address or {}).get("gstin") or (party.gstin if party else ""),
        "invoice": inv.pk,
        "invoice_number": inv.number,
        "invoice_date": inv.invoice_date,
        "invoice_total": str(inv.total),
        "branch": note.branch_id,
        "branch_name": note.branch.name,
        "bill_from_name": note.bill_from.name if note.bill_from else "",
        "note_date": note.note_date,
        "customer_ref": note.customer_ref,
        "remarks": note.remarks,
        "place_of_supply_name": (
            f"{note.place_of_supply} - {india.STATES.get(note.place_of_supply, '')}"
            if note.place_of_supply
            else "Outside India"
        ),
        "interstate": note.interstate,
        "taxable_total": str(note.taxable_total),
        "cgst_total": str(note.cgst_total),
        "sgst_total": str(note.sgst_total),
        "igst_total": str(note.igst_total),
        "round_off": str(note.round_off),
        "total": str(note.total),
        "cost_total": str(note.cost_total),
        "irn": note.irn,
        "ack_no": note.ack_no,
        "ack_date": note.ack_date,
        "has_signed_qr": bool(note.signed_qr),
        "needs_einvoice": inv_api.einvoice_party(party),
        "cancel_reason": note.cancel_reason,
        "created_by_name": note.created_by.display_name if note.created_by else "",
        "created_at": note.created_at,
        "submitted_at": note.submitted_at,
        "submitted_by_name": note.submitted_by.display_name if note.submitted_by else "",
    }
    if lines:
        rows = note.lines.select_related(
            "item", "unit", "batch", "location__parent__parent", "invoice_line__note_line"
        )
        data["lines"] = [_line_out(ln) for ln in rows]
        data["dues_after"] = _dues_after(note)
        if note.status == CreditNote.DRAFT and note.kind == CreditNote.GOODS_BACK:
            data["places"] = _places(note)
    return data


def _fresh(note: CreditNote) -> dict:
    return note_out(_notes(note.company).get(pk=note.pk))


def brief(note: CreditNote) -> dict:
    """What the invoice shows of its credit notes."""
    return {
        "id": note.pk,
        "number": note.number,
        "status": note.status,
        "status_label": note.get_status_display(),
        "kind_label": note.get_kind_display(),
        "note_date": note.note_date,
        "total": str(note.total),
    }


# Making one from an invoice --------------------------------------------------------


def _fill(note: CreditNote) -> None:
    """The note's lines for its type, all at nil: a quantity (or the correct
    rate) is given on the form."""
    note.lines.all().delete()
    rows: list[CreditNoteLine] = []
    inv = note.invoice
    for il in inv.lines.select_related("item", "unit", "note_line__order_line").order_by(
        "position"
    ):
        base = {
            "note": note,
            "invoice_line": il,
            "item": il.item,
            "unit": il.unit,
            "gst_rate": il.gst_rate,
        }
        if note.kind == CreditNote.RATE:
            left = il.qty - returned(il, note)
            if left > 0:
                rows.append(
                    CreditNoteLine(
                        **base,
                        position=len(rows) + 1,
                        qty=left,
                        new_rate=rate_left(il, note),
                    )
                )
        elif note.kind == CreditNote.GOODS_BACK and il.item.maintain_stock:
            for sent in batches_sent(il):
                rows.append(
                    CreditNoteLine(
                        **base,
                        position=len(rows) + 1,
                        batch=sent["batch"],
                        location=sent["location"],
                        rate=il.rate,
                    )
                )
        else:
            rows.append(CreditNoteLine(**base, position=len(rows) + 1, rate=il.rate))
    CreditNoteLine.objects.bulk_create(rows)
    _totals(note, rows)
    note.save()


def make(inv: SalesInvoice, kind: str, user) -> CreditNote:
    note = CreditNote.objects.create(
        company=inv.company,
        customer=inv.customer,
        invoice=inv,
        branch=inv.branch,
        bill_from=inv.bill_from,
        kind=kind,
        reason="rate_lower" if kind == CreditNote.RATE else "damaged",
        note_date=max(timezone.localdate(), inv.invoice_date),
        place_of_supply=inv.place_of_supply,
        interstate=inv.interstate,
        created_by=user,
    )
    _fill(note)
    return note


# Saving a draft ----------------------------------------------------------------


def _price(ln: CreditNoteLine, interstate: bool) -> None:
    ln.taxable = _money(ln.qty * ln.rate)
    ln.cgst, ln.sgst, ln.igst = _split(_money(ln.taxable * ln.gst_rate / 100), interstate)
    ln.amount = ln.taxable + ln.cgst + ln.sgst + ln.igst


def _totals(note: CreditNote, lines) -> None:
    note.taxable_total = sum((x.taxable for x in lines), ZERO)
    note.cgst_total = sum((x.cgst for x in lines), ZERO)
    note.sgst_total = sum((x.sgst for x in lines), ZERO)
    note.igst_total = sum((x.igst for x in lines), ZERO)
    exact = note.taxable_total + note.cgst_total + note.sgst_total + note.igst_total
    note.total = exact.quantize(RUPEE, rounding="ROUND_HALF_UP")
    note.round_off = note.total - exact


class LineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, required=False, min_value=0)
    location = serializers.IntegerField(required=False, allow_null=True)
    new_rate = serializers.DecimalField(
        max_digits=18, decimal_places=6, required=False, allow_null=True, min_value=0
    )


class NoteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=CreditNote.KINDS)
    reason = serializers.ChoiceField(choices=CreditNote.REASONS)
    note_date = serializers.DateField()
    customer_ref = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    remarks = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _set_line(ln: CreditNoteLine, given: dict, note: CreditNote, places: dict) -> list[str]:
    errors: list[str] = []
    label = f"Line {ln.position} ({ln.item.name})"
    if note.kind == CreditNote.RATE:
        if given.get("new_rate") is None:
            return errors
        left = rate_left(ln.invoice_line, note)
        new = given["new_rate"]
        if new > left:
            errors.append(
                f"{label}: the correct rate cannot be more than the rate billed "
                f"({_plain(left)}); a higher rate needs a supplementary invoice."
            )
            return errors
        ln.new_rate = new
        ln.rate = left - new
        ln.qty = max(ln.invoice_line.qty - returned(ln.invoice_line, note), ZERO)
    else:
        if "qty" in given:
            qty = given["qty"]
            top = most(ln)
            if qty > top:
                errors.append(
                    f"{label}: at most {_plain(top)} {inv_api._unit_name(ln.unit)} "
                    "can be returned (billed, less what earlier notes returned)."
                )
                return errors
            ln.qty = qty
        if note.kind == CreditNote.GOODS_BACK and _stock_item(ln) and "location" in given:
            loc = places.get(given["location"]) if given["location"] else None
            if given["location"] and loc is None:
                errors.append(f"{label}: pick a bin of {note.branch} from the list.")
            else:
                ln.location = loc
        ln.rate = ln.invoice_line.rate
    _price(ln, note.interstate)
    return errors


def _save(note: CreditNote, data: dict) -> None:
    inv = note.invoice
    if data["note_date"] < inv.invoice_date:
        raise ValidationError(
            {
                "note_date": [
                    f"The invoice is dated {inv.invoice_date:%d-%m-%Y}; "
                    "date the credit note on or after it."
                ]
            }
        )
    note.note_date = data["note_date"]
    note.reason = data["reason"]
    note.customer_ref = data.get("customer_ref", "").strip()
    note.remarks = data.get("remarks", "").strip()
    if data["kind"] != note.kind:
        note.kind = data["kind"]
        note.save()
        _fill(note)  # a new type starts from fresh lines; what was typed is dropped
        return
    places = {
        p.pk: p
        for p in WarehouseLocation.objects.filter(branch=note.branch, is_active=True).exclude(
            kind=WarehouseLocation.RACK
        )
    }
    lines = list(
        note.lines.select_related("item", "unit", "batch", "invoice_line__note_line__order_line")
    )
    by_id = {ln.pk: ln for ln in lines}
    errors: list[str] = []
    for given in data.get("lines", []):
        ln = by_id.get(given["id"])
        if ln is None:
            errors.append("A line is not on this credit note: open it again.")
            continue
        errors += _set_line(ln, given, note, places)
    if errors:
        raise ValidationError({"lines": errors})
    CreditNoteLine.objects.bulk_update(
        lines,
        [
            "qty",
            "rate",
            "new_rate",
            "location",
            "taxable",
            "cgst",
            "sgst",
            "igst",
            "amount",
        ],
    )
    _totals(note, lines)
    note.save()


# Posting -------------------------------------------------------------------------


def _credited(note: CreditNote) -> list[CreditNoteLine]:
    return [
        ln
        for ln in note.lines.select_related(
            "item__item_group", "unit", "batch", "location", "invoice_line__note_line__order_line"
        )
        if ln.taxable > 0 or (note.kind != CreditNote.RATE and ln.qty > 0)
    ]


def _comes_back(note: CreditNote, ln: CreditNoteLine) -> bool:
    return note.kind == CreditNote.GOODS_BACK and _stock_item(ln) and ln.qty > 0


def _needs(note: CreditNote) -> list[tuple[str, object, tuple]]:
    both = (accounts.SALES, accounts.STOCK, accounts.COGS)
    return [
        (
            f"Line {ln.position}",
            ln.item,
            both if _comes_back(note, ln) else (accounts.SALES,),
        )
        for ln in _credited(note)
    ]


def ledgers_refusal(note: CreditNote, user) -> dict | None:
    rows: dict[int, dict] = {}
    for label, item, needs in _needs(note):
        for r in accounts.missing_accounts(note.company, [(0, item)], needs):
            row = rows.setdefault(r["group"], {**r, "missing": [], "lines": []})
            row["missing"] += [m for m in r["missing"] if m not in row["missing"]]
            text = f"{label} {item.name}"
            if text not in row["lines"]:
                row["lines"].append(text)
    if not rows:
        return None
    names = ", ".join(r["group_name"] for r in rows.values())
    return {
        "detail": f"Set the ledgers of item group {names} for {note.company} "
        "(Masters > Item groups) before Submit.",
        "missing_accounts": list(rows.values()),
        "may_set": user.can("masters.edit"),
        "company": note.company.pk,
    }


def _stock_rate(ln: CreditNoteLine) -> Decimal:
    """The cost per stock unit the goods left at, in their batch."""
    sent = _sent_of(ln)
    if not sent or not sent["stock_qty"]:
        return ZERO
    return (sent["cost"] / sent["stock_qty"]).quantize(RATE_CENTS)


def _sales_gl(note: CreditNote, lines: list[CreditNoteLine]) -> list[GLLine]:
    company = note.company
    sales: dict[int, list] = {}
    for ln in lines:
        led = accounts.sales_ledger(company, ln.item)
        sales.setdefault(led.pk, [led, ZERO])[1] += ln.taxable
    why = f"Credit note against {note.invoice.number}"
    gl = [GLLine(led, debit=v, remarks=why) for led, v in sales.values() if v]
    for code, value in (
        (accounts.OUTPUT_CGST, note.cgst_total),
        (accounts.OUTPUT_SGST, note.sgst_total),
        (accounts.OUTPUT_IGST, note.igst_total),
    ):
        if value:
            gl.append(GLLine(accounts.system_ledger(company, code), debit=value))
    if note.round_off:
        gl.append(
            inv_api._side(accounts.system_ledger(company, accounts.ROUND_OFF), note.round_off)
        )
    gl.append(GLLine(note.customer, credit=note.total, remarks=why))
    return gl


def _check_left(note: CreditNote, lines: list[CreditNoteLine]) -> None:
    """Submit checks the limits again, with the invoice locked, against notes
    submitted since the draft was saved."""
    errors = []
    for ln in lines:
        if note.kind == CreditNote.RATE:
            if ln.rate > rate_left(ln.invoice_line, note):
                errors.append(f"Line {ln.position}: the rate was reduced since; open it again.")
        elif ln.qty > most(ln):
            errors.append(
                f"Line {ln.position} ({ln.item.name}): only {_plain(most(ln))} is left to return."
            )
        if _comes_back(note, ln) and ln.location_id is None:
            errors.append(f"Line {ln.position} ({ln.item.name}): pick the bin it comes back into.")
    if errors:
        raise ValidationError({"detail": "This credit note cannot be submitted.", "lines": errors})


def refused(note: CreditNote, user) -> Response | None:
    if not may(user, "submit"):
        return None
    if found := attachments.refuse_submit(note, KIND):
        return found
    if refusal := ledgers_refusal(note, user):
        return Response({**refusal, "id": note.pk}, status=400)
    return None


def _submit(note: CreditNote, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    inv = SalesInvoice.objects.select_for_update().get(pk=note.invoice_id)
    if inv.status != SalesInvoice.SUBMITTED:
        raise ValidationError({"detail": f"Invoice {inv.number or 'draft'} is not submitted."})
    attachments.require_file(note, KIND)
    lines = _credited(note)
    if not lines:
        raise ValidationError(
            {
                "detail": "Nothing is credited: give a quantity"
                + (" or a lower rate" if note.kind == CreditNote.RATE else "")
                + " on at least one line."
            }
        )
    _check_left(note, lines)
    if refusal := ledgers_refusal(note, user):
        raise accounts.AccountsMissing(refusal)
    # Lines left at nil are dropped, so the note and its print carry only what it credits.
    note.lines.exclude(pk__in=[ln.pk for ln in lines]).delete()
    for k, ln in enumerate(lines, start=1):
        ln.position = k
    _totals(note, lines)
    note.number = numbering.next_document_number(
        note.company, KIND, note.note_date, note.bill_from or note.branch
    )
    back = [ln for ln in lines if _comes_back(note, ln)]
    moves = [
        StockLine(
            ln.item,
            ln.location,
            ln.qty * unit_factor(ln.invoice_line.note_line.order_line),
            rate=_stock_rate(ln),
            batch=ln.batch,
        )
        for ln in back
    ]
    company = note.company

    def gl(values):
        rows = _sales_gl(note, lines)
        stock: dict[int, list] = {}
        cogs: dict[int, list] = {}
        for ln, value in zip(back, values, strict=True):
            ln.cost = value
            led = accounts.stock_ledger(company, ln.item)
            stock.setdefault(led.pk, [led, ZERO])[1] += value
            led = accounts.cogs_ledger(company, ln.item)
            cogs.setdefault(led.pk, [led, ZERO])[1] += value
        rows += [
            GLLine(led, debit=v, remarks="Goods back from the customer")
            for led, v in stock.values()
        ]
        rows += [
            GLLine(led, credit=v, remarks="Cost of goods returned") for led, v in cogs.values()
        ]
        return rows

    voucher = Voucher(company, note.branch, note.note_date, KIND, note.pk, note.number, user)
    service.post(voucher, stock=moves, gl=gl)
    CreditNoteLine.objects.bulk_update(lines, ["position", "cost"])
    note.cost_total = sum((ln.cost for ln in back), ZERO)
    note.status = CreditNote.SUBMITTED
    note.submitted_at = timezone.now()
    note.submitted_by = user
    note.save()


def _cancel(note: CreditNote, user, reason: str) -> None:
    if note.status == CreditNote.SUBMITTED:
        service.cancel(KIND, note.pk, user)
    note.status = CreditNote.CANCELLED
    note.cancel_reason = reason[:200]
    note.save()


def _posting_preview(note: CreditNote) -> dict:
    """What Submit will post; a ledger not yet set shows as missing."""
    company = note.company
    lines = _credited(note)
    sums: dict[object, list] = {}
    ledgers: dict[object, Ledger | None] = {}

    def add(fn, item, label, debit=ZERO, credit=ZERO):
        try:
            led = fn(company, item)
            key = led.pk
            ledgers[key] = led
        except ValidationError:
            key = f"{label} of item group {accounts.main_group(item)} not set"
            ledgers[key] = None
        row = sums.setdefault(key, [ZERO, ZERO])
        row[0] += debit
        row[1] += credit

    for ln in lines:
        add(accounts.sales_ledger, ln.item, "Sales Ledger", debit=ln.taxable)

    def row(key):
        led = ledgers[key]
        d, c = sums[key]
        return posting_api.ledger_row(led, d, c, "" if led else str(key))

    rows = [row(k) for k in sums]
    for code, value in (
        (accounts.OUTPUT_CGST, note.cgst_total),
        (accounts.OUTPUT_SGST, note.sgst_total),
        (accounts.OUTPUT_IGST, note.igst_total),
    ):
        if value:
            rows.append(posting_api.ledger_row(accounts.system_ledger(company, code), debit=value))
    if note.round_off:
        led = accounts.system_ledger(company, accounts.ROUND_OFF)
        rows.append(
            posting_api.ledger_row(led, debit=note.round_off)
            if note.round_off > 0
            else posting_api.ledger_row(led, credit=-note.round_off)
        )
    rows.append(posting_api.ledger_row(note.customer, credit=note.total))
    sums.clear()
    cost = ZERO
    for ln in lines:
        if _comes_back(note, ln):
            f = unit_factor(ln.invoice_line.note_line.order_line)
            value = _money(ln.qty * f * _stock_rate(ln))
            cost += value
            add(accounts.stock_ledger, ln.item, "Stock Ledger", debit=value)
            add(accounts.cogs_ledger, ln.item, "COGS/Expense Ledger", credit=value)
    rows += [row(k) for k in sums]
    if note.kind == CreditNote.GOODS_BACK:
        text = (
            f"The goods go back into stock at the cost they left at (₹{_money(cost)}), "
            "so Cost of Goods Sold comes down too. "
        )
    elif note.kind == CreditNote.GOODS_KEPT:
        text = "No stock moves: the cost of these goods stays in Cost of Goods Sold. "
    else:
        text = "Only the sale value and its GST come down; no stock or cost moves. "
    return posting_api.preview(rows, text)


# The e-invoice JSON (NIC schema 1.1, document type CRN) -----------------------------


def einvoice_json(note: CreditNote) -> list[dict]:
    inv = note.invoice
    party = note.customer.party
    seller_place = _branch_address(note.bill_from or note.branch)
    bill = inv.bill_address or {}
    overseas = party.gst_type == party.OVERSEAS
    if overseas:
        kind = "EXPWP" if note.igst_total else "EXPWOP"
    elif party.gst_type == party.SEZ:
        kind = "SEZWP" if note.igst_total else "SEZWOP"
    else:
        kind = "B2B"
    seller = inv_api._place(note.company.name, seller_place, seller_place["gstin"])
    gstin = "URP" if overseas else (bill.get("gstin") or party.gstin)
    buyer = inv_api._place(note.customer.name, bill, gstin)
    buyer["Pos"] = "96" if overseas else note.place_of_supply
    if overseas:
        buyer["Stcd"], buyer["Pin"] = "96", 999999
    num = inv_api._num
    items = []
    for k, ln in enumerate(note.lines.select_related("item", "unit"), start=1):
        items.append(
            {
                "SlNo": str(k),
                "PrdDesc": ln.item.name[:300],
                "IsServc": "Y" if ln.item.item_type == ln.item.SERVICE else "N",
                "HsnCd": ln.item.hsn,
                "Qty": num(round(ln.qty, 3)),
                "Unit": ln.unit.gst_code or "OTH",
                "UnitPrice": num(round(ln.rate, 3)),
                "TotAmt": num(ln.taxable),
                "Discount": 0,
                "AssAmt": num(ln.taxable),
                "GstRt": num(ln.gst_rate),
                "IgstAmt": num(ln.igst),
                "CgstAmt": num(ln.cgst),
                "SgstAmt": num(ln.sgst),
                "TotItemVal": num(ln.amount),
            }
        )
    return [
        {
            "Version": "1.1",
            "TranDtls": {"TaxSch": "GST", "SupTyp": kind, "RegRev": "N", "IgstOnIntra": "N"},
            "DocDtls": {
                "Typ": "CRN",
                "No": note.number,
                "Dt": note.note_date.strftime("%d/%m/%Y"),
            },
            "SellerDtls": seller,
            "BuyerDtls": buyer,
            "ItemList": items,
            "ValDtls": {
                "AssVal": num(note.taxable_total),
                "CgstVal": num(note.cgst_total),
                "SgstVal": num(note.sgst_total),
                "IgstVal": num(note.igst_total),
                "RndOffAmt": num(note.round_off),
                "TotInvVal": num(note.total),
            },
            "RefDtls": {
                "PrecDocDtls": [
                    {"InvNo": inv.number, "InvDt": inv.invoice_date.strftime("%d/%m/%Y")}
                ]
            },
        }
    ]


# Print ---------------------------------------------------------------------------


def print_data(note: CreditNote) -> dict:
    """The note in the shape of the invoice print (buying.po_pdf)."""
    from selling.api import _addresses_out

    inv = note.invoice
    data = _fresh(note)
    orders = inv_api.orders_of(inv_api.notes_of(inv))
    data["order_date"] = note.note_date
    data["doc_title"] = "CREDIT NOTE"
    data["currency"], data["currency_symbol"] = "INR", "₹"
    data["letterhead"] = _letterhead(note.company)
    data["addresses"] = _addresses_out(orders[0])
    data["addresses"]["bill_from"] = _branch_address(note.bill_from or note.branch)
    data["addresses"]["customer"].update(inv.bill_address or {})
    data["addresses"]["ship_to"] = {"name": note.customer.name, **data["addresses"]["customer"]}
    data["print_meta"] = [
        ("Place of Supply", data["place_of_supply_name"]),
        ("Type", data["kind_label"]),
        ("Reason", data["reason_label"]),
        ("Against Invoice", f"{inv.number} of {inv.invoice_date:%d-%m-%Y}"),
        ("Your Ref", note.customer_ref),
        ("IRN", note.irn),
        (
            "Ack No / Date",
            " · ".join(x for x in [note.ack_no, inv_api._dt(note.ack_date)] if x),
        ),
    ]
    # The invoice print's line shape: an item, its quantity and rate.
    data["lines"] = [
        {
            **ln,
            "rate": ln["rate"],
            "description": (
                f"Rate {ln['bill_rate']} → {ln['new_rate']}"
                if note.kind == CreditNote.RATE
                else (f"Batch {ln['batch_number']}" if ln["batch_number"] else "")
            ),
        }
        for ln in data["lines"]
    ]
    data["charges"] = []
    data["signed_qr"] = note.signed_qr
    data["qr_pending"] = (
        not note.signed_qr
        and note.status != CreditNote.CANCELLED
        and inv_api.einvoice_party(note.customer.party)
    )
    data["amount_words"] = words.amount(note.total, "INR", "Indian Rupee")
    data["submitted_by_signature"] = (
        note.submitted_by.signature_url()
        if note.submitted_by and note.status != CreditNote.DRAFT
        else ""
    )
    data["terms"] = ""
    return data


def note_pdf(note: CreditNote) -> bytes:
    from buying.po_pdf import order_pdf

    return order_pdf(print_data(note), "Original for Recipient")


# Views -----------------------------------------------------------------------


def _note(request, pk: int, lock: bool = False) -> CreditNote:
    rows = CreditNote.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    note = rows.select_related("company", "customer__party", "invoice", "branch").first()
    if note is None or "sales" not in note.company.modules:
        raise NotFound("No such credit note.")
    return note


VIEWS = (CreditNote.DRAFT, CreditNote.SUBMITTED, CreditNote.CANCELLED)


class NoteListView(APIView):
    """GET ?view=draft|submitted|cancelled|all: the company's credit notes."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        rows = _notes(company)
        view = request.query_params.get("view", "all")
        if view in VIEWS:
            rows = rows.filter(status=view)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(customer__name__icontains=word)
                | Q(invoice__number__icontains=word)
            )
        return Response([note_out(n, lines=False) for n in rows[:1000]])


class NoteFromInvoiceView(APIView):
    """POST {kind}: a draft credit note against a submitted invoice ("Create ▾ ›
    Credit Note"); the invoice's open draft if it has one."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        inv = inv_api._invoice(request, pk, lock=True)
        if inv.status != SalesInvoice.SUBMITTED:
            raise ValidationError({"detail": "A credit note is made against a submitted invoice."})
        draft = inv.credit_notes.filter(status=CreditNote.DRAFT).first()
        if draft is not None:
            return Response(_fresh(draft))
        kind = request.data.get("kind") or CreditNote.GOODS_BACK
        if kind not in dict(CreditNote.KINDS):
            raise ValidationError({"kind": ["Pick a type from the list."]})
        return Response(_fresh(make(inv, kind, request.user)), status=status.HTTP_201_CREATED)


class NoteDetailView(APIView):
    """GET one note; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(_fresh(_note(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        note = _note(request, pk, lock=True)
        if note.status != CreditNote.DRAFT:
            raise ValidationError(
                {
                    "detail": "A submitted credit note cannot be changed. "
                    "Cancel it and make a new one."
                }
            )
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(note, data)
        if data.get("submit"):
            if answer := refused(note, request.user):
                return answer
            _submit(note, request.user)
        return Response(_fresh(note))


class NoteSubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        note = _note(request, pk, lock=True)
        if note.status != CreditNote.DRAFT:
            raise ValidationError({"detail": "This credit note is not a draft."})
        if answer := refused(note, request.user):
            return answer
        _submit(note, request.user)
        return Response(_fresh(note))


class NoteCancelView(APIView):
    """POST {reason}: the entries (and any goods put back) are reversed."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        note = _note(request, pk, lock=True)
        if note.status == CreditNote.CANCELLED:
            raise ValidationError({"detail": "This credit note is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(note, request.user, reason)
        return Response(_fresh(note))


class EInvoiceSerializer(serializers.Serializer):
    irn = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    ack_no = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    ack_date = serializers.DateTimeField(required=False, allow_null=True)
    signed_qr = serializers.CharField(required=False, allow_blank=True, default="")


class NoteEInvoiceView(APIView):
    """POST: the IRN and acknowledgement as the portal gave them."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        note = _note(request, pk, lock=True)
        if note.status != CreditNote.SUBMITTED:
            raise ValidationError({"detail": "Submit the credit note first."})
        serializer = EInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        errors = {}
        irn = data["irn"].strip().lower()
        if irn and not re.fullmatch(r"[0-9a-f]{64}", irn):
            errors["irn"] = ["An IRN is 64 letters and digits (0-9, a-f), as on the portal."]
        ack = data["ack_no"].strip()
        if ack and not ack.isdigit():
            errors["ack_no"] = ["The acknowledgement number is digits only."]
        if errors:
            raise ValidationError(errors)
        note.irn, note.ack_no, note.ack_date = irn, ack, data.get("ack_date")
        if data["signed_qr"].strip():
            note.signed_qr = data["signed_qr"].strip()
        note.save()
        return Response(_fresh(note))


class NoteLedgerPostingView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        note = _note(request, pk)
        if note.status == CreditNote.DRAFT:
            return Response(_posting_preview(note))
        return Response(posting_api.posted(KIND, note.pk))


class NoteJsonView(APIView):
    """GET: the e-invoice JSON (document type CRN) to upload on the portal."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        note = _note(request, pk)
        if note.status != CreditNote.SUBMITTED:
            raise ValidationError(
                {"detail": "Submit the credit note first: the JSON needs its number."}
            )
        if not inv_api.einvoice_party(note.customer.party):
            raise ValidationError(
                {
                    "detail": f"{note.customer.name} is not a registered business, so this "
                    "credit note needs no e-invoice."
                }
            )
        body = json.dumps(einvoice_json(note), indent=2, ensure_ascii=False)
        response = HttpResponse(body, content_type="application/json")
        name = f"e-invoice-{note.number.replace('/', '-')}.json"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class NotePdfView(APIView):
    """GET (&download=1): the Credit Note in the GST format."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        note = _note(request, pk)
        response = HttpResponse(note_pdf(note), content_type="application/pdf")
        name = (note.number or "draft-credit-note").replace("/", "-")
        how = "attachment" if request.query_params.get("download") == "1" else "inline"
        response["Content-Disposition"] = f'{how}; filename="{name}.pdf"'
        return response


def invoice_credited(inv: SalesInvoice) -> list[dict]:
    return [brief(n) for n in inv.credit_notes.exclude(status=CreditNote.CANCELLED)]
