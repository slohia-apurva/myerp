"""Bills of materials (Masters > Production > BOM; Sidharth, 2026-11-22,
preview 14 in mockups/planning, approved with "Manufactured" and "Purchased"
for where a material comes from).

Rules:
- an item can have several versions, numbered 1, 2, 3 for that item;
- exactly one active version of an item is its Default (the star): planning
  and a new Manufacturing Order start from it, and an order may pick another
  active version;
- a material is "Manufactured" when it has a default BOM of its own (or is
  set to be made), "Customer's stock" when the item is Customer Provided
  (only a job work BOM may use those: counted, never valued), otherwise
  "Purchased";
- a job work BOM mixes the customer's goods with our own materials; ours are
  costed and their cost goes to the product, which is billed under its SAC
  code and despatched under its HSN code;
- no BOM may need, through its materials' default BOMs, the item it makes;
- once a Manufacturing Order uses a version its materials stop changing
  ("Duplicate as new version" instead).

The cost shown is an estimate: a material's rate is the value of its open
FIFO lots over their quantity, else the rate of its last receipt; a
manufactured material is costed from its own default BOM.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Max, Sum
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import lock_status, refuse_key_changes, uses
from core.models import Item, Party, Unit
from core.numbering import follow_numbers, next_number
from manufacturing.models import Bom, BomByproduct, BomLine
from posting.models import StockLot
from tenancy.context import tenant_atomic

ZERO = Decimal(0)
HUNDRED = Decimal(100)
MAX_DEPTH = 12

MANUFACTURED, PURCHASED, CUSTOMER = "manufactured", "purchased", "customer"
SOURCE_LABELS = {
    MANUFACTURED: "Manufactured",
    PURCHASED: "Purchased",
    CUSTOMER: "Customer's stock",
}


def money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _plain(value: Decimal) -> str:
    """A quantity without trailing zeros: 2.400000 -> 2.4."""
    text = format(Decimal(value).normalize(), "f")
    return text


# Serializers -----------------------------------------------------------------


class LineSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit_short = serializers.CharField(source="unit.short_name", read_only=True)

    class Meta:
        model = BomLine
        fields = ["item", "item_name", "qty", "unit", "unit_short", "loss_pct"]
        extra_kwargs = {"loss_pct": {"required": False}}


class ByproductSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit_short = serializers.CharField(source="unit.short_name", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = BomByproduct
        fields = ["item", "item_name", "qty", "unit", "unit_short", "kind", "kind_label", "rate"]
        extra_kwargs = {"rate": {"required": False}, "kind": {"required": False}}


class BomSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    makes_unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Party.objects.all(), allow_null=True, required=False
    )
    lines = LineSerializer(many=True, required=False)
    byproducts = ByproductSerializer(many=True, required=False)
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_number = serializers.CharField(source="item.item_number", read_only=True)
    makes_unit_short = serializers.CharField(source="makes_unit.short_name", read_only=True)
    customer_name = serializers.SerializerMethodField()
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    material_count = serializers.SerializerMethodField()
    lock = serializers.SerializerMethodField()

    class Meta:
        model = Bom
        fields = [
            "id", "number", "item", "item_name", "item_number", "version", "name",
            "is_default", "kind", "kind_label", "customer", "customer_name",
            "makes_qty", "makes_unit", "makes_unit_short", "valid_from", "notes", "packing_notes",
            "status", "status_label", "is_active", "lines", "byproducts",
            "material_count", "lock",
        ]  # fmt: skip
        read_only_fields = ["id", "version"]
        extra_kwargs = {
            "number": {"required": False, "allow_blank": True},
            "name": {"required": False, "allow_blank": True},
            "is_default": {"required": False},
            "status": {"required": False},
        }

    def get_customer_name(self, bom) -> str:
        return bom.customer.name if bom.customer_id else ""

    def get_material_count(self, bom) -> int:
        return len(bom.lines.all())

    def get_lock(self, bom) -> dict:
        return lock_status("bom", bom)


# Units and sources -------------------------------------------------------------


def _factors(item: Item) -> dict[int, Decimal]:
    """Stock units in one of each of the item's units, by unit id."""
    return {u.unit_id: u.factor for u in item.units.all()}


