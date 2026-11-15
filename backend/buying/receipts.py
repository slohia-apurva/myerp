"""Goods receipts (Entry > Purchase > Goods Receipt).

Either the purchase or the stock rights (`purchase.*` or `stock.*`) will do. A
receipt is saved as a draft and finished later; Submit numbers it, makes any
new batches typed on its lines, posts the stock and the GL through
posting.service, and adds the accepted quantities to the orders. More than
the order may be accepted: the Purchase team and the Owner are told
(Sidharth, 2026-11-07). Cancel reverses all of it.
"""

import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from audit.models import AuditEntry
from buying.api import _company
from buying.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    GoodsReceiptPutaway,
    PurchaseOrder,
    PurchaseOrderLine,
)
from core import numbering
from core.api import Signed
from core.batches import save_batch
from core.companies import visible_companies
from core.models import Batch, Branch, Item, ItemUnit, Ledger, WarehouseLocation
from core.notifications import notify, people_with_roles
from posting import accounts, service
from posting.service import GLLine, StockLine, Voucher, money
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic

ZERO = Decimal("0")
KIND = "goods_receipt"
VIEW, CREATE, SUBMIT, CANCEL = "view", "create", "submit", "cancel"


def can(user, action: str) -> bool:
    """Goods are received by the stores or by purchase: either role's right will do."""
    return user.can(f"purchase.{action}") or user.can(f"stock.{action}")


def _check(request, action: str) -> None:
    if not can(request.user, action):
        raise PermissionDenied("Your role does not allow this.")


