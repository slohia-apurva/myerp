"""Sales invoices (Entry > Sales > Sales Invoice): the tax invoice for one or
more submitted delivery notes (Sidharth, 2026-11-20, previews 14a/14b in
mockups/sales).

A draft is made from a note ("Create ▾ › Sales Invoice"); "Add Delivery Notes"
puts more of the customer's unbilled notes on it, so they go on one invoice and
one e-invoice. Notes go together only when they share the customer, Despatch
From, Bill From, the billing and shipping addresses and the credit term
(`match_key`). Quantities are what the notes sent; the rates, charges and
credit term are the orders' and cannot be changed on the invoice (Sidharth,
2026-11-20); an order's charges go on its first invoice. The transport details
come from the first note.

Submit (posting.service):
* Dr the customer for the total, with due dates from the credit term;
* Cr each item group's "Sales Ledger" for the items and charges, and Output
  CGST / SGST / IGST; the rounding to the rupee goes to Round Off;
* Dr Cost of Goods Sold, Cr "Goods Delivered but Bills not Made" for the
  note's FIFO cost (decided 2026-11-19), so cost and sale fall together.
Missing item group ledgers come back as for the goods receipt (posting.accounts)
for the screen's popup.

The e-invoice and e-way bill: until a provider's API is chosen, the invoice
gives the portal's JSON ("e-Invoice JSON") and the IRN, acknowledgement and
e-way bill numbers are typed in from the portal. The transport details can be
changed after Submit ("Update Transport"); they touch no ledger.

Who may do what: sales rights (sales.view, create, submit, cancel).
"""

from __future__ import annotations

import datetime
import json
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
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
from core.credit_terms import summary as term_summary
from core.models import Item, Ledger, Party
from posting import accounts, service
from posting import api as posting_api
from posting.service import GLLine, Voucher
from selling.api import _charges, _company, _split, charges_gst, place_state, source_words
from selling.models import (
    DeliveryNote,
    SalesInvoice,
    SalesInvoiceCharge,
    SalesInvoiceDue,
    SalesInvoiceLine,
)
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic

KIND = "sales_invoice"
ZERO = Decimal("0")
RUPEE = Decimal("1")
LIVE = (SalesInvoice.DRAFT, SalesInvoice.SUBMITTED)


def may(user, action: str) -> bool:
    return user.can(f"sales.{action}")


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with sales invoices.")


def _unit_name(unit) -> str:
    return unit.short_name or unit.name