def factor(item: Item, unit_id: int) -> Decimal | None:
    return _factors(item).get(unit_id)


def default_bom(item_id: int) -> Bom | None:
    return (
        Bom.objects.filter(item_id=item_id, is_default=True)
        .select_related("item", "makes_unit")
        .first()
    )


def source(item: Item) -> tuple[str, Bom | None]:
    """Where a material comes from: made (with its default BOM, if it has one),
    the customer's own goods, or bought."""
    sub = default_bom(item.pk)
    if sub is not None:
        return MANUFACTURED, sub
    if item.default_request_type == Item.CUSTOMER_PROVIDED:
        return CUSTOMER, None
    if item.default_request_type == Item.MANUFACTURE:
        return MANUFACTURED, None
    return PURCHASED, None


def source_text(code: str, sub: Bom | None) -> str:
    if code == MANUFACTURED:
        if sub is None:
            return "Manufactured: no BOM yet"
        return f"Manufactured: {sub.number} v{sub.version} (default)"
    return SOURCE_LABELS[code]


def _reaches(start_id: int, target_id: int, seen: set[int]) -> bool:
    """Whether the default BOM of `start_id`, unfolded through its materials'
    default BOMs, needs `target_id`."""
    if start_id == target_id:
        return True
    if start_id in seen:
        return False
    seen.add(start_id)
    sub = default_bom(start_id)
    if sub is None:
        return False
    return any(_reaches(i, target_id, seen) for i in sub.lines.values_list("item_id", flat=True))


# Cost estimate ------------------------------------------------------------------


def stock_rate(item: Item) -> tuple[Decimal | None, str]:
    """Rate of one stock unit: open FIFO lots (all companies), else the last
    receipt; (None, "") when the item was never received."""
    open_lots = StockLot.objects.filter(item=item, qty_left__gt=0).aggregate(
        q=Sum("qty_left"), v=Sum("value_left")
    )
    if open_lots["q"]:
        return open_lots["v"] / open_lots["q"], "FIFO"
    last = StockLot.objects.filter(item=item).order_by("-date", "-id").first()
    if last is not None:
        return last.rate, "last receipt"
    return None, ""


def rate_of(item: Item, unit_id: int, depth: int = 0):
    """The estimated rate of one `unit_id` of a material: (source, its default
    BOM, rate or None, where the rate came from, names of what has no rate)."""
    code, sub = source(item)
    if code == CUSTOMER:
        return code, sub, ZERO, "not valued", []
    mine = factor(item, unit_id)
    if sub is not None and depth < MAX_DEPTH:
        inner = costing(sub, depth + 1)
        per = factor(sub.item, sub.makes_unit_id)
        if inner["complete"] and per and mine:
            return code, sub, inner["net"] / (sub.makes_qty * per) * mine, f"from {sub.number}", []
        return code, sub, None, "", inner["missing"] or [item.name]
    base, how = stock_rate(item)
    if base is not None and mine:
        return code, sub, base * mine, how, []
    return code, sub, None, "", [item.name]


def costing(bom: Bom, depth: int = 0) -> dict:
    """The estimated cost of one batch (makes_qty in makes_unit): each line with
    its quantity to issue (loss added), rate and cost, and the totals."""
    rows = []
    missing: list[str] = []
    materials = ZERO
    for ln in bom.lines.all():
        need = ln.qty * (1 + ln.loss_pct / HUNDRED)
        code, sub, rate, how, lacking = rate_of(ln.item, ln.unit_id, depth)
        missing.extend(x for x in lacking if x not in missing)
        if rate is None:
            if ln.item.name not in missing:
                missing.append(ln.item.name)
            cost = None
        else:
            cost = money(need * rate)
            materials += cost
        rows.append(
            {
                "line": ln,
                "need": need,
                "code": code,
                "sub": sub,
                "rate": rate,
                "how": how,
                "cost": cost,
            }
        )
    by_value = sum((money(b.qty * b.rate) for b in bom.byproducts.all()), ZERO)
    return {
        "rows": rows,
        "materials": materials,
        "byproducts": by_value,
        "net": materials - by_value,
        "missing": missing,
        "complete": not missing,
    }


