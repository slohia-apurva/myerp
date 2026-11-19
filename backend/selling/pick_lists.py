"""Pick lists (Entry > Sales > Pick List): where the stores take a sales
order's goods from (Sidharth, 2026-11-19, preview 6).

A list is made by itself when the order is submitted (selling.picking). An
open list can be changed: another bin or batch, a different quantity, rows
added or taken out. "Submit" makes it final ("Picked"). "Cancel" frees the
stock it kept aside; "Pick List" under the order's "Create ▾" makes a new one.

Who may do what: people who may see sales or stock see them; who may make
sales or stock entries change them; submit and cancel likewise. Nothing here
posts to either ledger.
"""

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from core.api import Signed
from core.companies import visible_companies
from core.models import Batch
from selling import picking, stock
from selling.api import _company
from selling.api import _order as _sales_order
from selling.models import PickList, PickListLine, SalesOrder, SalesOrderLine
from tenancy.context import tenant_atomic

ZERO = Decimal("0")


def may(user, action: str) -> bool:
    return user.can(f"sales.{action}") or user.can(f"stock.{action}")


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with pick lists.")


def _pick(request, pk: int, lock: bool = False) -> PickList:
    rows = PickList.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    p = rows.select_related("company", "order", "branch", "area").first()
    if p is None or "sales" not in p.company.modules:
        raise NotFound("No such pick list.")
    return p


def place_label(p: PickList) -> str:
    return f"{p.branch.name} › {p.area.name}" if p.area_id else p.branch.name


def brief(p: PickList) -> dict:
    """What the sales order shows of its pick list."""
    s = picking.summary(p)
    return {
        "id": p.pk,
        "number": p.number,
        "status": p.status,
        "status_label": p.get_status_display(),
        "all_in": s["all_in"],
        "full_count": s["full"],
        "item_count": s["count"],
        "text": s["text"],
    }


def pick_out(p: PickList, full: bool = True) -> dict:
    s = picking.summary(p)
    data = {
        **brief(p),
        "company": p.company_id,
        "order": p.order_id,
        "order_number": p.order.number,
        "customer_name": p.order.customer.name,
        "order_date": p.order.order_date,
        "delivery_date": p.order.delivery_date,
        "despatch_from": place_label(p),
        "branch": p.branch_id,
        "area": p.area_id,
        "notes": p.notes,
        "cancel_reason": p.cancel_reason,
        "created_at": p.created_at,
        "created_by_name": p.created_by.display_name if p.created_by else "",
        "submitted_at": p.submitted_at,
        "submitted_by_name": p.submitted_by.display_name if p.submitted_by else "",
    }
    if not full:
        return data
    data["items"] = [
        {
            "order_line": i["line"].pk,
            "position": i["line"].position,
            "item": i["line"].item_id,
            "item_name": i["line"].item.name,
            "unit_name": i["unit_name"],
            "stock_unit_name": i["stock_unit_name"],
            "factor": picking.plain(i["factor"]),
            "ordered": picking.plain(i["want"] / i["factor"]),
            "picked": picking.plain(i["got"] / i["factor"]),
            "picked_stock": picking.plain(i["got"]),
            "short": picking.plain(i["short"] / i["factor"]),
            "short_stock": picking.plain(i["short"]),
            "rows": [
                {
                    "id": r.pk,
                    "location": r.location_id,
                    "location_name": r.location.name,
                    "batch": r.batch_id,
                    "batch_number": r.batch.number if r.batch else "",
                    "expiry": r.batch.expiry_date if r.batch else None,
                    "qty": picking.plain(r.qty),
                    "qty_unit": picking.plain(r.qty / i["factor"]),
                }
                for r in i["rows"]
            ],
        }
        for i in s["items"]
    ]
    return data


def _fresh(p: PickList) -> dict:
    return pick_out(
        PickList.objects.select_related(
            "company", "order__customer", "branch", "area", "created_by", "submitted_by"
        ).get(pk=p.pk)
    )


class RowSerializer(serializers.Serializer):
    order_line = serializers.IntegerField()
    location = serializers.IntegerField()
    batch = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=18, decimal_places=6)  # in the stock unit


class PickSerializer(serializers.Serializer):
    rows = RowSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True)


