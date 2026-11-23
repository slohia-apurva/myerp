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
  (`gst_rate_on` gives the rate for a day);
- Stock Planning (Sidharth, 2026-11-21): one line per branch with how that
  branch fills a shortage (buy, make, transfer from another branch of the
  same company, or the customer's goods), its safety stock and the level a
  refill brings it up to; the "Preferred Supplier" is one of the suppliers.
"""

import re
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import duplicates, erpnext, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.gst_rates import refuse_unlisted_rates
from core.locks import lock_status, refuse_key_changes, refuse_move_outside_top
from core.models import (
    USED_FOR,
    Branch,
    Brand,
    Item,
    ItemGroup,
    ItemGstRate,
    ItemPlan,
    ItemUnit,
    Party,
    PartyItemName,
    Unit,
)
from core.numbering import follow_numbers, next_number
from core.tds_sections import check_section
from tenancy.context import tenant_atomic
from tenancy.models import HsnCode

DESCRIPTION_MAX = 5000

CM3_PER_M3 = Decimal(1_000_000)


def volume_m3(row) -> Decimal | None:
    sizes = (row.length_cm, row.breadth_cm, row.height_cm)
    if any(v is None for v in sizes):
        return None
    return (sizes[0] * sizes[1] * sizes[2] / CM3_PER_M3).quantize(Decimal("0.00001"))


class PartyItemNameSerializer(serializers.ModelSerializer):
    """What one customer or supplier calls the item (name and/or code)."""

    party = serializers.PrimaryKeyRelatedField(queryset=Party.objects.all())
    party_name = serializers.CharField(source="party.name", read_only=True)
    party_kind = serializers.SerializerMethodField()
    name = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")
    code = serializers.CharField(max_length=40, allow_blank=True, required=False, default="")

    def get_party_kind(self, row) -> str:
        kinds = []
        if row.party.customer_number:
            kinds.append("Customer")
        if row.party.vendor_number:
            kinds.append("Supplier")
        return ", ".join(kinds)

    class Meta:
        model = PartyItemName
        fields = ["party", "party_name", "party_kind", "name", "code"]


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


class ItemPlanSerializer(serializers.ModelSerializer):
    """Stock planning at one branch: fulfilment, safety stock and refill level."""

    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    company_name = serializers.CharField(source="branch.company.name", read_only=True)
    transfer_from = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), allow_null=True, required=False
    )
    transfer_from_name = serializers.CharField(
        source="transfer_from.name", read_only=True, default=None
    )
    safety_qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=0)
    order_up_to = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=0, allow_null=True, required=False
    )
    transfer_days = serializers.IntegerField(min_value=0, allow_null=True, required=False)

    class Meta:
        model = ItemPlan
        fields = [
            "branch",
            "branch_name",
            "company_name",
            "fulfilment",
            "transfer_from",
            "transfer_from_name",
            "transfer_days",
            "safety_qty",
            "order_up_to",
        ]


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
    item_group = serializers.PrimaryKeyRelatedField(
        queryset=ItemGroup.objects.all(), allow_null=True, required=False
    )
    item_group_name = serializers.CharField(source="item_group.name", read_only=True, default=None)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(), allow_null=True, required=False
    )
    brand_name = serializers.CharField(source="brand.name", read_only=True, default=None)
    mrp = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    usp = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    usp_per = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(), allow_null=True, required=False
    )
    min_order_qty = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=0, allow_null=True, required=False
    )
    preferred_supplier = serializers.PrimaryKeyRelatedField(
        queryset=Party.objects.all(), allow_null=True, required=False
    )
    preferred_supplier_name = serializers.CharField(
        source="preferred_supplier.name", read_only=True, default=None
    )
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Party.objects.all(), allow_null=True, required=False
    )
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    plans = ItemPlanSerializer(many=True, required=False)
    units = ItemUnitSerializer(many=True, required=False)
    gst_rates = ItemGstRateSerializer(many=True, required=False)
    party_names = PartyItemNameSerializer(many=True, required=False)
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
            "delivery_hsn",
            "item_group",
            "item_group_name",
            "brand",
            "brand_name",
            "sales_description",
            "sales_unit",
            "sales_unit_name",
            "purchase_description",
            "purchase_unit",
            "purchase_unit_name",
            "mrp",
            "usp",
            "usp_per",
            "best_before_value",
            "best_before_unit",
            "batch_no",
            "lead_time_days",
            "min_order_qty",
            "preferred_supplier",
            "preferred_supplier_name",
            "customer",
            "customer_name",
            "batch_tracked",
            "qc_required",
            "default_request_type",
            "maintain_stock",
            "allow_purchase",
            "allow_sales",
            "purchase_charge",
            "sales_charge",
            "add_to_stock",
            "offer_to_all",
            "tds_section",
            "notes",
            "is_active",
            "units",
            "gst_rates",
            "party_names",
            "plans",
            "warnings",
            "lock",
        ]
        read_only_fields = ["item_number"]

    lock = serializers.SerializerMethodField()

    def get_lock(self, item) -> dict:
        return lock_status("item", item)

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


ITEM_NUMBER = re.compile(r"[A-Za-z0-9/._-]+")


def _take_number(item: Item, number: str | None) -> None:
    """An item number given in an import file (an ERPNext item code, say):
    used as it is. Empty leaves the item's number, or gives a new item the next
    one of the series."""
    number = (number or "").strip()
    if not number or number == item.item_number:
        return
    if not ITEM_NUMBER.fullmatch(number):
        raise ValidationError(
            {"item_number": ["Use only letters, digits and - / . _ in an item number."]}
        )
    clash = Item.objects.filter(item_number__iexact=number).exclude(pk=item.pk).first()
    if clash is not None:
        duplicates.refuse(
            "item_number",
            f'The item number {clash.item_number} is already on the item "{clash.name}".',
            clash,
            "item",
            name=clash.name,
        )
    item.item_number = number


def _save_item(item: Item, data: dict) -> Item:
    _take_number(item, data.pop("item_number", None))
    rows = data.pop("units", None)
    rates = data.pop("gst_rates", None)
    party_names = data.pop("party_names", None)
    plans = data.pop("plans", None)
    refuse_key_changes("item", item, data)
    if "item_group" in data:
        refuse_move_outside_top(
            "item", item, "item_group", item.item_group, data["item_group"], "item"
        )
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            Item.objects.all(),
            data["name"],
            exclude=item.pk,
            kind="item",
            message='There is already an item named "{name}".',
        )
    if "preferred_supplier" in data:
        _check_supplier(item, data["preferred_supplier"], item.preferred_supplier_id)
    brand = data.get("brand")
    if brand is not None and not brand.is_active and brand.pk != item.brand_id:
        raise ValidationError({"brand": [f"{brand.name} is disabled."]})
    group = data.get("item_group")
    if group is not None and not group.is_active and group.pk != item.item_group_id:
        raise ValidationError({"item_group": [f"{group.name} is disabled."]})
    if group is not None and group.pk != item.item_group_id and group.children.exists():
        raise ValidationError(
            {"item_group": [f"{group.name} has sub-groups. Pick one of its sub-groups."]}
        )
    for field in (
        "name",
        "item_type",
        "stock_unit",
        "hsn",
        "delivery_hsn",
        "sales_description",
        "sales_unit",
        "purchase_description",
        "purchase_unit",
        "item_group",
        "brand",
        "mrp",
        "usp",
        "usp_per",
        "best_before_value",
        "best_before_unit",
        "batch_no",
        "lead_time_days",
        "min_order_qty",
        "preferred_supplier",
        "customer",
        "batch_tracked",
        "qc_required",
        "default_request_type",
        "maintain_stock",
        "allow_purchase",
        "allow_sales",
        "purchase_charge",
        "sales_charge",
        "add_to_stock",
        "offer_to_all",
        "tds_section",
        "notes",
        "is_active",
    ):
        if field in data:
            setattr(item, field, data[field])
    item.tds_section = check_section(item.tds_section)
    if item.purchase_charge and item.item_type != Item.SERVICE:
        raise ValidationError(
            {"purchase_charge": ["Only a service item can be a purchase charge."]}
        )
    if item.sales_charge and item.item_type != Item.SERVICE:
        raise ValidationError({"sales_charge": ["Only a service item can be a sales charge."]})
    if "hsn" in data and data["hsn"] and not data["hsn"].isdigit():
        raise ValidationError({"hsn": ["The HSN code is digits only."]})
    if not item.hsn:
        raise ValidationError({"hsn": ["Give the HSN code."]})
    if item.item_group_id is None:
        raise ValidationError({"item_group": ["Pick the item group."]})
    if item.brand_id is None:
        raise ValidationError({"brand": ["Pick the brand."]})
    if (not item.pk or item.hsn != _saved_hsn(item)) and not HsnCode.objects.filter(
        hsn_code=item.hsn, is_active=True
    ).exists():
        raise ValidationError(
            {"hsn": ["That HSN code is not in the list. Pick one from the list."]}
        )
    # A service that keeps stock (job work) also has the goods code for the delivery
    # challan and e-way bill; for every other item the field is cleared.
    if item.item_type == Item.SERVICE and item.maintain_stock:
        if "delivery_hsn" in data and data["delivery_hsn"] and not data["delivery_hsn"].isdigit():
            raise ValidationError({"delivery_hsn": ["The delivery HSN code is digits only."]})
        if not item.delivery_hsn:
            raise ValidationError(
                {"delivery_hsn": ["Give the delivery HSN code (the goods code for the challan)."]}
            )
        if (not item.pk or item.delivery_hsn != _saved_hsn(item, "delivery_hsn")) and not (
            HsnCode.objects.filter(hsn_code=item.delivery_hsn, is_active=True).exists()
        ):
            raise ValidationError(
                {"delivery_hsn": ["That HSN code is not in the list. Pick one from the list."]}
            )
    else:
        item.delivery_hsn = ""
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
    # Plain text (Sidharth, 2026-11-15): no formatting; prints smaller under the item name.
    for field in ("sales_description", "purchase_description"):
        lines = [line.rstrip() for line in (getattr(item, field) or "").splitlines()]
        text = "\n".join(lines).strip()
        if len(text) > DESCRIPTION_MAX:
            raise ValidationError({field: ["That description is too long; shorten it."]})
        setattr(item, field, text)
    if item.usp is None:
        item.usp_per = None
    item.batch_no = item.batch_no.strip()
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
        kept = {(r.valid_from, r.rate) for r in item.gst_rates.all()} if item.pk else set()
        refuse_unlisted_rates(rates, kept)
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
    if party_names is not None:
        _save_party_names(item, party_names)
    if plans is not None:
        _save_plans(item, plans)
    elif not item.maintain_stock and item.plans.exists():
        raise ValidationError(
            {"plans": ["An item without stock has no stock planning. Remove its branch lines."]}
        )
    if item.default_request_type != Item.CUSTOMER_PROVIDED:
        item.customer = None
        Item.objects.filter(pk=item.pk).update(customer=None)
    elif item.customer_id is None:
        raise ValidationError({"customer": ["Pick the customer whose goods this item is."]})
    elif not item.customer.customer_number:
        raise ValidationError(
            {"customer": [f"{item.customer.name} is not a customer. Pick a customer."]}
        )
    if not item.default_request_type and item.plans.exists():
        raise ValidationError(
            {"default_request_type": ["Pick the Main Fulfilment: the item has branch lines."]}
        )
    if any(x is not None for x in (rows, rates, party_names, plans)):
        recorder.touch(item)
    return item


def _check_supplier(item: Item, supplier: Party | None, saved_id: int | None) -> None:
    """The preferred supplier must be a supplier (have a vendor number)."""
    if supplier is None or supplier.pk == saved_id:
        return
    if not supplier.vendor_number:
        raise ValidationError(
            {"preferred_supplier": [f"{supplier.name} is not a supplier. Pick a supplier."]}
        )


def _save_plans(item: Item, rows: list[dict]) -> None:
    """Replace the item's Stock Planning lines. One line per branch; the branch
    keeps stock; a transfer comes from another stock branch of the same company,
    and transfers never go round in a circle; the refill level is not below the
    safety stock."""
    if rows and not item.maintain_stock:
        raise ValidationError(
            {"plans": ["An item without stock has no stock planning. Remove its branch lines."]}
        )
    kept = set(item.plans.values_list("branch_id", flat=True)) if item.pk else set()
    seen: dict[int, dict] = {}
    for r in rows:
        branch = r["branch"]
        if branch.pk in seen:
            raise ValidationError({"plans": [f"{branch.name} is listed twice."]})
        seen[branch.pk] = r
        if branch.no_stock:
            raise ValidationError({"plans": [f"{branch.name} keeps no stock."]})
        if not branch.is_active and branch.pk not in kept:
            raise ValidationError({"plans": [f"{branch.name} is disabled."]})
        source = r.get("transfer_from")
        if r["fulfilment"] == ItemPlan.TRANSFER:
            if source is None:
                raise ValidationError(
                    {"plans": [f"{branch.name}: pick the branch it transfers from."]}
                )
            if source.pk == branch.pk:
                raise ValidationError({"plans": [f"{branch.name} cannot transfer from itself."]})
            if source.company_id != branch.company_id:
                raise ValidationError(
                    {
                        "plans": [
                            f"{branch.name}: transfers come from a branch of the same "
                            f"company; {source.name} is not."
                        ]
                    }
                )
            if source.no_stock:
                raise ValidationError({"plans": [f"{source.name} keeps no stock."]})
        else:
            r["transfer_from"] = None
            r["transfer_days"] = None
        up_to = r.get("order_up_to")
        if up_to is not None and up_to < r["safety_qty"]:
            raise ValidationError(
                {"plans": [f"{branch.name}: Order Up To cannot be below the safety stock."]}
            )
    for start in seen:
        path, at = [start], seen[start]
        while at.get("transfer_from") is not None:
            nxt = at["transfer_from"].pk
            if nxt in path:
                names = ", ".join(seen[b]["branch"].name for b in path)
                raise ValidationError({"plans": [f"Transfers go round in a circle ({names})."]})
            path.append(nxt)
            at = seen.get(nxt, {})
    item.plans.all().delete()
    ItemPlan.objects.bulk_create(
        [
            ItemPlan(
                item=item,
                branch=r["branch"],
                fulfilment=r["fulfilment"],
                transfer_from=r.get("transfer_from"),
                transfer_days=r.get("transfer_days"),
                safety_qty=r["safety_qty"],
                order_up_to=r.get("order_up_to"),
            )
            for r in rows
        ]
    )


def _save_party_names(item: Item, rows: list[dict]) -> None:
    """Replace the item's list of what each customer or supplier calls it. A party
    appears once, a row needs a name or a code, and a party's code belongs to one
    item only (so a scanned code always finds one item)."""
    seen: set[int] = set()
    clean = []
    for r in rows:
        party, name, code = r["party"], r.get("name", "").strip(), r.get("code", "").strip()
        if party.pk in seen:
            raise ValidationError({"party_names": [f"{party.name} is listed twice."]})
        seen.add(party.pk)
        if not name and not code:
            raise ValidationError(
                {"party_names": [f"{party.name}: give their item name, their item code, or both."]}
            )
        if code:
            clash = (
                PartyItemName.objects.filter(party=party, code__iexact=code)
                .exclude(item=item)
                .select_related("item")
                .first()
            )
            if clash:
                raise ValidationError(
                    {
                        "party_names": [
                            f"The code {code} of {party.name} is already on the item "
                            f'"{clash.item.name}".'
                        ]
                    }
                )
            if any(c[0].pk == party.pk and c[2].lower() == code.lower() for c in clean):
                raise ValidationError(
                    {"party_names": [f"{party.name}: that code is listed twice."]}
                )
        clean.append((party, name, code))
    item.party_names.all().delete()
    PartyItemName.objects.bulk_create(
        [PartyItemName(item=item, party=p, name=n, code=c) for p, n, c in clean]
    )


class ItemImportSerializer(ItemSerializer):
    """The item as an import file has it: the form's fields, and the item
    number may be given (kept from the system the items come from)."""

    item_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta(ItemSerializer.Meta):
        read_only_fields = []


def _follow_item_numbers(ctx) -> None:
    follow_numbers("item", Item.objects.values_list("item_number", flat=True))


def _queryset():
    return Item.objects.select_related(
        "stock_unit", "sales_unit", "purchase_unit", "preferred_supplier", "customer"
    ).prefetch_related(
        "units__unit",
        "units__contains_unit",
        "gst_rates",
        "party_names__party",
        "plans__branch__company",
        "plans__transfer_from",
    )


exchange.register(
    exchange.Master(
        key="items",
        label="Items",
        noun="item",
        serializer=ItemImportSerializer,
        queryset=lambda ctx: _queryset().order_by("name"),
        save=lambda ctx, item, data: _save_item(item or Item(), data),
        after=_follow_item_numbers,
        sources={"erpnext": erpnext.item_tables},
        labels={
            "stock_unit": "Default unit (stock unit)",
            "mrp": "MRP (₹)",
            "usp": "USP (₹)",
            "usp_per": "USP per",
            "best_before_value": "Best before",
            "best_before_unit": "Best before in",
            "batch_no": "Batch No",
            "lead_time_days": "Lead time (days)",
            "min_order_qty": "Minimum order qty",
            "preferred_supplier": "Preferred supplier",
            "customer": "Customer (for Customer Provided)",
            "sales_description": "Sales description",
            "sales_unit": "Default sales unit",
            "purchase_description": "Purchase description",
            "purchase_unit": "Default purchase unit",
            "batch_tracked": "Track batches",
            "default_request_type": "Main fulfilment",
            "maintain_stock": "Maintain stock",
            "allow_purchase": "Allow purchase",
            "allow_sales": "Allow sales",
            "purchase_charge": "Use as purchase charge",
            "sales_charge": "Use as sales charge",
            "add_to_stock": "Add to stock cost",
            "offer_to_all": "Offer to all",
            "tds_section": "TDS section",
            "units": "Units of measure",
            "units.contains_qty": "Contains how many",
            "units.contains_unit": "Of",
            "units.length_cm": "Length (cm)",
            "units.breadth_cm": "Breadth (cm)",
            "units.height_cm": "Height (cm)",
            "units.net_kg": "Net weight (kg)",
            "units.gross_kg": "Gross weight (kg)",
            "units.barcode": "Barcode",
            "units.used_for": "Used for",
            "party_names": "Customer and supplier names",
            "party_names.party": "Customer or supplier",
            "party_names.name": "Their item name",
            "party_names.code": "Their item code",
            "plans": "Stock planning",
            "plans.branch": "Branch",
            "plans.fulfilment": "Fulfilment",
            "plans.transfer_from": "Transfer from",
            "plans.transfer_days": "Transfer days",
            "plans.safety_qty": "Safety stock",
            "plans.order_up_to": "Order up to",
            "gst_rates": "GST rates",
            "gst_rates.valid_from": "From",
            "gst_rates.rate": "GST rate (%)",
        },
        hints={
            "item_number": "Leave empty for the next number; or give the item's code "
            "from your old system (new items then carry on after the highest)",
            "best_before_value": "A number: manufacturing date plus this is the best-before date",
            "min_order_qty": "In the default unit",
            "plans.safety_qty": "In the default unit",
            "plans.order_up_to": "In the default unit; empty refills to the safety stock",
            "plans.transfer_from": "Only for Transfer: the branch it comes from",
            "plans.transfer_days": "Only for Transfer: days on the way",
            "units.contains_qty": "Leave empty on the stock unit's row",
            "units.contains_unit": "Leave empty on the stock unit's row",
        },
    )
)


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


class PlanBranchesView(APIView):
    """Every branch of every company that keeps stock, for the Stock Planning
    lines of an item (items are shared by the whole group)."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        rows = Branch.objects.filter(no_stock=False).select_related("company")
        return Response(
            [
                {
                    "id": b.pk,
                    "name": b.name,
                    "company": b.company_id,
                    "company_name": b.company.name,
                    "is_active": b.is_active,
                }
                for b in rows.order_by("company__name", "name")
            ]
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


def _saved_hsn(item, field: str = "hsn") -> str:
    """The HSN code stored for an existing item (blank for a new one)."""
    return Item.objects.filter(pk=item.pk).values_list(field, flat=True).first() or ""