def _text(value):
    """Decimals as strings (never floats) all through a reply."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _text(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_text(v) for v in value]
    return value


def _rate(ol: PurchaseOrderLine) -> Decimal:
    """Rupees (or the order's currency) per unit after discount, before GST."""
    return (ol.taxable / ol.qty).quantize(Decimal("0.000001")) if ol.qty else ZERO


def _num(value: Decimal) -> str:
    return f"{value.normalize():f}" if value else "0"


# Reading ---------------------------------------------------------------------


def _receipts(company):
    return (
        GoodsReceipt.objects.filter(company=company)
        .select_related("supplier", "branch", "transporter", "received_by", "qc_by", "submitted_by")
        .prefetch_related(
            "orders",
            "lines__item",
            "lines__unit",
            "lines__order_line__order",
            "lines__putaways__location__parent",
            "lines__putaways__batch",
        )
    )


def _earlier(line: GoodsReceiptLine) -> Decimal:
    """Accepted on other submitted receipts of the same order line."""
    rows = GoodsReceiptLine.objects.filter(
        order_line=line.order_line, receipt__status=GoodsReceipt.SUBMITTED
    ).exclude(receipt=line.receipt)
    return sum((r.accepted_qty for r in rows), ZERO)


def _putaway_out(p: GoodsReceiptPutaway) -> dict:
    return {
        "location": p.location_id,
        "location_name": str(p.location),
        "batch": p.batch_id,
        "batch_number": p.batch.number if p.batch_id else p.batch_number,
        "new_batch": p.batch_id is None and bool(p.batch_number),
        "mfg_date": p.batch.mfg_date if p.batch_id else p.mfg_date,
        "expiry_date": p.batch.expiry_date if p.batch_id else p.expiry_date,
        "qty": p.qty,
    }


def _line_out(ln: GoodsReceiptLine) -> dict:
    ol = ln.order_line
    return {
        "order_line": ol.pk,
        "order": ol.order_id,
        "order_number": ol.order.number,
        "order_position": ol.position,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "batch_tracked": ln.item.batch_tracked,
        "qc_required": ln.item.qc_required,
        "unit": ln.unit_id,
        "unit_name": ln.unit.short_name,
        "rate": _rate(ol),
        "ordered": ol.qty,
        "earlier": _earlier(ln),
        "received_qty": ln.received_qty,
        "rejected_qty": ln.rejected_qty,
        "accepted_qty": ln.accepted_qty,
        "value": ln.value,
        "charges_value": ln.charges_value,
        "putaways": [_putaway_out(p) for p in ln.putaways.all()],
    }


def _receipt_out(r: GoodsReceipt, lines: bool = True) -> dict:
    out = {
        "id": r.id,
        "company": r.company_id,
        "number": r.number,
        "status": r.status,
        "status_label": r.get_status_display(),
        "supplier": r.supplier_id,
        "supplier_name": r.supplier.name,
        "branch": r.branch_id,
        "branch_name": r.branch.name,
        "receipt_date": r.receipt_date,
        "orders": [o.pk for o in r.orders.all()],
        "order_numbers": [o.number for o in r.orders.all()],
        "challan_no": r.challan_no,
        "challan_date": r.challan_date,
        "transporter": r.transporter_id,
        "transporter_name": r.transporter.name if r.transporter_id else "By Supplier",
        "lr_no": r.lr_no,
        "vehicle_no": r.vehicle_no,
        "eway_bill_no": r.eway_bill_no,
        "received_by": r.received_by_id,
        "received_by_name": r.received_by.display_name if r.received_by_id else "",
        "currency": r.currency,
        "exchange_rate": r.exchange_rate,
        "qc_cartons": r.qc_cartons,
        "qc_batch_print": r.qc_batch_print,
        "qc_by": r.qc_by_id,
        "qc_by_name": r.qc_by.display_name if r.qc_by_id else "",
        "notes": r.notes,
        "stock_value": r.stock_value,
        "accepted_total": sum((ln.accepted_qty for ln in r.lines.all()), ZERO),
        "cancel_reason": r.cancel_reason,
        "submitted_at": r.submitted_at,
        "submitted_by_name": r.submitted_by.display_name if r.submitted_by_id else "",
    }
    if lines:
        out["lines"] = [_line_out(ln) for ln in r.lines.all()]
    return out


def _fresh(r: GoodsReceipt) -> dict:
    return _text(_receipt_out(_receipts(r.company).get(pk=r.pk)))


def pending_lines(order: PurchaseOrder) -> list[dict]:
    """Stock lines of an order with what is still to come, for "Get items"."""
    out = []
    for ol in order.lines.select_related("item", "unit"):
        if not ol.item.maintain_stock:
            continue
        out.append(
            {
                "order_line": ol.pk,
                "order": order.pk,
                "order_number": order.number,
                "order_position": ol.position,
                "item": ol.item_id,
                "item_name": ol.item.name,
                "item_number": ol.item.item_number,
                "batch_tracked": ol.item.batch_tracked,
                "qc_required": ol.item.qc_required,
                "unit": ol.unit_id,
                "unit_name": ol.unit.short_name,
                "rate": _rate(ol),
                "ordered": ol.qty,
                "earlier": ol.received_qty,
                "pending": max(ol.qty - ol.received_qty, ZERO),
            }
        )
    return out


# Saving ----------------------------------------------------------------------


class PutawaySerializer(serializers.Serializer):
    location = serializers.IntegerField()
    batch = serializers.IntegerField(required=False, allow_null=True)
    batch_number = serializers.CharField(required=False, allow_blank=True, max_length=60)
    mfg_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))


class LineSerializer(serializers.Serializer):
    order_line = serializers.IntegerField()
    received_qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=0)
    rejected_qty = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=0, required=False, default=ZERO
    )
    putaways = PutawaySerializer(many=True, required=False, default=list)