def _dt(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%d-%m-%Y %I:%M %p")


# Reading ---------------------------------------------------------------------


def _invoices(company):
    return SalesInvoice.objects.filter(company=company).select_related(
        "company",
        "customer__party",
        "branch",
        "bill_from",
        "credit_term",
        "transporter",
        "created_by",
        "submitted_by",
    )


def _line_out(ln: SalesInvoiceLine) -> dict:
    ol = ln.note_line.order_line
    return {
        "id": ln.pk,
        "position": ln.position,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "description": ol.description,
        # The invoice and e-invoice carry the item's own code (a job-work service
        # its SAC); the challan carries the goods code.
        "hsn": ln.item.hsn,
        # The e-way bill carries the goods: a job-work service its Delivery HSN.
        "goods_hsn": ln.item.delivery_hsn or ln.item.hsn,
        "unit_name": _unit_name(ln.unit),
        "qty": _plain(ln.qty),
        "rate": _plain(ln.rate),
        "note_number": ln.note_line.note.number,
        "rate_source": source_words(ol.rate_source) if ol.rate_source else "",
        "taxable": str(ln.taxable),
        "gst_rate": _plain(ln.gst_rate),
        "cgst": str(ln.cgst),
        "sgst": str(ln.sgst),
        "igst": str(ln.igst),
        "amount": str(ln.amount),
        "cost": str(ln.cost),
    }


def _charge_out(c: SalesInvoiceCharge) -> dict:
    return {
        "id": c.pk,
        "item": c.item_id,
        "item_name": c.item.name,
        "sac": c.item.hsn,
        "basis": c.basis,
        "basis_label": c.get_basis_display(),
        "rate": _plain(c.rate),
        "amount": str(c.amount),
        "gst_rate": _plain(c.gst_rate),
        "cgst": str(c.cgst),
        "sgst": str(c.sgst),
        "igst": str(c.igst),
    }


def _due_rows(inv: SalesInvoice) -> list[dict]:
    """The credit term's parts as due dates, counted from the invoice date; the
    last part takes what is left."""
    total = inv.total or ZERO
    if not total:
        return []
    day = inv.invoice_date
    parts = list(inv.credit_term.parts.all()) if inv.credit_term else []
    if not parts:
        return [{"due_date": day, "amount": total}]
    rows, left = [], total
    for n, p in enumerate(parts):
        amount = left if n == len(parts) - 1 else _money(total * p.percent / 100)
        left -= amount
        rows.append({"due_date": day + datetime.timedelta(days=p.days), "amount": amount})
    return rows


def notes_of(inv: SalesInvoice) -> list[DeliveryNote]:
    return sorted(inv.delivery_notes.all(), key=lambda n: (n.note_date, n.number, n.pk))


def orders_of(notes: list[DeliveryNote]) -> list:
    found: dict = {}
    for n in notes:
        found.setdefault(n.order_id, n.order)
    return list(found.values())


def _joined(values) -> str:
    out: list[str] = []
    for v in values:
        if v and v not in out:
            out.append(v)
    return ", ".join(out)


def invoice_out(inv: SalesInvoice, lines: bool = True) -> dict:
    party = inv.customer.party
    dues = list(inv.dues.all()) if inv.status == SalesInvoice.SUBMITTED else []
    due_rows = [{"due_date": d.due_date, "amount": d.amount} for d in dues] or _due_rows(inv)
    notes = notes_of(inv)
    orders = orders_of(notes)
    data = {
        "id": inv.pk,
        "company": inv.company_id,
        "number": inv.number,
        "status": inv.status,
        "status_label": inv.get_status_display(),
        "customer": inv.customer_id,
        "customer_name": inv.customer.name,
        "customer_gstin": (inv.bill_address or {}).get("gstin") or (party.gstin if party else ""),
        "delivery_notes": [
            {
                "id": n.pk,
                "number": n.number,
                "note_date": n.note_date,
                "order": n.order_id,
                "order_number": n.order.number,
                "cost_total": str(n.cost_total),
            }
            for n in notes
        ],
        "delivery_note_number": _joined(n.number for n in notes),
        "orders": [{"id": o.pk, "number": o.number} for o in orders],
        "order_number": _joined(o.number for o in orders),
        "customer_po_no": _joined(o.customer_po_no for o in orders),
        "salesman_name": _joined(o.salesman.name for o in orders if o.salesman_id),
        "invoice_date": inv.invoice_date,
        "bill_from": inv.bill_from_id,
        "bill_from_name": inv.bill_from.name if inv.bill_from else "",
        "bill_from_gstin": (inv.bill_from.gstin if inv.bill_from else "") or inv.company.gstin,
        "bill_address": inv.bill_address,
        "ship_address": inv.ship_address,
        "place_of_supply": inv.place_of_supply,
        "place_of_supply_name": (
            f"{inv.place_of_supply} - {india.STATES.get(inv.place_of_supply, '')}"
            if inv.place_of_supply
            else "Outside India"
        ),
        "credit_term": inv.credit_term_id,
        "credit_term_name": inv.credit_term.name if inv.credit_term else "",
        "credit_term_summary": term_summary(inv.credit_term) if inv.credit_term else "",
        "dues": [{"due_date": d["due_date"], "amount": str(d["amount"])} for d in due_rows],
        "first_due": due_rows[0]["due_date"] if due_rows else None,
        "transporter": inv.transporter_id,
        "transporter_name": inv.transporter.name if inv.transporter else "By Customer",
        "transporter_gstin": inv.transporter.gstin if inv.transporter else "",
        "mode": inv.mode,
        "mode_label": inv.get_mode_display(),
        "vehicle_no": inv.vehicle_no,
        "distance_km": inv.distance_km,
        "lr_no": inv.lr_no,
        "lr_date": inv.lr_date,
        "packages": sum((n.packages or 0) for n in notes),
        "gross_weight": _plain(sum((n.gross_weight or ZERO for n in notes), ZERO)),
        "notes": inv.notes,
        "interstate": inv.interstate,
        "taxable_total": str(inv.taxable_total),
        "cgst_total": str(inv.cgst_total),
        "sgst_total": str(inv.sgst_total),
        "igst_total": str(inv.igst_total),
        "round_off": str(inv.round_off),
        "total": str(inv.total),
        "cost_total": str(inv.cost_total),
        "irn": inv.irn,
        "ack_no": inv.ack_no,
        "ack_date": inv.ack_date,
        "has_signed_qr": bool(inv.signed_qr),
        "eway_bill_no": inv.eway_bill_no,
        "eway_bill_date": inv.eway_bill_date,
        "eway_valid_until": inv.eway_valid_until,
        "needs_einvoice": einvoice_party(party),
        "eway_with_einvoice": eway_with_einvoice(inv),
        "cancel_reason": inv.cancel_reason,
        "created_by_name": inv.created_by.display_name if inv.created_by else "",
        "created_at": inv.created_at,
        "submitted_at": inv.submitted_at,
        "submitted_by_name": inv.submitted_by.display_name if inv.submitted_by else "",
    }
    if lines:
        rows = inv.lines.select_related("item", "unit", "note_line__order_line", "note_line__note")
        data["lines"] = [_line_out(ln) for ln in rows]
        data["charges"] = [_charge_out(c) for c in inv.charges.select_related("item")]
    return data


def _fresh(inv: SalesInvoice) -> dict:
    return invoice_out(_invoices(inv.company).get(pk=inv.pk))


def brief(inv: SalesInvoice | None) -> dict | None:
    """What a delivery note shows of its invoice."""
    if inv is None:
        return None
    return {
        "id": inv.pk,
        "number": inv.number,
        "status": inv.status,
        "status_label": inv.get_status_display(),
    }


def live_invoice(n: DeliveryNote) -> SalesInvoice | None:
    return next((i for i in n.invoices.all() if i.status in LIVE), None)


def eway_with_einvoice(inv: SalesInvoice) -> bool:
    """Whether the portal can make the e-way bill with the e-invoice: only for
    goods. An invoice of services alone (job work billed under its SAC) gets
    its e-way bill on the e-way bill portal, under the goods' Delivery HSN."""
    return inv.lines.exclude(item__item_type=Item.SERVICE).exists()


def einvoice_party(party: Party | None) -> bool:
    """An e-invoice is made for a registered business customer, an SEZ or an
    export; not for a consumer or an unregistered buyer."""
    return party is not None and (
        party.gst_type in Party.NEEDS_GSTIN or party.gst_type == Party.OVERSEAS
    )


# Making one from a delivery note -------------------------------------------------


def _price(ln, interstate: bool) -> None:
    ln.taxable = _money(ln.qty * ln.rate)
    ln.cgst, ln.sgst, ln.igst = _split(_money(ln.taxable * ln.gst_rate / 100), interstate)
    ln.amount = ln.taxable + ln.cgst + ln.sgst + ln.igst


def _totals(inv: SalesInvoice, lines: list, charges: list) -> None:
    both = [*lines, *charges]
    inv.taxable_total = sum((x.taxable for x in lines), ZERO) + sum(
        (c.amount for c in charges), ZERO
    )
    inv.cgst_total = sum((x.cgst for x in both), ZERO)
    inv.sgst_total = sum((x.sgst for x in both), ZERO)
    inv.igst_total = sum((x.igst for x in both), ZERO)
    exact = inv.taxable_total + inv.cgst_total + inv.sgst_total + inv.igst_total
    inv.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    inv.round_off = inv.total - exact


def term_of(n: DeliveryNote):
    """The credit term a note bills with: its order's, else the customer's."""
    party = n.customer.party
    return n.order.credit_term or (party.credit_term if party else None)


def _same(value) -> str:
    return json.dumps(value or {}, sort_keys=True, default=str)


def match_key(n: DeliveryNote) -> tuple:
    """What notes on one invoice must share: one customer, one despatch place and
    Bill From (one e-way bill, one series), one billing and shipping address and
    one credit term."""
    term = term_of(n)
    return (
        n.company_id,
        n.customer_id,
        n.branch_id,
        n.bill_from_id or n.order.bill_from_id,
        _same(n.order.bill_address),
        _same(n.ship_address),
        n.interstate,
        term.pk if term else None,
    )


def unbilled(company, customer_id) -> list[DeliveryNote]:
    """The customer's submitted notes that are on no live invoice."""
    return list(
        DeliveryNote.objects.filter(
            company=company, customer_id=customer_id, status=DeliveryNote.SUBMITTED
        )
        .exclude(invoices__status__in=LIVE)
        .select_related("order", "customer__party", "order__credit_term")
        .order_by("note_date", "number")
    )


def _billed_before(inv: SalesInvoice, order) -> bool:
    """Whether another live invoice bills a note of this order (and so carried
    its charges)."""
    others = SalesInvoice.objects.filter(delivery_notes__order=order, status__in=LIVE)
    return others.exclude(pk=inv.pk).exists()


def make(n: DeliveryNote, user) -> SalesInvoice:
    """A draft invoice for everything the note sent."""
    o = n.order
    party = n.customer.party
    bill = o.bill_address or {}
    with_gst = charges_gst(party)
    inv = SalesInvoice.objects.create(
        company=n.company,
        customer=n.customer,
        branch=n.branch,
        bill_from=n.bill_from or o.bill_from,
        invoice_date=max(timezone.localdate(), n.note_date),
        bill_address=bill,
        ship_address=n.ship_address,
        place_of_supply=place_state(party.state_code, bill) if with_gst else "",
        credit_term=term_of(n),
        transporter=n.transporter,
        mode=n.mode,
        vehicle_no=n.vehicle_no,
        distance_km=n.distance_km,
        lr_no=n.lr_no,
        lr_date=n.lr_date,
        interstate=n.interstate,
        created_by=user,
    )
    _fill(inv, [n])
    return inv


def _fill(inv: SalesInvoice, notes: list[DeliveryNote]) -> None:
    """The invoice's lines and charges for these notes, at the orders' rates."""
    notes = sorted(notes, key=lambda n: (n.note_date, n.number, n.pk))
    inv.delivery_notes.set(notes)
    inv.lines.all().delete()
    inv.charges.all().delete()
    lines, by_order = [], defaultdict(list)
    for n in notes:
        for nl in n.lines.select_related("item", "unit").filter(qty__gt=0).order_by("position"):
            ln = SalesInvoiceLine(
                invoice=inv,
                position=len(lines) + 1,
                note_line=nl,
                item=nl.item,
                unit=nl.unit,
                qty=nl.qty,
                rate=nl.rate,
                gst_rate=nl.gst_rate,
                cost=nl.cost,
            )
            _price(ln, inv.interstate)
            lines.append(ln)
            by_order[n.order_id].append(ln)
    SalesInvoiceLine.objects.bulk_create(lines)
    charges = []
    for o in orders_of(notes):
        if _billed_before(inv, o):
            continue
        given = [
            {"item": c.item, "basis": c.basis, "rate": c.rate, "gst_rate": c.gst_rate}
            for c in o.charges.select_related("item")
        ]
        if given:
            charges += _order_charges(inv, o, given, by_order[o.pk], len(charges))
    SalesInvoiceCharge.objects.bulk_create(charges)
    inv.cost_total = sum((n.cost_total for n in notes), ZERO)
    latest = max(n.note_date for n in notes)
    if inv.invoice_date < latest:
        inv.invoice_date = latest
    _totals(inv, lines, charges)
    inv.save()


def _order_charges(inv: SalesInvoice, o, given: list[dict], lines: list, before: int) -> list:
    """An order's charges worked out on its lines billed here (a share of the
    items' value or a rate per unit counts what is billed here)."""
    found = _charges(
        given,
        lines,
        o,
        charges_gst(inv.customer.party),
        inv.interstate,
        {"order_date": inv.invoice_date},
    )
    return [
        SalesInvoiceCharge(
            invoice=inv,
            position=before + k,
            item=c.item,
            basis=c.basis,
            rate=c.rate,
            amount=c.amount,
            gst_rate=c.gst_rate,
            cgst=c.cgst,
            sgst=c.sgst,
            igst=c.igst,
        )
        for k, c in enumerate(found, start=1)
    ]


# Saving a draft ----------------------------------------------------------------


class TransportSerializer(serializers.Serializer):
    transporter = serializers.IntegerField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=DeliveryNote.MODES, default=DeliveryNote.ROAD)
    vehicle_no = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    distance_km = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    lr_no = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    lr_date = serializers.DateField(required=False, allow_null=True)