def per_stock_unit(bom: Bom, net: Decimal) -> Decimal | None:
    per = factor(bom.item, bom.makes_unit_id)
    if not per or not bom.makes_qty:
        return None
    return money(net / (bom.makes_qty * per))


def _children(sub: Bom, need_stock: Decimal, depth: int) -> list[dict]:
    """The materials of a sub-BOM for `need_stock` stock units of its item,
    unfolded to the bottom (shown folded on the screen)."""
    per = factor(sub.item, sub.makes_unit_id)
    if not per or depth >= MAX_DEPTH:
        return []
    scale = need_stock / (sub.makes_qty * per)
    out = []
    for ln in sub.lines.all():
        code, inner = source(ln.item)
        qty = ln.qty * scale
        row = {
            "item": ln.item_id,
            "item_name": ln.item.name,
            "qty": _plain(qty.quantize(Decimal("0.000001"))),
            "unit_short": ln.unit.short_name,
            "loss_pct": _plain(ln.loss_pct),
            "source": code,
            "source_text": source_text(code, inner),
            "sub_bom": inner.pk if inner else None,
            "children": [],
        }
        mine = factor(ln.item, ln.unit_id)
        if inner is not None and mine:
            need = qty * (1 + ln.loss_pct / HUNDRED) * mine
            row["children"] = _children(inner, need, depth + 1)
        out.append(row)
    return out


def detail(bom: Bom) -> dict:
    """Everything the BOM's own page shows."""
    data = BomSerializer(bom).data
    cost = costing(bom)
    materials = []
    for r in cost["rows"]:
        ln, sub = r["line"], r["sub"]
        row = {
            "item": ln.item_id,
            "item_name": ln.item.name,
            "qty": _plain(ln.qty),
            "unit": ln.unit_id,
            "unit_short": ln.unit.short_name,
            "loss_pct": _plain(ln.loss_pct),
            "issue_qty": _plain(r["need"].quantize(Decimal("0.000001"))),
            "source": r["code"],
            "source_text": source_text(r["code"], sub),
            "sub_bom": sub.pk if sub else None,
            "rate": str(money(r["rate"])) if r["rate"] is not None else None,
            "rate_from": r["how"],
            "cost": str(r["cost"]) if r["cost"] is not None else None,
            "children": [],
        }
        mine = factor(ln.item, ln.unit_id)
        if sub is not None and mine:
            row["children"] = _children(sub, r["need"] * mine, 1)
        materials.append(row)
    data["materials"] = materials
    data["byproduct_rows"] = [
        {**b, "value": str(money(Decimal(b["qty"]) * Decimal(b["rate"] or 0)))}
        for b in data["byproducts"]
    ]
    stock_short = bom.item.stock_unit.short_name
    versions = []
    for v in (
        Bom.objects.filter(item=bom.item).select_related("item", "makes_unit").order_by("version")
    ):
        vc = costing(v) if v.pk != bom.pk else cost
        versions.append(
            {
                "id": v.pk,
                "number": v.number,
                "version": v.version,
                "name": v.name,
                "valid_from": v.valid_from,
                "is_default": v.is_default,
                "status": v.status,
                "status_label": v.get_status_display(),
                "is_active": v.is_active,
                "per_unit": str(per_stock_unit(v, vc["net"])) if vc["complete"] else None,
            }
        )
    data["versions"] = versions
    data["cost"] = {
        "materials": str(cost["materials"]),
        "byproducts": str(cost["byproducts"]),
        "net": str(cost["net"]),
        "per_unit": (str(per_stock_unit(bom, cost["net"])) if cost["complete"] else None),
        "stock_unit": stock_short,
        "missing": cost["missing"],
    }
    data["job"] = job_codes(bom)
    data["used_by"] = uses("bom", bom)
    return data