class ReceiptSerializer(serializers.Serializer):
    supplier = serializers.IntegerField()
    branch = serializers.IntegerField()
    receipt_date = serializers.DateField()
    orders = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    challan_no = serializers.CharField(required=False, allow_blank=True, max_length=40)
    challan_date = serializers.DateField(required=False, allow_null=True)
    transporter = serializers.IntegerField(required=False, allow_null=True)
    lr_no = serializers.CharField(required=False, allow_blank=True, max_length=40)
    vehicle_no = serializers.CharField(required=False, allow_blank=True, max_length=20)
    eway_bill_no = serializers.CharField(required=False, allow_blank=True, max_length=20)
    received_by = serializers.IntegerField(required=False, allow_null=True)
    exchange_rate = serializers.DecimalField(
        max_digits=18, decimal_places=9, required=False, allow_null=True, min_value=0
    )
    qc_cartons = serializers.ChoiceField(
        choices=["", *dict(GoodsReceipt.CARTONS)], required=False, allow_blank=True
    )
    qc_batch_print = serializers.ChoiceField(
        choices=["", *dict(GoodsReceipt.PRINTS)], required=False, allow_blank=True
    )
    qc_by = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = LineSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _user(value, field: str):
    if value in (None, ""):
        return None
    user = User.objects.filter(pk=value, is_active=True).first()
    if user is None:
        raise ValidationError({field: ["Pick a person from the list."]})
    return user


def _save(r: GoodsReceipt, data: dict) -> None:
    company = r.company
    supplier = Ledger.objects.filter(
        pk=data["supplier"], company=company, party_side="supplier"
    ).first()
    if supplier is None:
        raise ValidationError({"supplier": ["Pick a supplier of this company."]})
    branch = Branch.objects.filter(pk=data["branch"], company=company, is_active=True).first()
    if branch is None or branch.no_stock:
        raise ValidationError({"branch": ["Pick a branch of this company that holds stock."]})
    orders = list(
        PurchaseOrder.objects.filter(pk__in=data["orders"], company=company).select_related(
            "branch"
        )
    )
    if len(orders) != len(set(data["orders"])):
        raise ValidationError({"orders": ["Pick orders of this company."]})
    for o in orders:
        if o.supplier_id != supplier.pk:
            raise ValidationError({"orders": [f"{o.number} is not an order of {supplier}."]})
        if o.status not in PurchaseOrder.OPEN:
            raise ValidationError({"orders": [f"{o.number} is {o.get_status_display().lower()}."]})
        if o.branch_id != branch.pk:
            raise ValidationError({"orders": [f"{o.number} is for {o.branch}, not {branch}."]})
    currencies = {o.currency for o in orders}
    if len(currencies) > 1:
        raise ValidationError(
            {"orders": ["Orders in different currencies need separate receipts."]}
        )
    transporter = None
    if data.get("transporter"):
        transporter = CourierAccount.objects.filter(pk=data["transporter"], company=company).first()
        if transporter is None:
            raise ValidationError({"transporter": ["Pick one of this company's transporters."]})

    r.supplier, r.branch = supplier, branch
    r.receipt_date = data["receipt_date"]
    r.currency = currencies.pop() if currencies else "INR"
    r.exchange_rate = data.get("exchange_rate") if r.currency != "INR" else None
    for f in ("challan_no", "lr_no", "vehicle_no", "eway_bill_no", "notes"):
        setattr(r, f, (data.get(f) or "").strip())
    r.vehicle_no = r.vehicle_no.upper()
    r.challan_date = data.get("challan_date")
    r.transporter = transporter
    r.received_by = _user(data.get("received_by"), "received_by")
    r.qc_by = _user(data.get("qc_by"), "qc_by")
    r.qc_cartons = data.get("qc_cartons") or ""
    r.qc_batch_print = data.get("qc_batch_print") or ""
    r.save()
    r.orders.set(orders)

    order_lines = {
        ol.pk: ol
        for ol in PurchaseOrderLine.objects.filter(order__in=orders).select_related("item", "unit")
    }
    places = {
        p.pk: p
        for p in WarehouseLocation.objects.filter(branch=branch, is_active=True).exclude(
            kind=WarehouseLocation.RACK
        )
    }
    r.lines.all().delete()
    errors: dict[str, list[str]] = {}
    seen = set()
    for n, line in enumerate(data["lines"], start=1):
        ol = order_lines.get(line["order_line"])
        if ol is None:
            errors.setdefault("lines", []).append(f"Line {n}: not a line of the orders picked.")
            continue
        if ol.pk in seen:
            errors.setdefault("lines", []).append(f"Line {n}: {ol.item} is on the receipt twice.")
            continue
        seen.add(ol.pk)
        if line["rejected_qty"] > line["received_qty"]:
            errors.setdefault("lines", []).append(
                f"Line {n}: {ol.item} rejects more than was received."
            )
            continue
        ln = GoodsReceiptLine.objects.create(
            receipt=r,
            position=n,
            order_line=ol,
            item=ol.item,
            unit=ol.unit,
            received_qty=line["received_qty"],
            rejected_qty=line["rejected_qty"],
            accepted_qty=line["received_qty"] - line["rejected_qty"],
        )
        for m, p in enumerate(line["putaways"], start=1):
            place = places.get(p["location"])
            if place is None:
                errors.setdefault("lines", []).append(
                    f"Line {n}: pick a bin or area of {branch} for each part."
                )
                continue
            batch = None
            if p.get("batch"):
                batch = Batch.objects.filter(pk=p["batch"], item=ol.item).first()
                if batch is None:
                    errors.setdefault("lines", []).append(
                        f"Line {n}: that batch is not a batch of {ol.item}."
                    )
                    continue
            number = " ".join((p.get("batch_number") or "").split())
            if batch is None and number:
                batch = Batch.objects.filter(item=ol.item, number__iexact=number).first()
            GoodsReceiptPutaway.objects.create(
                line=ln,
                position=m,
                location=place,
                batch=batch,
                batch_number="" if batch else number,
                mfg_date=None if batch else p.get("mfg_date"),
                expiry_date=None if batch else p.get("expiry_date"),
                qty=p["qty"],
            )
    if errors:
        raise ValidationError(errors)


