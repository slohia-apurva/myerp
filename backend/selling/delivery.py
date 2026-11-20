"""Delivery notes (Entry > Sales > Delivery Note): the goods going out to the
customer (Sidharth, 2026-11-20, previews 7-9 in mockups/sales).

A note is made from a picked pick list ("Create ▾ › Delivery Note" on the
order or the list) and starts with every bin, batch and quantity picked. While
a draft, a bin can send less, or the goods can come from another bin or batch
that has them free; what is not sent stays pending on the order.

Submit (posting.service):
* the goods leave their bins at FIFO cost: Cr each item group's Stock Ledger;
* Dr "Goods Delivered but Bills not Made" for that cost (decided 2026-11-19):
  the sales invoice later moves it to Cost of Goods Sold and books the sale and
  GST, so cost and sale fall in the same month;
* the order's lines count the goods as delivered and the pick list is
  "Delivered".
Problems found on Submit (a bin no longer has the stock, a batch held back, a
line sending more than is pending) come back together as "problems", each with
its line, for the screen's popup; missing item group ledgers come back as for
the goods receipt (posting.accounts). Cancel puts the goods back and reverses
the entries.

Who may do what: as for pick lists, sales or stock rights.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import _branch_address, _letterhead, _money, _plain
from core import attachments, numbering
from core.api import Signed
from core.companies import visible_companies
from core.models import Batch, Ledger, Package
from posting import accounts, service
from posting import api as posting_api
from posting.models import StockLot
from posting.service import GLLine, StockLine, Voucher
from selling import picking, stock
from selling.api import _company, _split, order_status
from selling.models import (
    DeliveryNote,
    DeliveryNoteBin,
    DeliveryNoteLine,
    PickList,
    SalesOrder,
    SalesOrderLine,
)
from selling.pick_lists import _pick, may, package_out, place_label
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic

KIND = "delivery_note"
NUMBERS = "delivery_challan"  # the series on Settings › Numbering
ZERO = Decimal("0")


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with delivery notes.")


def _unit_name(unit) -> str:
    return unit.short_name or unit.name


# Reading ---------------------------------------------------------------------


def _notes(company):
    return (
        DeliveryNote.objects.filter(company=company)
        .select_related(
            "company",
            "customer__party",
            "order",
            "pick_list",
            "branch",
            "area",
            "bill_from",
            "transporter",
            "created_by",
            "submitted_by",
        )
        .prefetch_related("invoices")
    )


def _bin_out(b: DeliveryNoteBin, factor: Decimal) -> dict:
    return {
        "id": b.pk,
        "location": b.location_id,
        "location_name": b.location.name,
        "batch": b.batch_id,
        "batch_number": b.batch.number if b.batch else "",
        "expiry": b.batch.expiry_date if b.batch else None,
        **package_out(b.package),
        "picked": _plain(b.picked),
        "qty": _plain(b.qty),
        "qty_unit": picking.plain(b.qty / factor),
        "cost": str(b.cost),
    }


def _line_out(ln: DeliveryNoteLine, note: DeliveryNote) -> dict:
    ol = ln.order_line
    factor = picking.factor(ol)
    bins = list(ln.bins.all())
    mine = ln.qty if note.status == DeliveryNote.SUBMITTED else ZERO
    return {
        "id": ln.pk,
        "position": ln.position,
        "order_line": ol.pk,
        "item": ln.item_id,
        "item_name": ln.item.name,
        # The goods code goes on the challan and the e-way bill (a job-work
        # service keeps its goods code apart).
        "hsn": ln.item.delivery_hsn or ln.item.hsn,
        "unit_name": _unit_name(ln.unit),
        "stock_unit_name": _unit_name(ln.item.stock_unit),
        "factor": picking.plain(factor),
        "ordered": _plain(ol.qty),
        "sent_earlier": _plain(ol.delivered_qty - mine),
        "pending": _plain(picking.pending(ol) + mine),
        "picked": picking.plain(sum((b.picked for b in bins), ZERO) / factor),
        "qty": _plain(ln.qty),
        "rate": _plain(ln.rate),
        "taxable": str(ln.taxable),
        "gst_rate": _plain(ln.gst_rate),
        "cgst": str(ln.cgst),
        "sgst": str(ln.sgst),
        "igst": str(ln.igst),
        "amount": str(ln.amount),
        "cost": str(ln.cost),
        "bins": [_bin_out(b, factor) for b in bins],
    }


def note_out(n: DeliveryNote, lines: bool = True) -> dict:
    from selling.invoices import brief as invoice_brief
    from selling.invoices import live_invoice

    billed = invoice_brief(live_invoice(n))
    data = {
        "id": n.pk,
        "company": n.company_id,
        "number": n.number,
        "status": n.status,
        "status_label": n.get_status_display(),
        "customer": n.customer_id,
        "customer_name": n.customer.name,
        "customer_gstin": n.customer.party.gstin if n.customer.party_id else "",
        "order": n.order_id,
        "order_number": n.order.number,
        "customer_po_no": n.order.customer_po_no,
        "customer_po_date": n.order.customer_po_date,
        "pick_list": n.pick_list_id,
        "pick_list_number": n.pick_list.number,
        "pick_list_status": n.pick_list.get_status_display(),
        "branch": n.branch_id,
        "despatch_from": f"{n.branch.name} › {n.area.name}" if n.area_id else n.branch.name,
        "note_date": n.note_date,
        "bill_from": n.bill_from_id,
        "bill_from_name": n.bill_from.name if n.bill_from else "",
        "bill_from_gstin": (n.bill_from.gstin if n.bill_from else "") or n.company.gstin,
        "ship_address": n.ship_address,
        "transporter": n.transporter_id,
        "transporter_name": n.transporter.name if n.transporter else "By Customer",
        "mode": n.mode,
        "mode_label": n.get_mode_display(),
        "vehicle_no": n.vehicle_no,
        "distance_km": n.distance_km,
        "lr_no": n.lr_no,
        "lr_date": n.lr_date,
        "packages": n.packages,
        "gross_weight": _plain(n.gross_weight),
        "notes": n.notes,
        "interstate": n.interstate,
        "taxable_total": str(n.taxable_total),
        "cgst_total": str(n.cgst_total),
        "sgst_total": str(n.sgst_total),
        "igst_total": str(n.igst_total),
        "total": str(n.total),
        "cost_total": str(n.cost_total),
        "billed": billed is not None and billed["status"] == "submitted",
        "invoice": billed,
        "cancel_reason": n.cancel_reason,
        "created_by_name": n.created_by.display_name if n.created_by else "",
        "created_at": n.created_at,
        "submitted_at": n.submitted_at,
        "submitted_by_name": n.submitted_by.display_name if n.submitted_by else "",
    }
    if lines:
        rows = n.lines.select_related("item__stock_unit", "unit", "order_line").prefetch_related(
            "bins__location", "bins__batch", "bins__package"
        )
        data["lines"] = [_line_out(ln, n) for ln in rows]
        data["salesman_name"] = n.order.salesman.name if n.order.salesman_id else ""
    return data


def _fresh(n: DeliveryNote) -> dict:
    return note_out(_notes(n.company).get(pk=n.pk))


def brief(n: DeliveryNote) -> dict:
    """What the sales order shows of its delivery notes."""
    return {
        "id": n.pk,
        "number": n.number,
        "status": n.status,
        "status_label": n.get_status_display(),
    }


# Making one from a pick list -------------------------------------------------


def _totals(n: DeliveryNote, lines: list[DeliveryNoteLine]) -> None:
    n.taxable_total = sum((ln.taxable for ln in lines), ZERO)
    n.cgst_total = sum((ln.cgst for ln in lines), ZERO)
    n.sgst_total = sum((ln.sgst for ln in lines), ZERO)
    n.igst_total = sum((ln.igst for ln in lines), ZERO)
    n.total = sum((ln.amount for ln in lines), ZERO)


def _price(ln: DeliveryNoteLine, interstate: bool) -> None:
    """The line's value at the order's rate and GST, for the challan."""
    ln.taxable = _money(ln.qty * ln.rate)
    ln.cgst, ln.sgst, ln.igst = _split(_money(ln.taxable * ln.gst_rate / 100), interstate)
    ln.amount = ln.taxable + ln.cgst + ln.sgst + ln.igst


def make(p: PickList, user) -> DeliveryNote:
    """A draft note for everything on a picked list."""
    o = p.order
    n = DeliveryNote.objects.create(
        company=p.company,
        customer=o.customer,
        order=o,
        pick_list=p,
        branch=p.branch,
        area=p.area,
        note_date=max(timezone.localdate(), o.order_date),
        bill_from=o.bill_from,
        ship_address=o.ship_address,
        transporter=o.transporter,
        interstate=o.interstate,
        created_by=user,
    )
    rows = list(p.lines.select_related("order_line__unit", "item", "location", "batch", "package"))
    by_line: dict[int, list] = defaultdict(list)
    for r in rows:
        by_line[r.order_line_id].append(r)
    lines = []
    for ol in o.lines.select_related("item", "unit").filter(pk__in=by_line):
        factor = picking.factor(ol)
        picked = by_line[ol.pk]
        ln = DeliveryNoteLine.objects.create(
            note=n,
            position=ol.position,
            order_line=ol,
            item=ol.item,
            unit=ol.unit,
            qty=sum((r.qty for r in picked), ZERO) / factor,
            rate=ol.rate,
            gst_rate=ol.gst_rate,
        )
        _price(ln, n.interstate)
        ln.save()
        lines.append(ln)
        DeliveryNoteBin.objects.bulk_create(
            [
                DeliveryNoteBin(
                    line=ln,
                    location=r.location,
                    batch=r.batch,
                    package=r.package,
                    picked=r.qty,
                    qty=r.qty,
                )
                for r in picked
            ]
        )
    _totals(n, lines)
    n.save()
    return n


def live_note(p: PickList) -> DeliveryNote | None:
    return p.delivery_notes.exclude(status=DeliveryNote.CANCELLED).first()


# Saving a draft ----------------------------------------------------------------


class BinSerializer(serializers.Serializer):
    line = serializers.IntegerField()
    location = serializers.IntegerField()
    batch = serializers.IntegerField(required=False, allow_null=True)
    package = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))


class NoteSerializer(serializers.Serializer):
    note_date = serializers.DateField()
    transporter = serializers.IntegerField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=DeliveryNote.MODES, default=DeliveryNote.ROAD)
    vehicle_no = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    distance_km = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    lr_no = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    lr_date = serializers.DateField(required=False, allow_null=True)
    packages = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    gross_weight = serializers.DecimalField(
        max_digits=18, decimal_places=6, required=False, allow_null=True, min_value=Decimal("0")
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    bins = BinSerializer(many=True, required=False)
    submit = serializers.BooleanField(required=False, default=False)


def _save(n: DeliveryNote, data: dict) -> None:
    if data["note_date"] < n.order.order_date:
        raise ValidationError(
            {
                "note_date": [
                    f"The order is dated {n.order.order_date:%d-%m-%Y}; "
                    "date the note on or after it."
                ]
            }
        )
    transporter = None
    if data.get("transporter"):
        transporter = CourierAccount.objects.filter(
            pk=data["transporter"], company=n.company
        ).first()
        if transporter is None:
            raise ValidationError({"transporter": ["Pick a transporter from the list."]})
    n.note_date = data["note_date"]
    n.transporter = transporter
    n.mode = data.get("mode") or DeliveryNote.ROAD
    n.vehicle_no = data.get("vehicle_no", "").strip().upper().replace(" ", "")
    n.distance_km = data.get("distance_km")
    n.lr_no = data.get("lr_no", "").strip()
    n.lr_date = data.get("lr_date")
    n.packages = data.get("packages")
    n.gross_weight = data.get("gross_weight")
    n.notes = data.get("notes", "").strip()
    lines = {ln.pk: ln for ln in n.lines.select_related("item", "order_line__unit")}
    if "bins" in data:
        places = {x.pk: x for x in stock.places(n.branch, n.area)}
        picked = {
            (b.line_id, b.location_id, b.batch_id, b.package_id): b.picked
            for b in DeliveryNoteBin.objects.filter(line__note=n)
        }
        rows, errors = [], []
        for k, row in enumerate(data["bins"], start=1):
            ln = lines.get(row["line"])
            if ln is None:
                errors.append(f"Row {k}: pick a line of this note.")
                continue
            if not row["qty"]:
                continue  # a bin left at 0 sends nothing
            place = places.get(row["location"])
            if place is None:
                errors.append(f"Line {ln.position}: pick a bin in {place_label(n.pick_list)}.")
                continue
            batch = None
            if row.get("batch"):
                batch = Batch.objects.filter(pk=row["batch"], item=ln.item_id).first()
                if batch is None:
                    errors.append(f"Line {ln.position}: pick a batch of {ln.item.name}.")
                    continue
            package = None
            if row.get("package"):
                package = Package.objects.filter(
                    pk=row["package"], item=ln.item_id, location=place, batch=batch
                ).first()
                if package is None:
                    errors.append(f"Line {ln.position}: pick a package in {place.name}.")
                    continue
            key = (ln.pk, place.pk, batch.pk if batch else None, package.pk if package else None)
            rows.append(
                DeliveryNoteBin(
                    line=ln,
                    location=place,
                    batch=batch,
                    package=package,
                    picked=picked.get(key, ZERO),
                    qty=row["qty"],
                )
            )
        if errors:
            raise ValidationError({"bins": errors})
        sent: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for b in rows:
            sent[b.line_id] += b.qty
        over = []
        for ln in lines.values():
            want = picking.pending(ln.order_line) * picking.factor(ln.order_line)
            if sent[ln.pk] > want:
                over.append(
                    f"Line {ln.position}, {ln.item.name}: sends {picking.plain(sent[ln.pk])}, "
                    f"more than the {picking.plain(want)} still to go."
                )
        if over:
            raise ValidationError({"bins": over})
        # Rows that were picked but are now at 0 stay, to show what was picked.
        kept = {(b.line_id, b.location_id, b.batch_id, b.package_id) for b in rows}
        for (line_id, loc, batch, package), qty in picked.items():
            if qty and (line_id, loc, batch, package) not in kept:
                rows.append(
                    DeliveryNoteBin(
                        line_id=line_id,
                        location_id=loc,
                        batch_id=batch,
                        package_id=package,
                        picked=qty,
                        qty=ZERO,
                    )
                )
        DeliveryNoteBin.objects.filter(line__note=n).delete()
        DeliveryNoteBin.objects.bulk_create(rows)
        for ln in lines.values():
            ln.qty = sent[ln.pk] / picking.factor(ln.order_line)
    for ln in lines.values():
        _price(ln, n.interstate)
        ln.save()
    _totals(n, list(lines.values()))
    n.save()


# Submitting ---------------------------------------------------------------------


def _sending(n: DeliveryNote) -> list[DeliveryNoteLine]:
    return [
        ln
        for ln in n.lines.select_related(
            "item__item_group", "order_line__unit", "unit"
        ).prefetch_related("bins__location", "bins__batch", "bins__package")
        if ln.qty > 0
    ]


def problems(n: DeliveryNote) -> list[dict]:
    """Everything that stops Submit, each with its line: a batch held back, a
    bin that no longer has the stock free, a line sending more than is pending."""
    out = []
    lines = _sending(n)
    free: dict[int, dict] = {}
    asked: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    first: dict[tuple, tuple] = {}
    for ln in lines:
        if ln.item_id not in free:
            # Free per bin and batch; packages only say which bag.
            here: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
            for s in picking.spots(ln.item, n.branch, n.area, n.pick_list):
                here[s.key[:2]] += s.free
            free[ln.item_id] = here
        ol = SalesOrderLine.objects.get(pk=ln.order_line_id)
        if ln.qty > picking.pending(ol):
            out.append(
                {
                    "line": ln.position,
                    "text": f"Line {ln.position}, {ln.item.name}: sends {_plain(ln.qty)} "
                    f"{_unit_name(ln.unit)}, but only {_plain(picking.pending(ol))} is still to go "
                    "on the order.",
                }
            )
        for b in ln.bins.all():
            if not b.qty:
                continue
            if b.batch and b.batch.status in picking.HELD:
                out.append(
                    {
                        "line": ln.position,
                        "text": f"Line {ln.position}, {ln.item.name}: batch {b.batch.number} is "
                        f"held back ({b.batch.get_status_display()}) and cannot be sent.",
                    }
                )
                continue
            if b.package and b.qty > b.package.left_qty:
                out.append(
                    {
                        "line": ln.position,
                        "text": f"Line {ln.position}, {ln.item.name}: package "
                        f"{b.package.number} has {picking.plain(b.package.left_qty)} left; "
                        f"this note sends {picking.plain(b.qty)}.",
                    }
                )
                continue
            key = (ln.item_id, (b.location_id, b.batch_id))
            asked[key] += b.qty
            first.setdefault(key, (ln, b))
    for key, qty in asked.items():
        have = free[key[0]].get(key[1], ZERO)
        if qty > have:
            ln, b = first[key]
            unit = _unit_name(ln.item.stock_unit)
            where = f"bin {b.location.name}" + (f", batch {b.batch.number}" if b.batch else "")
            out.append(
                {
                    "line": ln.position,
                    "text": f"Line {ln.position}, {ln.item.name}: {where} now has "
                    f"{picking.plain(have)} {unit} free; this note sends {picking.plain(qty)} "
                    f"{unit}. Another entry has taken stock from it since it was picked.",
                }
            )
    return out


def _numbered(n: DeliveryNote) -> list[tuple[int, object]]:
    return [(ln.position, ln.item) for ln in _sending(n)]


def refused(n: DeliveryNote, user) -> Response | None:
    """Why Submit cannot go ahead, answered without raising so a draft just
    saved is kept ("id")."""
    if not may(user, "submit"):
        return None
    if found := attachments.refuse_submit(n, KIND):
        return found
    lines = _sending(n)
    if not lines:
        return Response(
            {"detail": "Nothing is being sent: give a quantity on at least one line.", "id": n.pk},
            status=400,
        )
    if found := problems(n):
        return Response(
            {
                "detail": "This note cannot be submitted yet.",
                "problems": found,
                "id": n.pk,
            },
            status=400,
        )
    if refusal := accounts.accounts_refusal(n.company, user, _numbered(n)):
        return Response({**refusal, "id": n.pk}, status=400)
    return None


def _submit(n: DeliveryNote, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    if n.pick_list.status != PickList.PICKED:
        raise ValidationError({"detail": f"Pick list {n.pick_list.number} is not picked."})
    attachments.require_file(n, KIND)
    lines = _sending(n)
    if not lines:
        raise ValidationError(
            {"detail": "Nothing is being sent: give a quantity on at least one line."}
        )
    if found := problems(n):
        raise ValidationError({"detail": "This note cannot be submitted yet.", "problems": found})
    accounts.require_accounts(n.company, user, _numbered(n))

    n.number = numbering.next_document_number(n.company, NUMBERS, n.note_date, n.branch)
    owners: list[tuple[DeliveryNoteLine, DeliveryNoteBin]] = []
    moves: list[StockLine] = []
    for ln in lines:
        for b in ln.bins.all():
            if b.qty:
                moves.append(StockLine(ln.item, b.location, -b.qty, batch=b.batch))
                owners.append((ln, b))
    gdnb = accounts.system_ledger(n.company, accounts.GOODS_DELIVERED_NOT_BILLED)

    def gl(values):
        per_ledger: dict[int, Decimal] = defaultdict(lambda: ZERO)
        ledgers: dict[int, Ledger] = {}
        for (ln, _b), value in zip(owners, values, strict=True):
            led = accounts.stock_ledger(n.company, ln.item)
            ledgers[led.pk] = led
            per_ledger[led.pk] += -value
        total = sum(per_ledger.values(), ZERO)
        return [GLLine(gdnb, debit=total, remarks=f"Goods to {n.customer.name}")] + [
            GLLine(ledgers[k], credit=v, remarks=f"Sent on {n.number}")
            for k, v in per_ledger.items()
        ]

    voucher = Voucher(n.company, n.branch, n.note_date, KIND, n.pk, n.number, user)
    done = service.post(voucher, stock=moves, gl=gl)
    line_cost: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for (ln, b), value in zip(owners, done.stock_values, strict=True):
        b.cost = -value
        b.save(update_fields=["cost"])
        line_cost[ln.pk] += -value
    for _ln, b in owners:
        if b.package_id:
            _use_package(b.package_id, b.qty)
    for ln in lines:
        ln.cost = line_cost[ln.pk]
        ln.save(update_fields=["cost"])
        ol = SalesOrderLine.objects.select_for_update().get(pk=ln.order_line_id)
        ol.delivered_qty += ln.qty
        ol.save(update_fields=["delivered_qty"])
    n.cost_total = sum(line_cost.values(), ZERO)
    n.status = DeliveryNote.SUBMITTED
    n.submitted_at = timezone.now()
    n.submitted_by = user
    n.save()
    n.pick_list.status = PickList.DELIVERED
    n.pick_list.save(update_fields=["status"])
    order_status(n.order)


def _use_package(package_id: int, qty: Decimal) -> None:
    """Take `qty` out of a package (a negative qty puts it back): "Used up" when
    nothing is left, "Part used" while some is, "In stock" when whole again."""
    pk = Package.objects.select_for_update().get(pk=package_id)
    pk.left_qty = max(pk.left_qty - qty, ZERO)
    if pk.left_qty <= 0:
        pk.status = Package.USED_UP
    elif pk.left_qty < pk.qty:
        pk.status = Package.PART_USED
    else:
        pk.left_qty = pk.qty
        pk.status = Package.IN_STOCK
    pk.save(update_fields=["left_qty", "status"])


def _cancel(n: DeliveryNote, user, reason: str) -> None:
    from selling.invoices import live_invoice

    if (inv := live_invoice(n)) is not None:
        raise ValidationError(
            {"detail": f"Cancel sales invoice {inv.number or '(draft)'} of this note first."}
        )
    if n.status == DeliveryNote.SUBMITTED:
        service.cancel(KIND, n.pk, user)
        for ln in n.lines.all():
            if not ln.qty:
                continue
            ol = SalesOrderLine.objects.select_for_update().get(pk=ln.order_line_id)
            ol.delivered_qty -= ln.qty
            ol.save(update_fields=["delivered_qty"])
        for b in DeliveryNoteBin.objects.filter(line__note=n, qty__gt=0).exclude(package=None):
            _use_package(b.package_id, -b.qty)
        # The goods are back in their bins; the pick list keeps them aside again.
        p = n.pick_list
        if p.status == PickList.DELIVERED:
            p.status = PickList.PICKED
            p.save(update_fields=["status"])
        order_status(SalesOrder.objects.get(pk=n.order_id))
    n.status = DeliveryNote.CANCELLED
    n.cancel_reason = reason[:200]
    n.save()


# The "Ledger Posting" section ---------------------------------------------------


def _fifo_cost(n: DeliveryNote, item, qty: Decimal, used: dict) -> Decimal | None:
    """What `qty` of the item would cost now, by FIFO, after what earlier lines
    of the same note use (`used`: lot id -> qty). None if there is not enough."""
    lots = StockLot.objects.filter(
        company=n.company, branch=n.branch, item=item, qty_left__gt=0, date__lte=n.note_date
    ).order_by("date", "id")
    left, value = qty, ZERO
    for lot in lots:
        if left <= 0:
            break
        have = lot.qty_left - used.get(lot.pk, ZERO)
        if have <= 0:
            continue
        take = min(left, have)
        used[lot.pk] = used.get(lot.pk, ZERO) + take
        value += lot.value_left if take == lot.qty_left else take * lot.rate
        left -= take
    return None if left > 0 else _money(value)


def _posting_preview(n: DeliveryNote) -> dict:
    per_ledger: dict[int, Decimal] = defaultdict(lambda: ZERO)
    ledgers: dict[int, Ledger] = {}
    unset: dict[str, Decimal] = defaultdict(lambda: ZERO)
    used: dict[int, Decimal] = {}
    short = []
    for ln in _sending(n):
        qty = sum((b.qty for b in ln.bins.all()), ZERO)
        value = _fifo_cost(n, ln.item, qty, used)
        if value is None:
            short.append(ln.item.name)
            continue
        try:
            led = accounts.stock_ledger(n.company, ln.item)
        except ValidationError:
            unset[f"Stock Ledger of item group {accounts.main_group(ln.item)} not set"] += value
            continue
        ledgers[led.pk] = led
        per_ledger[led.pk] += value
    total = sum(per_ledger.values(), ZERO) + sum(unset.values(), ZERO)
    rows = []
    if total:
        gdnb = accounts.system_ledger(n.company, accounts.GOODS_DELIVERED_NOT_BILLED)
        rows.append(posting_api.ledger_row(gdnb, debit=total))
    rows += [posting_api.ledger_row(ledgers[k], credit=v) for k, v in per_ledger.items()]
    rows += [posting_api.ledger_row(None, credit=v, missing=text) for text, v in unset.items()]
    note = (
        "At cost (FIFO), not at the sale price. The sales invoice moves it to Cost of Goods Sold. "
    )
    if short:
        note = f"Not enough stock to cost {', '.join(short)} now. " + note
    return posting_api.preview(rows, note)


# Views -----------------------------------------------------------------------


def _note(request, pk: int, lock: bool = False) -> DeliveryNote:
    rows = DeliveryNote.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    n = rows.select_related("company", "order", "pick_list", "branch", "area").first()
    if n is None or "sales" not in n.company.modules:
        raise NotFound("No such delivery note.")
    return n


VIEWS = (DeliveryNote.DRAFT, DeliveryNote.SUBMITTED, DeliveryNote.CANCELLED)


class NoteListView(APIView):
    """GET ?view=draft|submitted|cancelled|all&q=text: the company's notes."""

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
                | Q(order__number__icontains=word)
                | Q(lines__item__name__icontains=word)
            ).distinct()
        return Response([note_out(n, lines=False) for n in rows[:1000]])


