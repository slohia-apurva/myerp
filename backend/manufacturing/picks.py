"""Picking the materials of a Manufacturing Order (Sidharth, 2026-11-23,
preview 17 in mockups/planning): the order is its own pick list.

On Submit each material gets its bins, batches and packages proposed by the
sales pick list rule (selling/picking.py: earliest expiry first, then oldest
received; Quarantine and Rejected batches never; stock picked for other lists
and open orders kept aside), from "Materials From" (else the whole branch). A
customer's goods come only from that customer's stock. While the order is open
the picks can be changed per material, or proposed again ("Pick again"), and
they are held for it. Quantities are in the item's stock unit; a material may
be picked short and the rest picked once stock comes in.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import Signed
from core.models import Batch, Item, Package
from manufacturing.boms import factor
from manufacturing.models import ManufacturingOrder, ManufacturingOrderPick
from selling import picking
from selling.stock import places
from tenancy.context import tenant_atomic

ZERO = Decimal("0")
MO = ManufacturingOrder
Pick = ManufacturingOrderPick


def _owner(mo: MO, item: Item):
    return mo.customer if item.default_request_type == Item.CUSTOMER_PROVIDED else None


def needs(mo: MO) -> dict[int, tuple[Item, Decimal]]:
    """Per material: the item and what is still to issue, in its stock unit."""
    out: dict[int, tuple[Item, Decimal]] = {}
    for ln in mo.lines.select_related("item"):
        if not ln.item.maintain_stock:
            continue
        left = max(ln.required - ln.issued, ZERO) * (factor(ln.item, ln.unit_id) or Decimal(1))
        item, had = out.get(ln.item_id, (ln.item, ZERO))
        out[ln.item_id] = (item, had + left)
    return out


def spots(mo: MO, item: Item) -> list[picking.Spot]:
    return picking.spots(
        item, mo.branch, mo.materials_from, owner=_owner(mo, item), leave_out_mo=mo
    )


def fill(mo: MO, items: set[int] | None = None) -> None:
    """Propose picks by the rule for every material (or only `items`),
    replacing what they had."""
    want = needs(mo)
    chosen = set(want) if items is None else items & set(want)
    mo.picks.filter(item__in=chosen if items is not None else want).delete()
    if items is None:
        mo.picks.exclude(item__in=want).delete()
    rows = []
    for item_id in chosen:
        item, need = want[item_id]
        for spot in spots(mo, item):
            if need <= 0:
                break
            take = min(spot.free, need)
            need -= take
            rows.append(
                Pick(
                    order=mo,
                    item=item,
                    location=spot.location,
                    batch=spot.batch,
                    package=spot.package,
                    qty=take,
                )
            )
    Pick.objects.bulk_create(rows)


def tidy(mo: MO) -> None:
    """After an open order is saved: picks for materials no longer on it go,
    a material picked beyond what is still to issue is trimmed from its last
    picks, and a new material gets its picks proposed."""
    want = needs(mo)
    mo.picks.exclude(item__in=want).delete()
    have: dict[int, list[Pick]] = {}
    for p in mo.picks.order_by("id"):
        have.setdefault(p.item_id, []).append(p)
    for item_id, rows in have.items():
        extra = sum((p.qty for p in rows), ZERO) - want[item_id][1]
        for p in reversed(rows):
            if extra <= 0:
                break
            if p.qty <= extra:
                extra -= p.qty
                p.delete()
            else:
                p.qty -= extra
                p.save(update_fields=["qty"])
                extra = ZERO
    fresh = {i for i, (_item, need) in want.items() if need > 0 and i not in have}
    if fresh:
        fill(mo, fresh)


def rows_out(mo: MO) -> dict[int, list[dict]]:
    """Each material's picks as the screen shows them."""
    out: dict[int, list[dict]] = {}
    for p in mo.picks.select_related("location__parent__parent", "batch", "package"):
        a = picking.area_of(p.location)
        out.setdefault(p.item_id, []).append(
            {
                "id": p.pk,
                "location": p.location_id,
                "location_name": p.location.name,
                "area": a.pk if a else None,
                "area_name": a.name if a else "",
                "batch": p.batch_id,
                "batch_number": p.batch.number if p.batch else "",
                "expiry": p.batch.expiry_date if p.batch else None,
                "package": p.package_id,
                "package_number": p.package.number if p.package else "",
                "qty": picking.plain(p.qty),
            }
        )
    return out


# Changing the picks -------------------------------------------------------------------


class RowSerializer(serializers.Serializer):
    location = serializers.IntegerField()
    batch = serializers.IntegerField(required=False, allow_null=True)
    package = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=18, decimal_places=6)  # in the stock unit


class PicksSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    rows = RowSerializer(many=True)


def _open(request, pk: int) -> MO:
    from manufacturing.orders import _check, _order

    _check(request, "create")
    mo = _order(request, pk, lock=True)
    if mo.status not in MO.OPEN:
        raise ValidationError({"detail": "Only a submitted order still open has picks to change."})
    return mo