def job_codes(bom: Bom) -> dict | None:
    """For job work: the SAC code the work is billed under (invoice, e-invoice)
    and the HSN code the goods go under (delivery challan, e-way bill)."""
    if bom.kind != Bom.JOB_WORK:
        return None
    item = bom.item
    if item.item_type == Item.SERVICE and item.delivery_hsn:
        return {"sac": item.hsn, "hsn": item.delivery_hsn, "note": ""}
    return {
        "sac": item.hsn if item.item_type == Item.SERVICE else "",
        "hsn": item.delivery_hsn or (item.hsn if item.item_type == Item.GOODS else ""),
        "note": (
            f"Job work is billed under a SAC code and despatched under an HSN code. "
            f"{item.name} is not set up that way: make it a Service that keeps stock, "
            "with its SAC code and its Delivery HSN (Masters › Items)."
        ),
    }


# Saving --------------------------------------------------------------------------


def _line_key(rows) -> list[tuple]:
    return [
        (r["item"].pk, Decimal(r["qty"]), r["unit"].pk, Decimal(r.get("loss_pct") or 0))
        for r in rows
    ]


def _saved_key(bom: Bom) -> list[tuple]:
    return [(ln.item_id, ln.qty, ln.unit_id, ln.loss_pct) for ln in bom.lines.all()]


def _check_lines(bom: Bom, kind: str, rows: list[dict], byproducts: list[dict]) -> None:
    problems: list[str] = []
    seen: set[int] = set()
    for n, r in enumerate(rows, 1):
        item, unit = r["item"], r["unit"]
        where = f"Material {n} ({item.name})"
        if item.pk == bom.item_id:
            problems.append(f"{where}: a BOM cannot use the item it makes.")
            continue
        if item.pk in seen:
            problems.append(f"{where} is listed twice; put the whole quantity on one line.")
        seen.add(item.pk)
        if r["qty"] <= 0:
            problems.append(f"{where}: the quantity must be more than 0.")
        loss = r.get("loss_pct") or ZERO
        if loss < 0 or loss >= HUNDRED:
            problems.append(f"{where}: Loss % must be from 0 to less than 100.")
        if factor(item, unit.pk) is None:
            problems.append(f"{where} is not kept in {unit.short_name}; pick one of its units.")
        if item.default_request_type == Item.CUSTOMER_PROVIDED and kind != Bom.JOB_WORK:
            problems.append(f"{where} is a customer's own goods: only a job work BOM may use it.")
        if _reaches(item.pk, bom.item_id, set()):
            problems.append(
                f"{where} is itself made from {bom.item.name} (through its default BOM), "
                "so this would go round in a circle."
            )
    for n, r in enumerate(byproducts, 1):
        item, unit = r["item"], r["unit"]
        where = f"By-product {n} ({item.name})"
        if r["qty"] <= 0:
            problems.append(f"{where}: the quantity must be more than 0.")
        if (r.get("rate") or ZERO) < 0:
            problems.append(f"{where}: the value cannot be below 0.")
        if factor(item, unit.pk) is None:
            problems.append(f"{where} is not kept in {unit.short_name}; pick one of its units.")
    if problems:
        raise ValidationError({"lines": problems})


def _set_default(bom: Bom) -> None:
    """Move the item's star to this version (the old default is saved, so the
    audit log shows the change on both)."""
    for old in (
        Bom.objects.select_for_update().filter(item=bom.item, is_default=True).exclude(pk=bom.pk)
    ):
        old.is_default = False
        old.save(update_fields=["is_default"])
    bom.is_default = True