def _check_rows(p: PickList, rows: list[PickListLine]) -> None:
    """Every row takes from a place in the Despatch From that has that much
    free (stock less what other lists keep aside), and no line gets more than
    it still needs."""
    errors = []
    by_item: dict[int, dict] = {}
    asked: dict[tuple, Decimal] = {}
    for r in rows:
        if r.item_id not in by_item:
            by_item[r.item_id] = {s.key: s for s in picking.spots(r.item, p.branch, p.area, p)}
        key = (r.item_id, (r.location_id, r.batch_id))
        asked[key] = asked.get(key, ZERO) + r.qty
    for (item_id, spot_key), qty in asked.items():
        spot = by_item[item_id].get(spot_key)
        free = spot.free if spot else ZERO
        if qty > free:
            r = next(
                x for x in rows if (x.item_id, (x.location_id, x.batch_id)) == (item_id, spot_key)
            )
            where = r.location.name + (f", batch {r.batch.number}" if r.batch else "")
            errors.append(
                f"{r.item.name}: {where} has {picking.plain(free)} free, not {picking.plain(qty)}."
            )
    per_line: dict[int, Decimal] = {}
    for r in rows:
        per_line[r.order_line_id] = per_line.get(r.order_line_id, ZERO) + r.qty
    for line in SalesOrderLine.objects.filter(pk__in=per_line).select_related("item"):
        want = picking.pending(line) * picking.factor(line)
        if per_line[line.pk] > want:
            errors.append(
                f"{line.item.name}: picks {picking.plain(per_line[line.pk])}, more than the "
                f"{picking.plain(want)} still to go."
            )
    if errors:
        raise ValidationError({"rows": errors})


def _save(p: PickList, data: dict) -> None:
    lines = {ln.pk: ln for ln in p.order.lines.select_related("item")}
    places = {x.pk: x for x in stock.places(p.branch, p.area)}
    rows, errors = [], []
    for n, row in enumerate(data["rows"], start=1):
        line = lines.get(row["order_line"])
        if line is None or not line.item.maintain_stock:
            errors.append(f"Row {n}: pick an item of the order.")
            continue
        place = places.get(row["location"])
        if place is None:
            errors.append(f"Row {n}: pick a bin in {place_label(p)}.")
            continue
        batch = None
        if row.get("batch"):
            batch = Batch.objects.filter(pk=row["batch"], item=line.item_id).first()
            if batch is None:
                errors.append(f"Row {n}: pick a batch of {line.item.name}.")
                continue
            if batch.status in picking.HELD:
                errors.append(
                    f"Row {n}: batch {batch.number} is {batch.get_status_display()} "
                    "and cannot be picked."
                )
                continue
        if row["qty"] <= 0:
            errors.append(f"Row {n}: the quantity must be more than zero.")
            continue
        rows.append(
            PickListLine(
                pick_list=p,
                order_line=line,
                position=line.position,
                item=line.item,
                location=place,
                batch=batch,
                qty=row["qty"],
            )
        )
    if errors:
        raise ValidationError({"rows": errors})
    _check_rows(p, rows)
    p.notes = data.get("notes", p.notes).strip()
    p.save()
    p.lines.all().delete()
    PickListLine.objects.bulk_create(rows)


VIEWS = {
    "open": [PickList.OPEN],
    "picked": [PickList.PICKED],
    "cancelled": [PickList.CANCELLED],
}


class PickListView(APIView):
    """GET ?view=open|picked|cancelled|all: the company's pick lists."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        rows = PickList.objects.filter(company=company).select_related(
            "company", "order__customer", "branch", "area", "created_by", "submitted_by"
        )
        view = request.query_params.get("view", "open")
        if view in VIEWS:
            rows = rows.filter(status__in=VIEWS[view])
        return Response([pick_out(p, full=False) for p in rows[:500]])


class PickDetailView(APIView):
    """GET one list; PATCH an open one: {rows: [{order_line, location, batch,
    qty}], notes}."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(_fresh(_pick(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        p = _pick(request, pk, lock=True)
        if p.status != PickList.OPEN:
            raise ValidationError({"detail": "Only an open pick list can be changed."})
        serializer = PickSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _save(p, dict(serializer.validated_data))
        return Response(_fresh(p))