class InvoiceSerializer(TransportSerializer):
    invoice_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    # The delivery notes to bill (the ones on it, plus any "Add Delivery Notes" picks).
    delivery_notes = serializers.ListField(child=serializers.IntegerField(), required=False)
    submit = serializers.BooleanField(required=False, default=False)


def _set_transport(inv: SalesInvoice, data: dict) -> None:
    transporter = None
    if data.get("transporter"):
        transporter = CourierAccount.objects.filter(
            pk=data["transporter"], company=inv.company
        ).first()
        if transporter is None:
            raise ValidationError({"transporter": ["Pick a transporter from the list."]})
        if not transporter.is_active and transporter.pk != inv.transporter_id:
            raise ValidationError({"transporter": [f"{transporter.name} is disabled."]})
    inv.transporter = transporter
    inv.mode = data.get("mode") or DeliveryNote.ROAD
    inv.vehicle_no = re.sub(r"[^A-Z0-9]", "", data.get("vehicle_no", "").upper())
    inv.distance_km = data.get("distance_km")
    inv.lr_no = data.get("lr_no", "").strip()
    inv.lr_date = data.get("lr_date")


def _pick_notes(inv: SalesInvoice, ids: list[int]) -> list[DeliveryNote]:
    """The notes asked for, each on this invoice already or unbilled and
    matching it."""
    if not ids:
        raise ValidationError({"delivery_notes": ["Keep at least one delivery note."]})
    have = {n.pk: n for n in inv.delivery_notes.select_related("order", "customer__party")}
    free = {n.pk: n for n in unbilled(inv.company, inv.customer_id)}
    first = next(iter(have.values()), None)
    key = match_key(first) if first else None
    picked, errors = [], []
    for pk in dict.fromkeys(ids):
        n = have.get(pk) or free.get(pk)
        if n is None:
            errors.append("Pick delivery notes of this customer that are not billed yet.")
        elif key is not None and pk not in have and match_key(n) != key:
            errors.append(
                f"{n.number} goes from another place, to another address or on another "
                "credit term, so it needs an invoice of its own."
            )
        else:
            picked.append(n)
    if errors:
        raise ValidationError({"delivery_notes": list(dict.fromkeys(errors))})
    return picked