def save_bom(bom: Bom, data: dict, user=None) -> Bom:
    lines = data.pop("lines", None)
    byproducts = data.pop("byproducts", None)
    new = bom.pk is None
    item = data.get("item", bom.item if not new else None)
    if item is None:
        raise ValidationError({"item": ["Pick the item this BOM makes."]})
    if not new and item.pk != bom.item_id:
        raise ValidationError(
            {"item": ["A BOM's item does not change. Make a new BOM for the other item."]}
        )
    if not item.maintain_stock:
        raise ValidationError(
            {"item": [f"{item.name} keeps no stock, so it cannot be made from a BOM."]}
        )
    refuse_key_changes("bom", bom, data)
    bom.item = item
    if new:
        top = Bom.objects.filter(item=item).aggregate(m=Max("version"))["m"] or 0
        bom.version = top + 1
    for field in (
        "kind", "customer", "makes_qty", "makes_unit", "valid_from", "notes", "packing_notes",
        "status", "is_active",
    ):  # fmt: skip
        if field in data:
            setattr(bom, field, data[field])
    if bom.kind != Bom.JOB_WORK:
        bom.customer = None
    if bom.customer is not None and not bom.customer.customer_number:
        raise ValidationError({"customer": [f"{bom.customer.name} is not a customer."]})
    name = duplicates.tidy(data.get("name", bom.name)) or f"Version {bom.version}"
    duplicates.check_name(
        Bom.objects.filter(item=item),
        name,
        exclude=bom.pk,
        kind="bom",
        message=f'{item.name} already has a version named "{{name}}".',
    )
    bom.name = name
    number = (data.get("number") or "").strip().upper()
    if number:
        clash = Bom.objects.filter(number__iexact=number).exclude(pk=bom.pk).first()
        if clash is not None:
            duplicates.refuse(
                "number", f"{clash.number} is already used by another BOM.", clash, "bom"
            )
        bom.number = number
    if bom.makes_qty is None or bom.makes_qty <= 0:
        raise ValidationError({"makes_qty": ["How much one batch makes must be more than 0."]})
    if factor(item, bom.makes_unit_id) is None:
        raise ValidationError(
            {
                "makes_unit": [
                    f"{item.name} is not kept in {bom.makes_unit.short_name}; "
                    "pick one of its units."
                ]
            }
        )
    if lines is not None:
        if not new and _line_key(lines) != _saved_key(bom) and (why := uses("bom", bom)):
            raise ValidationError(
                {
                    "lines": [
                        f"This version is in use ({', '.join(why)}), so its materials cannot "
                        'change. Use "Duplicate as new version".'
                    ]
                }
            )
        _check_lines(bom, bom.kind, lines, byproducts or [])
    elif byproducts is not None:
        _check_lines(bom, bom.kind, [], byproducts)
    has_lines = bool(lines) if lines is not None else (not new and bom.lines.exists())
    if bom.status == Bom.ACTIVE and not has_lines:
        raise ValidationError({"lines": ["Add at least one material (or save it as a Draft)."]})
    usable = bom.status == Bom.ACTIVE and bom.is_active
    wants_default = data.get("is_default", bom.is_default)
    current = Bom.objects.filter(item=item, is_default=True).exclude(pk=bom.pk).first()
    if not usable and bom.is_default and not new:
        others = Bom.objects.filter(item=item, status=Bom.ACTIVE, is_active=True).exclude(pk=bom.pk)
        if others.exists():
            raise ValidationError(
                {
                    "is_default": [
                        "This is the default version. Make another version the default "
                        "first, then disable it or turn it back into a Draft."
                    ]
                }
            )
        bom.is_default = False  # the last usable version: the item is left without one
    if wants_default and not usable:
        raise ValidationError(
            {"is_default": ["Only an active version that is not disabled can be the default."]}
        )
    try:
        bom.full_clean(validate_constraints=False, exclude=["number", "version"])
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    if not bom.number:
        bom.number = next_number("bom", lambda n: Bom.objects.filter(number=n).exists())
    if new and user is not None and getattr(user, "pk", None):
        bom.created_by = user
    if usable and (wants_default or current is None):
        _set_default(bom)  # the first usable version takes the star by itself
    bom.save()
    if lines is not None:
        bom.lines.all().delete()
        BomLine.objects.bulk_create(
            [
                BomLine(
                    bom=bom,
                    position=n,
                    item=r["item"],
                    qty=r["qty"],
                    unit=r["unit"],
                    loss_pct=r.get("loss_pct") or ZERO,
                )
                for n, r in enumerate(lines, 1)
            ]
        )
    if byproducts is not None:
        bom.byproducts.all().delete()
        BomByproduct.objects.bulk_create(
            [
                BomByproduct(
                    bom=bom,
                    position=n,
                    item=r["item"],
                    qty=r["qty"],
                    unit=r["unit"],
                    kind=r.get("kind") or BomByproduct.SCRAP,
                    rate=r.get("rate") or ZERO,
                )
                for n, r in enumerate(byproducts, 1)
            ]
        )
    if lines is not None or byproducts is not None:
        recorder.touch(bom)
    return bom


