"""Items: the group's shared catalogue. Each item has a stock unit and a
chain of other units (packet -> inner box -> carton -> pallet) with size,
weight and barcode (spec 00, "Item units of measure").

Rules kept here:
- the stock unit always has a row, with factor 1;
- every other row says how many of another row's unit it contains, and its
  factor (stock units in one) is worked out from the chain, never typed;
- volume is worked out from the size; a missing size is a warning only;
- the sales and purchase names are blank when they are the item name;
- the default sales and purchase units must be among the item's units;
- GST rates are dated rows: one per "from" date, a new law means a new row
  (`gst_rate_on` gives the rate for a day).
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import duplicates
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import USED_FOR, Item, ItemGstRate, ItemUnit, Unit
from core.numbering import next_number
from tenancy.context import tenant_atomic

CM3_PER_M3 = Decimal(1_000_000)


def volume_m3(row) -> Decimal | None:
    sizes = (row.length_cm, row.breadth_cm, row.height_cm)
    if any(v is None for v in sizes):
        return None
    return (sizes[0] * sizes[1] * sizes[2] / CM3_PER_M3).quantize(Decimal("0.00001"))


class ItemUnitSerializer(serializers.ModelSerializer):
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
    contains_unit = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(), allow_null=True, required=False
    )
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    contains_unit_name = serializers.CharField(
        source="contains_unit.name", read_only=True, default=None
    )
    factor = serializers.DecimalField(max_digits=18, decimal_places=6, read_only=True)
    volume_m3 = serializers.SerializerMethodField()
    used_for = serializers.ListField(
        child=serializers.ChoiceField(choices=USED_FOR), required=False, default=list
    )

    class Meta:
        model = ItemUnit
        fields = [
            "unit",
            "unit_name",
            "contains_qty",
            "contains_unit",
            "contains_unit_name",
            "factor",
            "length_cm",
            "breadth_cm",
            "height_cm",
            "net_kg",
            "gross_kg",
            "volume_m3",
            "barcode",
            "whole_numbers",
            "used_for",
        ]

    def get_volume_m3(self, row):
        v = volume_m3(row)
        return None if v is None else format(v, "f")


class ItemGstRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemGstRate
        fields = ["valid_from", "rate"]


class ItemSerializer(serializers.ModelSerializer):
    stock_unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
    stock_unit_name = serializers.CharField(source="stock_unit.name", read_only=True)
    sales_unit = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(), allow_null=True, required=False
    )
    sales_unit_name = serializers.CharField(source="sales_unit.name", read_only=True, default=None)
    purchase_unit = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(), allow_null=True, required=False
    )
    purchase_unit_name = serializers.CharField(
        source="purchase_unit.name", read_only=True, default=None
    )
    units = ItemUnitSerializer(many=True, required=False)
    gst_rates = ItemGstRateSerializer(many=True, required=False)
    warnings = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            "id",
            "item_number",
            "name",
            "item_type",
            "stock_unit",
            "stock_unit_name",
            "hsn",
            "sales_name",
            "sales_description",
            "sales_unit",
            "sales_unit_name",
            "purchase_name",
            "purchase_description",
            "purchase_unit",
            "purchase_unit_name",
            "shelf_life_days",
            "batch_tracked",
            "qc_required",
            "notes",
            "is_active",
            "units",
            "gst_rates",
            "warnings",
        ]
        read_only_fields = ["item_number"]

    def get_warnings(self, item) -> list[str]:
        missing = [
            str(r.unit)
            for r in item.units.all()
            if any(v is None for v in (r.length_cm, r.breadth_cm, r.height_cm))
        ]
        return [f"Size missing for: {', '.join(missing)}."] if missing else []


def _resolve_chain(item_stock: Unit, rows: list[dict]) -> list[dict]:
    """Check the rows and give each its factor. Raises ValidationError."""
    by_unit: dict[int, dict] = {}
    for r in rows:
        if r["unit"].pk in by_unit:
            raise ValidationError({"units": [f"{r['unit'].name} is listed twice."]})
        by_unit[r["unit"].pk] = r
    if item_stock.pk not in by_unit:
        by_unit[item_stock.pk] = {"unit": item_stock}
        rows.insert(0, by_unit[item_stock.pk])
    stock_row = by_unit[item_stock.pk]
    if stock_row.get("contains_unit") or stock_row.get("contains_qty"):
        raise ValidationError(
            {"units": [f"{item_stock.name} is the stock unit; it contains nothing."]}
        )
    stock_row["factor"] = Decimal(1)
    stock_row["contains_qty"] = None
    stock_row["contains_unit"] = None
    for r in rows:
        if r is stock_row:
            continue
        qty, below = r.get("contains_qty"), r.get("contains_unit")
        if qty is None or below is None or qty <= 0:
            raise ValidationError(
                {"units": [f"Say how many of which unit one {r['unit'].name} contains."]}
            )
        if below.pk == r["unit"].pk or below.pk not in by_unit:
            raise ValidationError(
                {"units": [f"{r['unit'].name} must contain a unit that is also in the list."]}
            )
    for _ in range(len(rows)):
        for r in rows:
            if "factor" in r:
                continue
            below = by_unit[r["contains_unit"].pk]
            if "factor" in below:
                r["factor"] = r["contains_qty"] * below["factor"]
    stuck = [r["unit"].name for r in rows if "factor" not in r]
    if stuck:
        raise ValidationError(
            {"units": [f"The chain of units goes round in a circle ({', '.join(stuck)})."]}
        )
    for r in rows:
        r["factor"] = r["factor"].quantize(Decimal("0.000001"))
    return rows


def gst_rate_on(item: Item, day: date) -> Decimal | None:
    """The item's GST rate on a day: the row with the latest "from" date on
    or before it. None when no rate had started by then."""
    row = item.gst_rates.filter(valid_from__lte=day).order_by("-valid_from").first()
    return None if row is None else row.rate


def _check_rates(rates: list[dict]) -> list[dict]:
    seen = set()
    for r in rates:
        if r["valid_from"] in seen:
            raise ValidationError(
                {"gst_rates": [f"Two rates start on {r['valid_from']:%d-%m-%Y}; keep one."]}
            )
        seen.add(r["valid_from"])
    return sorted(rates, key=lambda r: r["valid_from"])


def _save_item(item: Item, data: dict) -> None:
    rows = data.pop("units", None)
    rates = data.pop("gst_rates", None)
    refuse_key_changes("item", item, data)
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            Item.objects.all(),
            data["name"],
            exclude=item.pk,
            kind="item",
            message='There is already an item named "{name}".',
        )
    for field in (
        "name",
        "item_type",
        "stock_unit",
        "hsn",
        "sales_name",
        "sales_description",
        "sales_unit",
        "purchase_name",
        "purchase_description",
        "purchase_unit",
        "shelf_life_days",
        "batch_tracked",
        "qc_required",
        "notes",
        "is_active",
    ):
        if field in data:
            setattr(item, field, data[field])
    if "hsn" in data and data["hsn"] and not data["hsn"].isdigit():
        raise ValidationError({"hsn": ["The HSN code is digits only."]})
    if rows is None and not item.pk:
        rows = []
    if rows is not None:
        rows = _resolve_chain(item.stock_unit, [dict(r) for r in rows])
        if item.pk:
            old = sorted((r.unit_id, r.contains_qty, r.contains_unit_id) for r in item.units.all())
            new = sorted(
                (r["unit"].pk, r.get("contains_qty"), getattr(r.get("contains_unit"), "pk", None))
                for r in rows
            )
            if old != new:
                refuse_key_changes("item", item, {"units": new})
        had = set(item.units.values_list("unit_id", flat=True)) if item.pk else set()
        for r in rows:
            if (
                not r["unit"].is_active
                and r["unit"].pk not in had
                and r["unit"].pk != item.stock_unit_id
            ):
                raise ValidationError({"units": [f"{r['unit'].name} is disabled."]})
    elif item.pk and item.units.exists():
        # The stock unit may have changed: its chain must still hold.
        existing = [
            {
                "unit": r.unit,
                "contains_qty": r.contains_qty,
                "contains_unit": r.contains_unit,
            }
            for r in item.units.all()
        ]
        _resolve_chain(item.stock_unit, existing)
    for field in ("sales_description", "purchase_description"):
        setattr(item, field, getattr(item, field).strip())
    for field in ("sales_name", "purchase_name"):
        value = " ".join(getattr(item, field).split())
        # the same as the item name is kept blank, so it follows a rename
        setattr(item, field, "" if value.lower() == item.name.lower() else value)
    if rows is not None:
        unit_ids = {r["unit"].pk for r in rows}
    elif item.pk:
        unit_ids = set(item.units.values_list("unit_id", flat=True)) | {item.stock_unit_id}
    else:
        unit_ids = {item.stock_unit_id}
    for field, label in (("sales_unit", "sales"), ("purchase_unit", "purchase")):
        chosen = getattr(item, field)
        if chosen is not None and chosen.pk not in unit_ids:
            raise ValidationError(
                {
                    field: [
                        f"The default {label} unit {chosen.name} is not one of the item's "
                        "units of measure. Add it there first."
                    ]
                }
            )
    if rates is not None:
        rates = _check_rates([dict(r) for r in rates])
    try:
        item.full_clean(validate_constraints=False, exclude=["item_number"])
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    if not item.item_number:
        item.item_number = next_number(
            "item", lambda n: Item.objects.filter(item_number=n).exists()
        )
    item.save()
    if rows is not None:
        for r in rows:
            barcode = (r.get("barcode") or "").strip()
            if barcode:
                clash = ItemUnit.objects.filter(barcode=barcode).exclude(item=item).first()
                if clash is not None:
                    duplicates.refuse(
                        "units",
                        f'The barcode {barcode} is already on the item "{clash.item.name}".',
                        clash.item,
                        "item",
                        name=clash.item.name,
                    )
        item.units.all().delete()
        for r in rows:
            row = ItemUnit(
                item=item,
                unit=r["unit"],
                contains_qty=r.get("contains_qty"),
                contains_unit=r.get("contains_unit"),
                factor=r["factor"],
                length_cm=r.get("length_cm"),
                breadth_cm=r.get("breadth_cm"),
                height_cm=r.get("height_cm"),
                net_kg=r.get("net_kg"),
                gross_kg=r.get("gross_kg"),
                barcode=(r.get("barcode") or "").strip(),
                whole_numbers=r.get("whole_numbers", True),
                used_for=r.get("used_for", []),
            )
            try:
                row.full_clean(validate_constraints=False)
            except DjangoValidationError as exc:
                raise ValidationError({"units": exc.messages}) from exc
            row.save()
    if rates is not None:
        old = [(r.valid_from, r.rate) for r in item.gst_rates.all()]
        new = [(r["valid_from"], r["rate"]) for r in rates]
        if old != new:
            item.gst_rates.all().delete()
            for r in rates:
                ItemGstRate.objects.create(item=item, valid_from=r["valid_from"], rate=r["rate"])
    if rows is not None or rates is not None:
        recorder.touch(item)


def _queryset():
    return Item.objects.select_related(
        "stock_unit", "sales_unit", "purchase_unit"
    ).prefetch_related("units__unit", "units__contains_unit", "gst_rates")


class ItemListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(ItemSerializer(_queryset().order_by("name"), many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = ItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = Item()
        _save_item(item, dict(serializer.validated_data))
        return Response(
            ItemSerializer(_queryset().get(pk=item.pk)).data, status=status.HTTP_201_CREATED
        )


class ItemDetailView(APIView):
    """Edit only: items are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        item = Item.objects.select_for_update().filter(pk=pk).first()
        if item is None:
            raise NotFound("No such item.")
        serializer = ItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_item(item, dict(serializer.validated_data))
        return Response(ItemSerializer(_queryset().get(pk=item.pk)).data)