def _save(inv: SalesInvoice, data: dict) -> None:
    if "delivery_notes" in data:
        notes = _pick_notes(inv, data["delivery_notes"])
        if {n.pk for n in notes} != set(inv.delivery_notes.values_list("pk", flat=True)):
            _fill(inv, notes)
    latest = max(n.note_date for n in inv.delivery_notes.all())
    if data["invoice_date"] < latest:
        raise ValidationError(
            {
                "invoice_date": [
                    f"The delivery note is dated {latest:%d-%m-%Y}; "
                    "date the invoice on or after it."
                ]
            }
        )
    _set_transport(inv, data)
    inv.invoice_date = data["invoice_date"]
    inv.notes = data.get("notes", "").strip()
    inv.save()


# Posting -------------------------------------------------------------------------


def _side(ledger: Ledger, value: Decimal, remarks: str = "") -> GLLine:
    if value >= 0:
        return GLLine(ledger, debit=value, remarks=remarks)
    return GLLine(ledger, credit=-value, remarks=remarks)


def _needs(inv: SalesInvoice) -> list[tuple[str, object, tuple]]:
    """Each line and charge with the item group ledgers it posts to."""
    both, sales = (accounts.SALES, accounts.COGS), (accounts.SALES,)
    out = [
        (f"Line {ln.position}", ln.item, both if ln.cost else sales)
        for ln in inv.lines.select_related("item__item_group")
    ]
    out += [
        (f"Charge {c.item.name}", c.item, (accounts.SALES,))
        for c in inv.charges.select_related("item__item_group")
    ]
    return out


def ledgers_refusal(inv: SalesInvoice, user) -> dict | None:
    """Every main item group whose Sales (or COGS) ledger is not set, at once,
    for the screen's popup."""
    rows: dict[int, dict] = {}
    for label, item, needs in _needs(inv):
        for r in accounts.missing_accounts(inv.company, [(0, item)], needs):
            row = rows.setdefault(r["group"], {**r, "missing": [], "lines": []})
            row["missing"] += [m for m in r["missing"] if m not in row["missing"]]
            text = f"{label} {item.name}" if label.startswith("Line") else label
            if text not in row["lines"]:
                row["lines"].append(text)
    if not rows:
        return None
    names = ", ".join(r["group_name"] for r in rows.values())
    return {
        "detail": f"Set the ledgers of item group {names} for {inv.company} "
        "(Masters > Item groups) before Submit.",
        "missing_accounts": list(rows.values()),
        "may_set": user.can("masters.edit"),
        "company": inv.company.pk,
    }


def _gl(inv: SalesInvoice) -> list[GLLine]:
    company = inv.company
    sales: dict[int, list] = {}
    cogs: dict[int, list] = {}
    for ln in inv.lines.select_related("item__item_group"):
        led = accounts.sales_ledger(company, ln.item)
        sales.setdefault(led.pk, [led, ZERO])[1] += ln.taxable
        if ln.cost:
            led = accounts.cogs_ledger(company, ln.item)
            cogs.setdefault(led.pk, [led, ZERO])[1] += ln.cost
    for c in inv.charges.select_related("item__item_group"):
        led = accounts.sales_ledger(company, c.item)
        sales.setdefault(led.pk, [led, ZERO])[1] += c.amount
    gl = [GLLine(inv.customer, debit=inv.total, remarks=f"Invoice {inv.number}".strip())]
    gl += [GLLine(led, credit=v) for led, v in sales.values() if v]
    for code, value in (
        (accounts.OUTPUT_CGST, inv.cgst_total),
        (accounts.OUTPUT_SGST, inv.sgst_total),
        (accounts.OUTPUT_IGST, inv.igst_total),
    ):
        if value:
            gl.append(GLLine(accounts.system_ledger(company, code), credit=value))
    if inv.round_off:
        gl.append(_side(accounts.system_ledger(company, accounts.ROUND_OFF), -inv.round_off))
    cost = sum((v for _led, v in cogs.values()), ZERO)
    if cost:
        gl += [GLLine(led, debit=v, remarks="Cost of goods billed") for led, v in cogs.values()]
        gdnb = accounts.system_ledger(company, accounts.GOODS_DELIVERED_NOT_BILLED)
        note = ", ".join(n.number for n in notes_of(inv))
        gl.append(GLLine(gdnb, credit=cost, remarks=f"Goods of {note} billed"[:200]))
    return gl