def make_default(bom: Bom) -> Bom:
    if bom.status != Bom.ACTIVE or not bom.is_active:
        raise ValidationError(
            {"is_default": ["Only an active version that is not disabled can be the default."]}
        )
    for ln in bom.lines.select_related("item"):
        if _reaches(ln.item_id, bom.item_id, set()):
            raise ValidationError(
                {
                    "is_default": [
                        f"{ln.item.name} is itself made from {bom.item.name}, so this "
                        "version cannot be the default (it would go round in a circle)."
                    ]
                }
            )
    _set_default(bom)
    bom.save(update_fields=["is_default"])
    return bom


# Import, export and print ------------------------------------------------------------


def _queryset(ctx=None):
    return Bom.objects.select_related("item", "makes_unit", "customer").prefetch_related(
        "lines__item", "lines__unit", "byproducts__item", "byproducts__unit"
    )


exchange.register(
    exchange.Master(
        key="boms",
        label="BOMs",
        noun="BOM",
        serializer=BomSerializer,
        queryset=lambda ctx: _queryset().order_by("item__name", "version"),
        save=lambda ctx, bom, data: save_bom(bom or Bom(), data, ctx.request.user),
        link="number",
        exclude=(
            "item_name",
            "item_number",
            "makes_unit_short",
            "customer_name",
            "kind_label",
            "status_label",
            "material_count",
            "lock",
            "lines.item_name",
            "lines.unit_short",
            "byproducts.item_name",
            "byproducts.unit_short",
            "byproducts.kind_label",
        ),  # fmt: skip
        show=("version",),
        labels={
            "number": "BOM No",
            "makes_qty": "Makes Qty",
            "makes_unit": "Makes Unit",
            "is_default": "Default",
            "is_active": "Active",
            "packing_notes": "Packing Notes",
            "lines": "Materials",
            "lines.item": "Item",
            "lines.qty": "Qty",
            "lines.unit": "Unit",
            "lines.loss_pct": "Loss %",
            "byproducts": "By-products",
            "byproducts.item": "Item",
            "byproducts.qty": "Qty",
            "byproducts.unit": "Unit",
            "byproducts.kind": "Kind",
            "byproducts.rate": "Value per Unit",
        },
        hints={
            "number": "Leave empty for the next number (BOM-00001); materials name it",
            "name": "Leave empty for Version 1, 2, …",
            "lines.qty": "For the quantity the BOM makes",
        },
        report=(
            "number",
            "item",
            "version",
            "name",
            "is_default",
            "makes_qty",
            "makes_unit",
            "status",
        ),
        after=lambda ctx: follow_numbers("bom", Bom.objects.values_list("number", flat=True)),
    )
)


# Views -----------------------------------------------------------------------------


def _bom(pk: int, lock: bool = False) -> Bom:
    rows = _queryset()
    if lock:
        rows = rows.select_for_update(of=("self",))
    bom = rows.filter(pk=pk).first()
    if bom is None:
        raise NotFound("No such BOM.")
    return bom


class BomListView(APIView):
    """GET every BOM (?item=ID for one item's versions). POST a new one."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        rows = _queryset().order_by("item__name", "version")
        item = request.query_params.get("item")
        if item:
            rows = rows.filter(item_id=item)
        return Response(BomSerializer(rows, many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = BomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bom = save_bom(Bom(), dict(serializer.validated_data), request.user)
        return Response(detail(_bom(bom.pk)), status=status.HTTP_201_CREATED)


class BomDetailView(APIView):
    """GET one BOM with its materials unfolded, cost and versions. PATCH it.
    BOMs are never deleted, only disabled."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(detail(_bom(pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        bom = _bom(pk, lock=True)
        serializer = BomSerializer(bom, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        save_bom(bom, dict(serializer.validated_data), request.user)
        return Response(detail(_bom(pk)))


class BomMakeDefaultView(APIView):
    """POST: this version becomes the item's default (the star moves)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        make_default(_bom(pk, lock=True))
        return Response(detail(_bom(pk)))