class PickSubmitView(APIView):
    """POST: the goods are picked; the list is final."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        p = _pick(request, pk, lock=True)
        if p.status != PickList.OPEN:
            raise ValidationError({"detail": "This pick list is not open."})
        rows = list(p.lines.select_related("item", "location", "batch"))
        if not rows:
            raise ValidationError({"detail": "Nothing is picked: add a bin for at least one item."})
        bad = [r for r in rows if r.batch and r.batch.status in picking.HELD]
        if bad:
            raise ValidationError(
                {
                    "rows": [
                        f"Batch {r.batch.number} is {r.batch.get_status_display()}." for r in bad
                    ]
                }
            )
        _check_rows(p, rows)
        p.status = PickList.PICKED
        p.submitted_at = timezone.now()
        p.submitted_by = request.user
        p.save()
        return Response(_fresh(p))


def cancel(p: PickList, user, reason: str) -> None:
    p.status = PickList.CANCELLED
    p.cancel_reason = reason[:200]
    p.save()
    AuditEntry.objects.create(
        user=user,
        user_name=user.display_name[:150],
        company=p.company,
        record_type="sales_order",
        record_id=p.order_id,
        record_name=str(p.order)[:200],
        action=AuditEntry.UPDATE,
        changes=[
            {
                "field": "pick_list",
                "label": "Pick list",
                "old": p.number,
                "new": f"{p.number} cancelled: {p.cancel_reason}",
            }
        ],
    )


class PickCancelView(APIView):
    """POST {reason}: frees the stock the list kept aside."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        p = _pick(request, pk, lock=True)
        if p.status == PickList.CANCELLED:
            raise ValidationError({"detail": "This pick list is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        cancel(p, request.user, reason)
        return Response(_fresh(p))


class PickPlacesView(APIView):
    """GET ?item=ID: where that item of the list's order may be picked from, with
    what is free (leaving out what this list itself keeps aside)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        p = _pick(request, pk)
        line = (
            p.order.lines.select_related("item")
            .filter(item=request.query_params.get("item") or 0)
            .first()
        )
        if line is None:
            raise ValidationError({"item": ["Pick an item of the order."]})
        return Response(
            [
                {
                    "location": s.location.pk,
                    "location_name": s.location.name,
                    "batch": s.batch.pk if s.batch else None,
                    "batch_number": s.batch.number if s.batch else "",
                    "expiry": s.expiry,
                    "free": picking.plain(s.free),
                }
                for s in picking.spots(line.item, p.branch, p.area, p)
            ]
        )


class OrderPickView(APIView):
    """POST: a new pick list for what is still to go on a submitted order, when
    it has no open or picked one ("Create ▾ › Pick List")."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        o = _sales_order(request, pk, lock=True)
        if o.status not in SalesOrder.OPEN:
            raise ValidationError({"detail": "Only a submitted, open order gets a pick list."})
        if o.pick_lists.filter(status__in=PickList.HOLDING).exists():
            raise ValidationError({"detail": "This order already has a pick list."})
        p = picking.make(o, request.user)
        if p is None:
            raise ValidationError({"detail": "Nothing on this order is left to pick."})
        return Response(_fresh(p), status=201)


class PickPdfView(APIView):
    """GET: the list for the stores to pick from, as a PDF (?download=1 saves it).
    The last column is left blank to tick as each row is picked."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from core import printout

        _check(request, "view")
        data = _fresh(_pick(request, pk))
        rows = []
        for i in data["items"]:
            first = True
            ordered = f"{i['ordered']} {i['unit_name']}"
            status = "Full" if i["short"] == "0" else f"Short {i['short']} {i['unit_name']}"
            for r in i["rows"] or [None]:
                rows.append(
                    [
                        str(i["position"]) if first else "",
                        i["item_name"] if first else "",
                        ordered if first else "",
                        r["location_name"] if r else "Not found",
                        r["batch_number"] if r else "",
                        r["expiry"].strftime("%d-%m-%Y") if r and r["expiry"] else "",
                        f"{r['qty_unit']} {i['unit_name']}" if r else "",
                        f"{r['qty']} {i['stock_unit_name']}" if r else "",
                        status if first else "",
                        "",
                    ]
                )
                first = False
        sheet = {
            "title": data["text"],
            "columns": [
                "#", "Item", "Ordered", "Bin", "Batch", "Expiry", "Pick Qty",
                "In Stock Unit", "Status", "Picked",
            ],
            "rows": rows,
        }  # fmt: skip
        scope = " · ".join(
            [data["customer_name"], f"Sales Order {data['order_number']}", data["despatch_from"]]
        )
        response = printout.pdf_response(
            f"Pick List {data['number']}", scope, [sheet], data["number"]
        )
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