# Submit ----------------------------------------------------------------------


def _factor(item: Item, unit_id: int) -> Decimal:
    if unit_id == item.stock_unit_id:
        return Decimal("1")
    row = ItemUnit.objects.filter(item=item, unit_id=unit_id).first()
    if row is None:
        raise ValidationError({"lines": [f"{item.name} has no conversion for its order unit."]})
    return row.factor


def _charges_for(lines: list[GoodsReceiptLine]) -> dict[int, Decimal]:
    """The order charges marked "Add to Stock Cost", spread over this receipt's
    lines: each order line carries its share of the charge (by quantity or by
    value), per unit ordered, times what was accepted now."""
    out: dict[int, Decimal] = defaultdict(lambda: ZERO)
    by_order = defaultdict(list)
    for ln in lines:
        by_order[ln.order_line.order_id].append(ln)
    for ln_list in by_order.values():
        order = ln_list[0].order_line.order
        stock_lines = [ol for ol in order.lines.select_related("item") if ol.item.maintain_stock]
        for charge in order.charges.all():
            if charge.add_to_stock == Item.NO_STOCK_COST or not charge.amount:
                continue

            def weight(ol, basis=charge.add_to_stock):
                return ol.qty if basis == Item.BY_QTY else ol.taxable

            total = sum((weight(ol) for ol in stock_lines), ZERO)
            if not total:
                continue
            for ln in ln_list:
                ol = ln.order_line
                share = charge.amount * weight(ol) / total
                out[ln.pk] += share / ol.qty * ln.accepted_qty
    return out


def _new_batch(item: Item, p: GoodsReceiptPutaway) -> Batch:
    found = Batch.objects.filter(item=item, number__iexact=p.batch_number).first()
    if found is not None:
        return found
    status_ = Batch.QUARANTINE if item.qc_required else Batch.RELEASED
    return save_batch(
        Batch(),
        {
            "item": item,
            "number": p.batch_number,
            "mfg_date": p.mfg_date,
            "expiry_date": p.expiry_date,
            "status": status_,
            "notes": "Made by a goods receipt",
        },
    )