class NoteFromPickView(APIView):
    """POST: a draft delivery note for a picked list ("Create ▾ › Delivery Note");
    the list's draft if it has one already."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        p = _pick(request, pk, lock=True)
        if (n := live_note(p)) is not None:
            if n.status == DeliveryNote.SUBMITTED:
                raise ValidationError(
                    {"detail": f"Pick list {p.number} has gone out on {n.number} already."}
                )
            return Response(_fresh(n))
        if p.status != PickList.PICKED:
            raise ValidationError(
                {
                    "detail": "Submit the pick list first: "
                    "a delivery note is made from a picked list."
                }
            )
        if not p.lines.exists():
            raise ValidationError({"detail": "Nothing was picked on this list."})
        return Response(_fresh(make(p, request.user)), status=status.HTTP_201_CREATED)


class NoteDetailView(APIView):
    """GET one note (?print=1 adds the letterhead and addresses); PATCH a draft
    (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        n = _note(request, pk)
        data = _fresh(n)
        if request.query_params.get("print") == "1":
            data["letterhead"] = _letterhead(n.company)
            data["bill_from_address"] = _branch_address(n.bill_from) if n.bill_from else None
        return Response(data)

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        n = _note(request, pk, lock=True)
        if n.status != DeliveryNote.DRAFT:
            raise ValidationError(
                {"detail": "A submitted note cannot be changed. Cancel it and make a new one."}
            )
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(n, data)
        if data.get("submit"):
            if answer := refused(n, request.user):
                return answer
            _submit(n, request.user)
        return Response(_fresh(n))


class NoteSubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        n = _note(request, pk, lock=True)
        if n.status != DeliveryNote.DRAFT:
            raise ValidationError({"detail": "This note is not a draft."})
        if answer := refused(n, request.user):
            return answer
        _submit(n, request.user)
        return Response(_fresh(n))


class NoteCancelView(APIView):
    """POST {reason}: the goods go back into their bins and the entries are
    reversed; the order's lines are pending again."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        n = _note(request, pk, lock=True)
        if n.status == DeliveryNote.CANCELLED:
            raise ValidationError({"detail": "This note is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(n, request.user, reason)
        return Response(_fresh(n))


class NoteLedgerPostingView(APIView):
    """GET: the "Ledger Posting" section. A draft shows what Submit will post."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        n = _note(request, pk)
        if n.status == DeliveryNote.DRAFT:
            return Response(_posting_preview(n))
        return Response(posting_api.posted(KIND, n.pk))


class NotePlacesView(APIView):
    """GET ?item=ID: where that item may be sent from, with what is free
    (leaving out what the note's own pick list keeps aside)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        n = _note(request, pk)
        ln = (
            n.lines.select_related("item")
            .filter(item=request.query_params.get("item") or 0)
            .first()
        )
        if ln is None:
            raise ValidationError({"item": ["Pick an item of the note."]})
        return Response(
            [
                {
                    "location": s.location.pk,
                    "location_name": s.location.name,
                    "batch": s.batch.pk if s.batch else None,
                    "batch_number": s.batch.number if s.batch else "",
                    "expiry": s.expiry,
                    **package_out(s.package),
                    "free": picking.plain(s.free),
                }
                for s in picking.spots(ln.item, n.branch, n.area, n.pick_list)
            ]
        )


class NotePdfView(APIView):
    """GET ?layout=challan|packing (&download=1): the Delivery Challan (items,
    quantities, values, transport) or the Packing List (bins and batches)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from core import printout

        _check(request, "view")
        n = _note(request, pk)
        data = _fresh(n)
        packing = request.query_params.get("layout") == "packing"
        ship = data["ship_address"] or {}
        transport = " · ".join(
            x
            for x in [
                data["transporter_name"],
                data["mode_label"],
                data["vehicle_no"] and f"Vehicle {data['vehicle_no']}",
                data["lr_no"] and f"LR {data['lr_no']}",
                data["packages"] and f"{data['packages']} packages",
            ]
            if x
        )
        scope = " · ".join(
            x
            for x in [
                data["customer_name"],
                data["customer_gstin"] and f"GSTIN {data['customer_gstin']}",
                f"Sales Order {data['order_number']}",
                data["note_date"].strftime("%d-%m-%Y"),
                ship.get("label") and f"Ship to {ship.get('label')}",
                transport,
            ]
            if x
        )
        lines = [ln for ln in data["lines"] if Decimal(ln["qty"])]
        if packing:
            rows = []
            for ln in lines:
                first = True
                for b in ln["bins"]:
                    if not Decimal(b["qty"]):
                        continue
                    rows.append(
                        [
                            str(ln["position"]) if first else "",
                            ln["item_name"] if first else "",
                            b["location_name"],
                            b["batch_number"],
                            b["package_number"],
                            b["expiry"].strftime("%d-%m-%Y") if b["expiry"] else "",
                            f"{b['qty_unit']} {ln['unit_name']}",
                            f"{b['qty']} {ln['stock_unit_name']}",
                            "",
                        ]
                    )
                    first = False
            sheet = {
                "title": "",
                "columns": [
                    "#",
                    "Item",
                    "Bin",
                    "Batch",
                    "Package",
                    "Expiry",
                    "Qty",
                    "In Stock Unit",
                    "Checked",
                ],
                "rows": rows,
            }
            title = f"Packing List {data['number'] or 'Draft'}"
        else:
            rows = [
                [
                    str(ln["position"]),
                    ln["item_name"],
                    ln["hsn"],
                    f"{ln['qty']} {ln['unit_name']}",
                    ln["rate"],
                    ln["taxable"],
                    f"{ln['gst_rate']}%",
                    ln["amount"],
                ]
                for ln in lines
            ]
            gst = "IGST" if data["interstate"] else "CGST + SGST"
            tax = Decimal(data["total"]) - Decimal(data["taxable_total"])
            rows.append(
                ["", "Total", "", "", "", data["taxable_total"], f"{gst} {tax}", data["total"]]
            )
            sheet = {
                "title": "",
                "columns": ["#", "Item", "HSN", "Qty", "Rate ₹", "Taxable ₹", "GST", "Value ₹"],
                "rows": rows,
            }
            title = f"Delivery Challan {data['number'] or 'Draft'}"
        response = printout.pdf_response(title, scope, [sheet], data["number"] or "delivery-note")
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
