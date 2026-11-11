"""Units of measure: the group's list, shared by every company. Items pick
their units from it (spec 00, "Item units of measure")."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import Unit
from tenancy.context import tenant_atomic

# The GST unit quantity codes (UQC) accepted in GST returns, with their
# official names.
GST_UNIT_CODES = {
    "BAG": "Bags", "BAL": "Bale", "BDL": "Bundles", "BKL": "Buckles",
    "BOU": "Billions of units", "BOX": "Box", "BTL": "Bottles", "BUN": "Bunches",
    "CAN": "Cans", "CBM": "Cubic meter", "CCM": "Cubic centimeter",
    "CMS": "Centimeter", "CTN": "Cartons", "DOZ": "Dozen", "DRM": "Drum",
    "GGR": "Great gross", "GMS": "Grams", "GRS": "Gross", "GYD": "Gross yards",
    "KGS": "Kilograms", "KLR": "Kiloliter", "KME": "Kilometre", "LTR": "Litres",
    "MLT": "Millilitre", "MTR": "Meters", "MTS": "Metric ton", "NOS": "Numbers",
    "PAC": "Packs", "PCS": "Pieces", "PRS": "Pairs", "QTL": "Quintal",
    "ROL": "Rolls", "SET": "Sets", "SQF": "Square feet", "SQM": "Square meters",
    "SQY": "Square yards", "TBS": "Tablets", "TGM": "Ten gross", "THD": "Thousands",
    "TON": "Tonnes", "TUB": "Tubes", "UGS": "US gallons", "UNT": "Units",
    "YDS": "Yards", "OTH": "Others",
}  # fmt: skip

# name, short name, whole numbers only, GST code. The group starts with these.
STANDARD_UNITS = [
    ("Nos", "nos", True, "NOS"),
    ("Packet", "pkt", True, "PAC"),
    ("Inner box", "ibox", True, "BOX"),
    ("Carton", "ctn", True, "CTN"),
    ("Pallet", "plt", True, "OTH"),
    ("Bag", "bag", True, "BAG"),
    ("Bottle", "btl", True, "BTL"),
    ("Kilogram", "kg", False, "KGS"),
    ("Gram", "g", False, "GMS"),
    ("Tonne", "t", False, "TON"),
    ("Litre", "l", False, "LTR"),
    ("Millilitre", "ml", False, "MLT"),
    ("Metre", "m", False, "MTR"),
]


def seed_units(Unit) -> None:
    """Add the standard units the group lacks. Takes the model so that
    migrations can pass their historical version."""
    have = {n.lower() for n in Unit.objects.values_list("name", flat=True)}
    have_short = {n.lower() for n in Unit.objects.values_list("short_name", flat=True)}
    for name, short, whole, code in STANDARD_UNITS:
        if name.lower() in have or short.lower() in have_short:
            continue
        Unit.objects.create(name=name, short_name=short, whole_numbers=whole, gst_code=code)


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name", "short_name", "gst_code", "whole_numbers", "is_active"]


def _save_unit(unit: Unit, data: dict) -> Unit:
    if "gst_code" in data:
        data["gst_code"] = data["gst_code"].strip().upper()
        if data["gst_code"] not in GST_UNIT_CODES:
            raise ValidationError({"gst_code": ["Pick a GST unit code from the list."]})
    elif not unit.gst_code:
        raise ValidationError({"gst_code": ["Pick a GST unit code from the list."]})
    for field in ("name", "short_name"):
        if field in data:
            data[field] = data[field].strip()
    for field, label in (("name", "name"), ("short_name", "short name")):
        if field in data:
            clash = Unit.objects.filter(**{f"{field}__iexact": data[field]})
            if unit.pk:
                clash = clash.exclude(pk=unit.pk)
            if clash.exists():
                raise ValidationError({field: [f"There is already a unit with this {label}."]})
    refuse_key_changes("unit", unit, data)
    for field in ("name", "short_name", "gst_code", "whole_numbers", "is_active"):
        if field in data:
            setattr(unit, field, data[field])
    try:
        unit.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    unit.save()
    return unit


def _gst_code_cell(text: str) -> str:
    code = text.split("-")[0].strip().upper()
    if code not in GST_UNIT_CODES:
        raise ValueError(f"{text!r} is not a GST unit code (see the How to fill sheet)")
    return code


exchange.register(
    exchange.Master(
        key="units",
        label="Units",
        noun="unit",
        serializer=UnitSerializer,
        queryset=lambda ctx: Unit.objects.order_by("name"),
        save=lambda ctx, unit, data: _save_unit(unit or Unit(), data),
        codecs={
            "gst_code": exchange.Codec(
                to_cell=lambda v: v or "",
                from_cell=_gst_code_cell,
                choices=lambda: [f"{c} ({n})" for c, n in GST_UNIT_CODES.items()],
            )
        },
    )
)


class UnitListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(UnitSerializer(Unit.objects.order_by("name"), many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = UnitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unit = Unit()
        _save_unit(unit, dict(serializer.validated_data))
        return Response(UnitSerializer(unit).data, status=status.HTTP_201_CREATED)


class UnitDetailView(APIView):
    """Edit only: units are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        unit = Unit.objects.select_for_update().filter(pk=pk).first()
        if unit is None:
            raise NotFound("No such unit.")
        serializer = UnitSerializer(unit, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_unit(unit, dict(serializer.validated_data))
        return Response(UnitSerializer(unit).data)


class GstUnitCodeView(APIView):
    """The official GST unit codes, for the picker on the Units screen."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response([{"code": c, "name": n} for c, n in GST_UNIT_CODES.items()])