def _over_receipts(r: GoodsReceipt, user) -> None:
    """Tell the Purchase team and the Owner about lines accepted beyond their
    order, and note it in each order's activity."""
    rows = []
    for ln in r.lines.select_related("order_line__order", "item", "unit"):
        ol = ln.order_line
        if ol.received_qty > ol.qty:
            rows.append((ol, ln))
    if not rows:
        return
    who = r.received_by.display_name if r.received_by_id else user.display_name
    for ol, ln in rows:
        o = ol.order
        text = (
            f"{ln.item.name}: {_num(ol.received_qty)} {ln.unit.short_name} received against "
            f"{_num(ol.qty)} ordered on {o.number} ({_num(ol.received_qty - ol.qty)} over), "
            f"by {r.number}, received by {who}."
        )
        notify(
            people_with_roles(r.company, "purchase", "owner"),
            r.company,
            f"Over-receipt on {o.number}",
            text,
            f"#/companies/{r.company_id}/goods-receipts?open={r.pk}",
        )
        AuditEntry.objects.create(
            user=user,
            user_name=user.display_name[:150],
            company=r.company,
            record_type="purchase_order",
            record_id=o.pk,
            record_name=str(o)[:200],
            action=AuditEntry.UPDATE,
            changes=[{"field": "over_receipt", "label": "Over-receipt", "old": None, "new": text}],
        )


def _order_status(o: PurchaseOrder) -> None:
    lines = [ol for ol in o.lines.select_related("item") if ol.item.maintain_stock]
    got = [ol.received_qty for ol in lines]
    if lines and all(ol.received_qty >= ol.qty for ol in lines):
        o.status = PurchaseOrder.RECEIVED
    elif any(g > 0 for g in got):
        o.status = PurchaseOrder.PART_RECEIVED
    else:
        o.status = PurchaseOrder.ORDERED
    o.save()