def refused(inv: SalesInvoice, user) -> Response | None:
    """Why Submit cannot go ahead, answered without raising so a draft just
    saved is kept ("id")."""
    if not may(user, "submit"):
        return None
    if found := attachments.refuse_submit(inv, KIND):
        return found
    if refusal := ledgers_refusal(inv, user):
        return Response({**refusal, "id": inv.pk}, status=400)
    return None


def _submit(inv: SalesInvoice, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    ids = list(inv.delivery_notes.values_list("pk", flat=True))
    for n in DeliveryNote.objects.select_for_update().filter(pk__in=ids).order_by("pk"):
        if n.status != DeliveryNote.SUBMITTED:
            raise ValidationError(
                {"detail": f"Delivery note {n.number or 'draft'} is not submitted."}
            )
        billed = n.invoices.filter(status=SalesInvoice.SUBMITTED).exclude(pk=inv.pk)
        if billed.exists():
            raise ValidationError({"detail": f"Delivery note {n.number} is billed already."})
    attachments.require_file(inv, KIND)
    if not inv.lines.exists():
        raise ValidationError({"detail": "There is nothing to bill."})
    if refusal := ledgers_refusal(inv, user):
        raise accounts.AccountsMissing(refusal)
    inv.number = numbering.next_document_number(
        inv.company, KIND, inv.invoice_date, inv.bill_from or inv.branch
    )
    voucher = Voucher(inv.company, inv.branch, inv.invoice_date, KIND, inv.pk, inv.number, user)
    service.post(voucher, gl=_gl(inv))
    inv.dues.all().delete()
    SalesInvoiceDue.objects.bulk_create(
        [
            SalesInvoiceDue(invoice=inv, position=k, due_date=d["due_date"], amount=d["amount"])
            for k, d in enumerate(_due_rows(inv), start=1)
        ]
    )
    inv.status = SalesInvoice.SUBMITTED
    inv.submitted_at = timezone.now()
    inv.submitted_by = user
    inv.save()


def _cancel(inv: SalesInvoice, user, reason: str) -> None:
    if inv.status == SalesInvoice.SUBMITTED:
        service.cancel(KIND, inv.pk, user)
    inv.status = SalesInvoice.CANCELLED
    inv.cancel_reason = reason[:200]
    inv.save()


def _posting_preview(inv: SalesInvoice) -> dict:
    """What Submit will post; a ledger not yet set shows as missing."""
    company = inv.company
    rows: list[dict] = [posting_api.ledger_row(inv.customer, debit=inv.total)]
    sales: dict[object, Decimal] = defaultdict(lambda: ZERO)
    cogs: dict[object, Decimal] = defaultdict(lambda: ZERO)
    ledgers: dict[object, Ledger | None] = {}

    def find(fn, item, label):
        try:
            led = fn(company, item)
        except ValidationError:
            key = f"{label} of item group {accounts.main_group(item)} not set"
            ledgers[key] = None
            return key
        ledgers[led.pk] = led
        return led.pk

    for ln in inv.lines.select_related("item__item_group"):
        sales[find(accounts.sales_ledger, ln.item, "Sales Ledger")] += ln.taxable
        if ln.cost:
            cogs[find(accounts.cogs_ledger, ln.item, "COGS/Expense Ledger")] += ln.cost
    for c in inv.charges.select_related("item__item_group"):
        sales[find(accounts.sales_ledger, c.item, "Sales Ledger")] += c.amount

    def row(key, debit=ZERO, credit=ZERO):
        led = ledgers[key]
        return posting_api.ledger_row(led, debit, credit, "" if led else str(key))

    rows += [row(k, credit=v) for k, v in sales.items() if v]
    for code, value in (
        (accounts.OUTPUT_CGST, inv.cgst_total),
        (accounts.OUTPUT_SGST, inv.sgst_total),
        (accounts.OUTPUT_IGST, inv.igst_total),
    ):
        if value:
            rows.append(posting_api.ledger_row(accounts.system_ledger(company, code), credit=value))
    if inv.round_off:
        led = accounts.system_ledger(company, accounts.ROUND_OFF)
        rows.append(
            posting_api.ledger_row(led, credit=inv.round_off)
            if inv.round_off > 0
            else posting_api.ledger_row(led, debit=-inv.round_off)
        )
    cost = sum(cogs.values(), ZERO)
    if cost:
        rows += [row(k, debit=v) for k, v in cogs.items()]
        gdnb = accounts.system_ledger(company, accounts.GOODS_DELIVERED_NOT_BILLED)
        rows.append(posting_api.ledger_row(gdnb, credit=cost))
    note = (
        f"The cost (₹{_money(cost)}, FIFO) was set aside by the delivery note; the invoice "
        "moves it to Cost of Goods Sold. "
        if cost
        else ""
    )
    return posting_api.preview(rows, note)


# The e-invoice JSON (NIC schema 1.1) -----------------------------------------------


MODE_CODES = {"road": "1", "rail": "2", "air": "3", "ship": "4"}


def _address_lines(text: str) -> tuple[str, str]:
    parts = [x.strip().rstrip(",") for x in (text or "").split("\n") if x.strip()]
    first = parts[0] if parts else ""
    rest = ", ".join(parts[1:])
    return first[:100] or "-", rest[:100]


def _pin(value) -> int | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if len(digits) == 6 else None


def _place(name: str, a: dict, gstin: str | None = None) -> dict:
    one, two = _address_lines(a.get("address", ""))
    out = {"LglNm": name[:100], "Addr1": one}
    if gstin is not None:
        out = {"Gstin": gstin, **out}
    if two:
        out["Addr2"] = two
    out["Loc"] = (a.get("city") or "-")[:50]
    out["Pin"] = _pin(a.get("pincode"))
    out["Stcd"] = a.get("state_code") or "96"
    return out


def _num(value) -> float:
    return float(Decimal(str(value)))


def einvoice_json(inv: SalesInvoice) -> list[dict]:
    """The invoice as the e-invoice portal's bulk upload takes it (a list of one).
    The e-way bill details go in with it, so the portal makes both."""
    party = inv.customer.party
    seller_place = _branch_address(inv.bill_from or inv.branch)
    bill = inv.bill_address or {}
    overseas = party.gst_type == Party.OVERSEAS
    if overseas:
        kind = "EXPWP" if inv.igst_total else "EXPWOP"
    elif party.gst_type == Party.SEZ:
        kind = "SEZWP" if inv.igst_total else "SEZWOP"
    else:
        kind = "B2B"
    seller = _place(inv.company.name, seller_place, seller_place["gstin"])
    gstin = "URP" if overseas else (bill.get("gstin") or party.gstin)
    buyer = _place(inv.customer.name, bill, gstin)
    buyer["Pos"] = "96" if overseas else inv.place_of_supply
    if overseas:
        buyer["Stcd"], buyer["Pin"] = "96", 999999
    doc = {
        "Version": "1.1",
        "TranDtls": {"TaxSch": "GST", "SupTyp": kind, "RegRev": "N", "IgstOnIntra": "N"},
        "DocDtls": {"Typ": "INV", "No": inv.number, "Dt": inv.invoice_date.strftime("%d/%m/%Y")},
        "SellerDtls": seller,
        "BuyerDtls": buyer,
    }
    if inv.branch_id != (inv.bill_from_id or inv.branch_id):
        despatch = _place(inv.company.name, _branch_address(inv.branch))
        doc["DispDtls"] = {"Nm": despatch.pop("LglNm"), **despatch}
    ship = inv.ship_address or {}
    if ship and ship.get("label") != bill.get("label"):
        doc["ShipDtls"] = _place(inv.customer.name, ship, ship.get("gstin") or None)
        if doc["ShipDtls"].get("Gstin") is None:
            doc["ShipDtls"].pop("Gstin", None)
    items = []
    k = 0
    for ln in inv.lines.select_related("item", "unit"):
        k += 1
        service_item = ln.item.item_type == Item.SERVICE
        row = {
            "SlNo": str(k),
            "PrdDesc": ln.item.name[:300],
            "IsServc": "Y" if service_item else "N",
            "HsnCd": ln.item.hsn,
            "Qty": _num(round(ln.qty, 3)),
            "Unit": ln.unit.gst_code or "OTH",
            "UnitPrice": _num(round(ln.rate, 3)),
            "TotAmt": _num(ln.taxable),
            "Discount": 0,
            "AssAmt": _num(ln.taxable),
            "GstRt": _num(ln.gst_rate),
            "IgstAmt": _num(ln.igst),
            "CgstAmt": _num(ln.cgst),
            "SgstAmt": _num(ln.sgst),
            "TotItemVal": _num(ln.amount),
        }
        items.append(row)
    for c in inv.charges.select_related("item"):
        k += 1
        value = c.amount + c.cgst + c.sgst + c.igst
        items.append(
            {
                "SlNo": str(k),
                "PrdDesc": c.item.name[:300],
                "IsServc": "Y",
                "HsnCd": c.item.hsn,
                "UnitPrice": _num(c.amount),
                "TotAmt": _num(c.amount),
                "Discount": 0,
                "AssAmt": _num(c.amount),
                "GstRt": _num(c.gst_rate),
                "IgstAmt": _num(c.igst),
                "CgstAmt": _num(c.cgst),
                "SgstAmt": _num(c.sgst),
                "TotItemVal": _num(value),
            }
        )
    doc["ItemList"] = items
    doc["ValDtls"] = {
        "AssVal": _num(inv.taxable_total),
        "CgstVal": _num(inv.cgst_total),
        "SgstVal": _num(inv.sgst_total),
        "IgstVal": _num(inv.igst_total),
        "RndOffAmt": _num(inv.round_off),
        "TotInvVal": _num(inv.total),
    }
    if (inv.vehicle_no or inv.transporter_id) and eway_with_einvoice(inv):
        ewb = {"Distance": inv.distance_km or 0}
        if inv.transporter and inv.transporter.gstin:
            ewb["TransId"] = inv.transporter.gstin
        if inv.transporter:
            ewb["TransName"] = inv.transporter.name[:100]
        if inv.lr_no:
            ewb["TransDocNo"] = inv.lr_no[:15]
        if inv.lr_date:
            ewb["TransDocDt"] = inv.lr_date.strftime("%d/%m/%Y")
        if inv.vehicle_no:
            ewb["TransMode"] = MODE_CODES.get(inv.mode, "1")
            ewb["VehNo"] = inv.vehicle_no
            ewb["VehType"] = "R"
        doc["EwbDtls"] = ewb
    return [doc]


# Views -----------------------------------------------------------------------


def _invoice(request, pk: int, lock: bool = False) -> SalesInvoice:
    rows = SalesInvoice.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    inv = rows.select_related("company", "customer__party").first()
    if inv is None or "sales" not in inv.company.modules:
        raise NotFound("No such sales invoice.")
    return inv


VIEWS = (SalesInvoice.DRAFT, SalesInvoice.SUBMITTED, SalesInvoice.CANCELLED)


class InvoiceListView(APIView):
    """GET ?view=draft|submitted|cancelled|all&q=text: the company's invoices."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        rows = _invoices(company).prefetch_related("dues", "delivery_notes__order__salesman")
        view = request.query_params.get("view", "all")
        if view in VIEWS:
            rows = rows.filter(status=view)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(customer__name__icontains=word)
                | Q(delivery_notes__number__icontains=word)
                | Q(delivery_notes__order__number__icontains=word)
            ).distinct()
        return Response([invoice_out(i, lines=False) for i in rows[:1000]])


class InvoiceFromNoteView(APIView):
    """POST: a draft invoice for a submitted delivery note ("Create ▾ › Sales
    Invoice"); the note's draft if it has one already."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        from selling.delivery import _note

        _check(request, "create")
        n = _note(request, pk, lock=True)
        if (inv := live_invoice(n)) is not None:
            if inv.status == SalesInvoice.SUBMITTED:
                raise ValidationError(
                    {"detail": f"Delivery note {n.number} is billed on {inv.number} already."}
                )
            return Response(_fresh(inv))
        if n.status != DeliveryNote.SUBMITTED:
            raise ValidationError(
                {"detail": "Submit the delivery note first: an invoice is made from a sent note."}
            )
        return Response(_fresh(make(n, request.user)), status=status.HTTP_201_CREATED)


class InvoiceMoreNotesView(APIView):
    """GET: the customer's other unbilled delivery notes that can go on this
    draft ("Add Delivery Notes")."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        inv = _invoice(request, pk)
        have = notes_of(inv)
        if inv.status != SalesInvoice.DRAFT or not have:
            return Response([])
        key = match_key(have[0])
        return Response(
            [
                {
                    "id": n.pk,
                    "number": n.number,
                    "note_date": n.note_date,
                    "order_number": n.order.number,
                    "customer_po_no": n.order.customer_po_no,
                }
                for n in unbilled(inv.company, inv.customer_id)
                if match_key(n) == key
            ]
        )


class InvoiceDetailView(APIView):
    """GET one invoice; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(_fresh(_invoice(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        inv = _invoice(request, pk, lock=True)
        if inv.status != SalesInvoice.DRAFT:
            raise ValidationError(
                {"detail": "A submitted invoice cannot be changed. Cancel it and make a new one."}
            )
        serializer = InvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(inv, data)
        if data.get("submit"):
            if answer := refused(inv, request.user):
                return answer
            _submit(inv, request.user)
        return Response(_fresh(inv))


class InvoiceSubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        inv = _invoice(request, pk, lock=True)
        if inv.status != SalesInvoice.DRAFT:
            raise ValidationError({"detail": "This invoice is not a draft."})
        if answer := refused(inv, request.user):
            return answer
        _submit(inv, request.user)
        return Response(_fresh(inv))


class InvoiceCancelView(APIView):
    """POST {reason}: the entries are reversed and the delivery note can be
    billed again."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        inv = _invoice(request, pk, lock=True)
        if inv.status == SalesInvoice.CANCELLED:
            raise ValidationError({"detail": "This invoice is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(inv, request.user, reason)
        return Response(_fresh(inv))


class InvoiceTransportView(APIView):
    """POST: "Update Transport": transporter, mode, vehicle, distance and LR, on
    a draft or a submitted invoice (they post nothing)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        inv = _invoice(request, pk, lock=True)
        if inv.status == SalesInvoice.CANCELLED:
            raise ValidationError({"detail": "This invoice is cancelled."})
        serializer = TransportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _set_transport(inv, dict(serializer.validated_data))
        inv.save()
        return Response(_fresh(inv))


class EInvoiceSerializer(serializers.Serializer):
    irn = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    ack_no = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    ack_date = serializers.DateTimeField(required=False, allow_null=True)
    signed_qr = serializers.CharField(required=False, allow_blank=True, default="")
    eway_bill_no = serializers.CharField(
        max_length=14, required=False, allow_blank=True, default=""
    )
    eway_bill_date = serializers.DateTimeField(required=False, allow_null=True)
    eway_valid_until = serializers.DateTimeField(required=False, allow_null=True)


class InvoiceEInvoiceView(APIView):
    """POST: the IRN, acknowledgement and e-way bill numbers as the portal gave
    them, typed in after Submit (until a provider's API does it)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        inv = _invoice(request, pk, lock=True)
        if inv.status != SalesInvoice.SUBMITTED:
            raise ValidationError({"detail": "Submit the invoice first."})
        serializer = EInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        errors = {}
        irn = data["irn"].strip().lower()
        if irn and not re.fullmatch(r"[0-9a-f]{64}", irn):
            errors["irn"] = ["An IRN is 64 letters and digits (0-9, a-f), as on the portal."]
        ewb = re.sub(r"\s", "", data["eway_bill_no"])
        if ewb and not re.fullmatch(r"\d{12}", ewb):
            errors["eway_bill_no"] = ["An e-way bill number is 12 digits."]
        ack = data["ack_no"].strip()
        if ack and not ack.isdigit():
            errors["ack_no"] = ["The acknowledgement number is digits only."]
        if errors:
            raise ValidationError(errors)
        inv.irn, inv.ack_no, inv.ack_date = irn, ack, data.get("ack_date")
        if data["signed_qr"].strip():  # left blank, a QR given earlier stays
            inv.signed_qr = data["signed_qr"].strip()
        inv.eway_bill_no = ewb
        inv.eway_bill_date = data.get("eway_bill_date")
        inv.eway_valid_until = data.get("eway_valid_until")
        inv.save()
        return Response(_fresh(inv))


class InvoiceLedgerPostingView(APIView):
    """GET: the "Ledger Posting" section. A draft shows what Submit will post."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        inv = _invoice(request, pk)
        if inv.status == SalesInvoice.DRAFT:
            return Response(_posting_preview(inv))
        return Response(posting_api.posted(KIND, inv.pk))


class InvoiceJsonView(APIView):
    """GET: the e-invoice JSON to upload on the portal (with the e-way bill)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        inv = _invoice(request, pk)
        if inv.status != SalesInvoice.SUBMITTED:
            raise ValidationError(
                {"detail": "Submit the invoice first: the JSON needs its number."}
            )
        if not einvoice_party(inv.customer.party):
            raise ValidationError(
                {
                    "detail": f"{inv.customer.name} is not a registered business, so this "
                    "invoice needs no e-invoice."
                }
            )
        body = json.dumps(einvoice_json(inv), indent=2, ensure_ascii=False)
        response = HttpResponse(body, content_type="application/json")
        name = f"e-invoice-{inv.number.replace('/', '-')}.json"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


COPIES = [
    "Original for Recipient",
    "Duplicate for Transporter",
    "Triplicate for Supplier",
]


def print_data(inv: SalesInvoice) -> dict:
    """The invoice in the shape of the sales order print (buying.po_pdf)."""
    from core.models import TermsSet
    from core.terms import terms_for
    from selling.api import _addresses_out

    data = _fresh(inv)
    party = inv.customer.party
    notes = notes_of(inv)
    orders = orders_of(notes)
    ship = inv.ship_address or {}
    data["order_date"] = inv.invoice_date
    data["doc_title"] = "TAX INVOICE"
    data["currency"], data["currency_symbol"] = "INR", "₹"
    data["letterhead"] = _letterhead(inv.company)
    # The order's print gives the customer's address with its GSTIN, FSSAI and
    # the people the order went to; the bill and ship addresses are the invoice's.
    data["addresses"] = _addresses_out(orders[0])
    data["addresses"]["bill_from"] = _branch_address(inv.bill_from or inv.branch)
    data["addresses"]["customer"].update(inv.bill_address or {})
    # Shipped to the billing address when the note names no other.
    data["addresses"]["ship_to"] = {
        "name": inv.customer.name,
        **(ship or data["addresses"]["customer"]),
    }
    po = _joined(
        o.customer_po_no + (f" of {o.customer_po_date:%d-%m-%Y}" if o.customer_po_date else "")
        for o in orders
        if o.customer_po_no
    )
    due = data["first_due"]
    lr = data["lr_no"] and f"LR {data['lr_no']}"
    transport = " · ".join(x for x in [data["transporter_name"], data["vehicle_no"], lr] if x)
    data["print_meta"] = [
        ("Place of Supply", data["place_of_supply_name"]),
        ("Due Date", due.strftime("%d-%m-%Y") if due else ""),
        ("Credit Term", data["credit_term_name"]),
        ("Your PO", po),
        ("Delivery Note" + ("s" if len(notes) > 1 else ""), data["delivery_note_number"]),
        ("Sales Order" + ("s" if len(orders) > 1 else ""), data["order_number"]),
        ("Transport", transport),
        ("Salesman", data["salesman_name"]),
        ("IRN", inv.irn),
        ("Ack No / Date", " · ".join(x for x in [inv.ack_no, _dt(inv.ack_date)] if x)),
        ("e-Way Bill", " · ".join(x for x in [inv.eway_bill_no, _dt(inv.eway_bill_date)] if x)),
    ]
    data["signed_qr"] = inv.signed_qr
    # Until the IRN is in, the QR's place says so (an e-invoice must carry it).
    data["qr_pending"] = (
        not inv.signed_qr and inv.status != SalesInvoice.CANCELLED and einvoice_party(party)
    )
    data["amount_words"] = words.amount(inv.total, "INR", "Indian Rupee")
    data["submitted_by_signature"] = (
        inv.submitted_by.signature_url() if inv.submitted_by and inv.status != "draft" else ""
    )
    default = terms_for(inv.company, party, TermsSet.SALES)
    data["terms"] = next((o.terms for o in orders if o.terms.strip()), "") or (
        default.text if default else ""
    )
    return data


def invoice_pdf(inv: SalesInvoice, copies: list[str]) -> bytes:
    from reportlab.platypus import NextPageTemplate, PageBreak

    from buying.po_pdf import order_pdf

    data = print_data(inv)
    prefix: list = []
    for label in copies[:-1]:
        prefix += order_pdf(data, label, story_only=True)
        prefix += [NextPageTemplate("first"), PageBreak()]
    return order_pdf(data, copies[-1], prefix=prefix)


def _eway_pdf(inv: SalesInvoice):
    from core import printout

    data = _fresh(inv)
    rows = [
        [
            str(ln["position"]),
            ln["item_name"],
            ln["goods_hsn"],
            f"{ln['qty']} {ln['unit_name']}",
            ln["taxable"],
            f"{ln['gst_rate']}%",
            ln["amount"],
        ]
        for ln in data["lines"]
    ]
    total = ["", "Total (with charges and tax)", "", "", data["taxable_total"], "", data["total"]]
    rows.append(total)
    scope = " · ".join(
        x
        for x in [
            f"e-Way Bill {inv.eway_bill_no}" if inv.eway_bill_no else "e-Way Bill not yet made",
            inv.eway_bill_date and f"Made {_dt(inv.eway_bill_date)}",
            inv.eway_valid_until and f"Valid until {_dt(inv.eway_valid_until)}",
            f"From GSTIN {data['bill_from_gstin']}",
            f"To {data['customer_name']}"
            + (f" GSTIN {data['customer_gstin']}" if data["customer_gstin"] else ""),
            f"Invoice {inv.number} of {inv.invoice_date:%d-%m-%Y}",
            f"Transport: {data['transporter_name']}, {data['mode_label']}"
            + (f", vehicle {inv.vehicle_no}" if inv.vehicle_no else "")
            + (f", LR {inv.lr_no}" if inv.lr_no else "")
            + (f", {inv.distance_km} km" if inv.distance_km else ""),
        ]
        if x
    )
    sheet = {
        "title": "",
        "columns": ["#", "Item", "HSN", "Qty", "Taxable ₹", "GST", "Value ₹"],
        "rows": rows,
    }
    return printout.pdf_response("e-Way Bill", scope, [sheet], f"eway-{inv.number or 'draft'}")


class InvoicePdfView(APIView):
    """GET ?layout=invoice|copies|eway (&download=1): the Tax Invoice (Original
    for Recipient), the three copies, or the e-way bill details."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        inv = _invoice(request, pk)
        layout = request.query_params.get("layout", "invoice")
        if layout == "eway":
            response = _eway_pdf(inv)
        else:
            copies = COPIES if layout == "copies" else COPIES[:1]
            response = HttpResponse(invoice_pdf(inv, copies), content_type="application/pdf")
            name = (inv.number or "draft-invoice").replace("/", "-")
            response["Content-Disposition"] = f'attachment; filename="{name}.pdf"'
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