def save_rows(mo: MO, item: Item, rows: list[dict]) -> None:
    """Replace one material's picks: each from a place in Materials From with
    that much free, and no more in all than is still to issue."""
    want = needs(mo).get(item.pk)
    if want is None:
        raise ValidationError({"item": [f"{item.name} is not a material of this order."]})
    where = {x.pk: x for x in places(mo.branch, mo.materials_from)}
    free = {s.key: s for s in spots(mo, item)}
    errors, made, asked = [], [], {}
    for n, row in enumerate(rows, start=1):
        place = where.get(row["location"])
        if place is None:
            errors.append(f"Row {n}: pick a bin of {mo.materials_from or mo.branch}.")
            continue
        batch = None
        if row.get("batch"):
            batch = Batch.objects.filter(pk=row["batch"], item=item).first()
            if batch is None or batch.status in picking.HELD:
                errors.append(f"Row {n}: pick a batch of {item.name} that may be used.")
                continue
        package = None
        if row.get("package"):
            package = Package.objects.filter(
                pk=row["package"], item=item, location=place, batch=batch
            ).first()
            if package is None:
                errors.append(f"Row {n}: pick a package in {place.name} of that batch.")
                continue
        if row["qty"] <= 0:
            errors.append(f"Row {n}: the quantity must be more than zero.")
            continue
        key = (place.pk, batch.pk if batch else None, package.pk if package else None)
        asked[key] = asked.get(key, ZERO) + row["qty"]
        spot = free.get(key)
        if spot is None or asked[key] > spot.free:
            label = place.name + (f", batch {batch.number}" if batch else "")
            label += f", package {package.number}" if package else ""
            have = spot.free if spot else ZERO
            errors.append(
                f"Row {n}: {label} has {picking.plain(have)} free, not {picking.plain(asked[key])}."
            )
            continue
        made.append(
            Pick(order=mo, item=item, location=place, batch=batch, package=package, qty=row["qty"])
        )
    total = sum((p.qty for p in made), ZERO)
    if total > want[1]:
        errors.append(
            f"{item.name}: picks {picking.plain(total)}, more than the "
            f"{picking.plain(want[1])} still to issue."
        )
    if errors:
        raise ValidationError({"rows": errors})
    mo.picks.filter(item=item).delete()
    Pick.objects.bulk_create(made)


class PicksView(APIView):
    """PATCH {item, rows: [{location, batch, package, qty}]}: one material's picks."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        from manufacturing.orders import _fresh

        mo = _open(request, pk)
        serializer = PicksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        item = Item.objects.filter(pk=data["item"]).first()
        if item is None:
            raise ValidationError({"item": ["Pick a material of this order."]})
        save_rows(mo, item, data["rows"])
        return Response(_fresh(mo))


class PickAgainView(APIView):
    """POST {item?}: propose the picks again by the rule (one material, or all)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        from manufacturing.orders import _fresh

        mo = _open(request, pk)
        item = request.data.get("item")
        fill(mo, {int(item)} if item else None)
        return Response(_fresh(mo))


class PlacesView(APIView):
    """GET ?item=ID: where that material may be picked from, with what is free
    (this order's own picks not kept aside)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from manufacturing.orders import _check, _order

        _check(request, "view")
        mo = _order(request, pk)
        item = Item.objects.filter(pk=request.query_params.get("item") or 0).first()
        if item is None or item.pk not in needs(mo):
            raise ValidationError({"item": ["Pick a material of this order."]})
        return Response(
            [
                {
                    "location": s.location.pk,
                    "location_name": s.location.name,
                    "area": a.pk if (a := picking.area_of(s.location)) else None,
                    "area_name": a.name if a else "",
                    "batch": s.batch.pk if s.batch else None,
                    "batch_number": s.batch.number if s.batch else "",
                    "expiry": s.expiry,
                    "package": s.package.pk if s.package else None,
                    "package_number": s.package.number if s.package else "",
                    "free": picking.plain(s.free),
                }
                for s in spots(mo, item)
            ]
        )


class PickPdfView(APIView):
    """GET (&download=1): the Material Pick List for the store, sorted by bin,
    with a tick box per row and "Picked By" / "Checked By"."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from core import printout
        from manufacturing.orders import _check, _fresh, _order

        _check(request, "view")
        mo = _order(request, pk)
        data = _fresh(mo)
        rows = []
        for ln in data["lines"]:
            for p in ln["picks"]:
                rows.append(
                    (
                        p["location_name"].lower(),
                        [
                            p["location_name"],
                            ln["item_name"],
                            p["batch_number"],
                            p["expiry"].strftime("%d-%m-%Y") if p["expiry"] else "",
                            p["package_number"],
                            f"{p['qty']} {ln['stock_unit_name']}",
                            "☐",
                        ],
                    )
                )
        rows.sort(key=lambda r: r[0])
        short = [
            [ln["item_name"], f"{ln['pick_short']} {ln['stock_unit_name']}"]
            for ln in data["lines"]
            if ln["pick_short"] != "0"
        ]
        sheets = [
            {
                "title": "Materials to Pick",
                "columns": ["Bin", "Material", "Batch", "Expiry", "Package", "Qty", "Picked"],
                "rows": [r[1] for r in rows] or [["Nothing picked yet", "", "", "", "", "", ""]],
            }
        ]
        if short:
            sheets.append(
                {"title": "Not in Stock Yet", "columns": ["Material", "Short"], "rows": short}
            )
        sheets.append(
            {
                "title": "Signatures",
                "columns": ["Picked By", "Checked By"],
                "rows": [["\n\n", "\n\n"]],
            }
        )
        scope = " · ".join(
            x
            for x in [
                data["branch_name"],
                data["materials_from_name"] and f"From {data['materials_from_name']}",
                f"For {data['item_name']}: {data['qty']} {data['unit_name']}",
                data["batch_no"] and f"Batch {data['batch_no']}",
            ]
            if x
        )
        title = f"Material Pick List {data['number']}"
        response = printout.pdf_response(title, scope, sheets, f"{data['number']}-pick")
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