def _submit(r: GoodsReceipt, user) -> None:
    if not can(user, SUBMIT):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    lines = list(
        r.lines.select_related("item", "unit", "order_line__order").prefetch_related(
            "putaways__location", "putaways__batch"
        )
    )
    lines = [ln for ln in lines if ln.received_qty > 0]
    if not any(ln.accepted_qty > 0 for ln in lines):
        raise ValidationError({"lines": ["Receive at least one item before submitting."]})
    if r.currency != "INR" and not r.exchange_rate:
        raise ValidationError(
            {"exchange_rate": [f"Give the exchange rate: rupees per {r.currency}."]}
        )
    errors = []
    for ln in lines:
        puts = list(ln.putaways.all())
        total = sum((p.qty for p in puts), ZERO)
        unit = ln.unit.short_name
        if total != ln.accepted_qty:
            errors.append(
                f"{ln.item.name}: {_num(total)} of {_num(ln.accepted_qty)} {unit} put away; "
                "put away all of the accepted quantity."
            )
        for p in puts:
            has_batch = p.batch_id or p.batch_number
            if ln.item.batch_tracked and not has_batch:
                errors.append(f"{ln.item.name}: give the batch for each bin.")
            if not ln.item.batch_tracked and has_batch:
                errors.append(f"{ln.item.name} does not keep batches.")
    if errors:
        raise ValidationError({"lines": sorted(set(errors), key=errors.index)})

    r.number = numbering.next_document_number(r.company, KIND, r.receipt_date, r.branch)
    rate_to_inr = r.exchange_rate if r.currency != "INR" else Decimal("1")
    charges = _charges_for(lines)
    stock: list[StockLine] = []
    owners: list[GoodsReceiptLine] = []
    for ln in lines:
        if ln.accepted_qty <= 0:
            continue
        ol = ln.order_line
        factor = _factor(ln.item, ln.unit_id)
        goods = ol.taxable / ol.qty * ln.accepted_qty * rate_to_inr
        extra = charges.get(ln.pk, ZERO) * rate_to_inr
        stock_rate = (goods + extra) / (ln.accepted_qty * factor)
        ln.charges_value = money(extra)
        for p in ln.putaways.all():
            if p.batch_id is None and p.batch_number:
                p.batch = _new_batch(ln.item, p)
                p.batch_number = ""
                p.save(update_fields=["batch", "batch_number"])
            stock.append(
                StockLine(
                    ln.item,
                    p.location,
                    p.qty * factor,
                    stock_rate.quantize(Decimal("0.000001")),
                    batch=p.batch,
                )
            )
            owners.append(ln)
    grni = accounts.system_ledger(r.company, accounts.GRNI)

    def gl(values):
        per_ledger: dict[int, Decimal] = defaultdict(lambda: ZERO)
        ledgers = {}
        for ln, value in zip(owners, values, strict=True):
            led = accounts.stock_ledger(r.company, ln.item)
            ledgers[led.pk] = led
            per_ledger[led.pk] += value
        total = sum(per_ledger.values(), ZERO)
        return [GLLine(ledgers[k], debit=v) for k, v in per_ledger.items()] + [
            GLLine(grni, credit=total, remarks=f"Goods from {r.supplier}")
        ]

    voucher = Voucher(r.company, r.branch, r.receipt_date, KIND, r.pk, r.number, user)
    done = service.post(voucher, stock=stock, gl=gl)
    line_values: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for ln, value in zip(owners, done.stock_values, strict=True):
        line_values[ln.pk] += value
    for ln in lines:
        ln.value = line_values.get(ln.pk, ZERO)
        ln.save(update_fields=["value", "charges_value"])
        ol = PurchaseOrderLine.objects.select_for_update().get(pk=ln.order_line_id)
        ol.received_qty += ln.accepted_qty
        ol.save(update_fields=["received_qty"])
    r.stock_value = sum(line_values.values(), ZERO)
    r.status = GoodsReceipt.SUBMITTED
    r.submitted_at = timezone.now()
    r.submitted_by = user
    r.save()
    for o in r.orders.all():
        _order_status(o)
    _over_receipts(r, user)


def _cancel(r: GoodsReceipt, user, reason: str) -> None:
    if r.status == GoodsReceipt.SUBMITTED:
        service.cancel(KIND, r.pk, user)
        for ln in r.lines.all():
            ol = PurchaseOrderLine.objects.select_for_update().get(pk=ln.order_line_id)
            ol.received_qty -= ln.accepted_qty
            ol.save(update_fields=["received_qty"])
        for o in r.orders.all():
            _order_status(o)
    r.status = GoodsReceipt.CANCELLED
    r.cancel_reason = reason[:200]
    r.save()


# Views -----------------------------------------------------------------------


def _receipt(request, pk: int, lock: bool = False) -> GoodsReceipt:
    rows = GoodsReceipt.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    r = rows.select_related("company").first()
    if r is None or "purchase" not in r.company.modules:
        raise NotFound("No such goods receipt.")
    return r


class ReceiptListView(APIView):
    """GET ?view=draft|submitted|cancelled|all&q=text. POST makes a draft (or,
    with "submit": true, submits it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = _receipts(company)
        view = request.query_params.get("view", "all")
        if view in (GoodsReceipt.DRAFT, GoodsReceipt.SUBMITTED, GoodsReceipt.CANCELLED):
            rows = rows.filter(status=view)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(supplier__name__icontains=word)
                | Q(challan_no__icontains=word)
                | Q(orders__number__icontains=word)
                | Q(lines__item__name__icontains=word)
            ).distinct()
        return Response(_text([_receipt_out(r, lines=False) for r in rows[:1000]]))

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        serializer = ReceiptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        r = GoodsReceipt(company=company, created_by=request.user)
        _save(r, data)
        if data.get("submit"):
            _submit(r, request.user)
        return Response(_fresh(r), status=status.HTTP_201_CREATED)


class ReceiptDetailView(APIView):
    permission_classes = ReceiptListView.permission_classes

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(_fresh(_receipt(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        r = _receipt(request, pk, lock=True)
        if r.status != GoodsReceipt.DRAFT:
            raise ValidationError(
                {"detail": "A submitted receipt cannot be changed. Cancel it and make a new one."}
            )
        serializer = ReceiptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(r, data)
        if data.get("submit"):
            _submit(r, request.user)
        return Response(_fresh(r))


class ReceiptSubmitView(APIView):
    permission_classes = ReceiptListView.permission_classes

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        r = _receipt(request, pk, lock=True)
        if r.status != GoodsReceipt.DRAFT:
            raise ValidationError({"detail": "This receipt is already submitted."})
        _submit(r, request.user)
        return Response(_fresh(r))


class ReceiptCancelView(APIView):
    """POST {reason}. Reverses the stock and GL; refused if the goods have since
    been issued or moved."""

    permission_classes = ReceiptListView.permission_classes

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CANCEL)
        r = _receipt(request, pk, lock=True)
        if r.status == GoodsReceipt.CANCELLED:
            raise ValidationError({"detail": "This receipt is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(r, request.user, reason)
        return Response(_fresh(r))


class PendingOrdersView(APIView):
    """GET ?supplier=ID&branch=ID: the supplier's open orders for that branch,
    each with its lines still to come ("Get items")."""

    permission_classes = ReceiptListView.permission_classes

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = PurchaseOrder.objects.filter(
            company=company, status__in=PurchaseOrder.OPEN
        ).select_related("branch", "supplier")
        if s := request.query_params.get("supplier"):
            rows = rows.filter(supplier_id=s) if s.isdigit() else rows.none()
        if b := request.query_params.get("branch"):
            rows = rows.filter(branch_id=b) if b.isdigit() else rows.none()
        return Response(
            _text(
                [
                    {
                        "id": o.pk,
                        "number": o.number,
                        "order_date": o.order_date,
                        "supplier": o.supplier_id,
                        "supplier_name": o.supplier.name,
                        "branch": o.branch_id,
                        "branch_name": o.branch.name,
                        "currency": o.currency,
                        "transporter": o.transporter_id,
                        "lines": pending_lines(o),
                    }
                    for o in rows.order_by("order_date", "id")
                ]
            )
        )


class ReceiptSetupView(APIView):
    """What the form's pickers need: the stock-holding branches with their bins
    and areas, the transporters and the people."""

    permission_classes = ReceiptListView.permission_classes

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        branches = Branch.objects.filter(company=company, is_active=True, no_stock=False)
        places = WarehouseLocation.objects.filter(
            branch__in=branches, is_active=True
        ).select_related("parent")
        return Response(
            {
                "branches": [{"id": b.pk, "name": b.name} for b in branches],
                "locations": [
                    {
                        "id": p.pk,
                        "branch": p.branch_id,
                        "kind": p.kind,
                        "name": str(p),
                        "is_default": p.is_default,
                        "purpose": p.purpose,
                    }
                    for p in places
                    if p.kind != WarehouseLocation.RACK
                ],
                "transporters": [
                    {"id": t.pk, "name": t.name}
                    for t in CourierAccount.objects.filter(company=company, is_active=True)
                ],
                "users": [
                    {"id": u.pk, "name": u.display_name}
                    for u in User.objects.filter(is_active=True).order_by("full_name", "email")
                ],
                "suppliers": [
                    {"id": s.pk, "name": s.name}
                    for s in Ledger.objects.filter(
                        company=company,
                        party_side="supplier",
                        purchase_orders__status__in=PurchaseOrder.OPEN,
                    )
                    .distinct()
                    .order_by("name")
                ],
                "can_submit": can(request.user, SUBMIT),
                "can_cancel": can(request.user, CANCEL),
                "can_create": can(request.user, CREATE),
                "today": datetime.date.today(),
            }
        )
