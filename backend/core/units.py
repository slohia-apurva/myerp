"""Units of measure: the group's list, shared by every company. Items pick
their units from it (spec 00, "Item units of measure")."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import lock_status, refuse_key_changes
from core.models import Unit
from tenancy.context import tenant_atomic
from tenancy.models import GstUnit


def gst_codes(active_only: bool = True) -> dict[str, str]:
    """The GST unit codes (UQC) from the central list (tenancy.GstUnit, kept by
    platform admins on Central > GST Units): code -> official name."""
    rows = GstUnit.objects.all()
    if active_only:
        rows = rows.filter(is_active=True)
    return dict(rows.values_list("code", "name"))


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
    # The other GST unit codes, one unit each (Sidharth, 2026-11-23), so items
    # brought from other systems find their units.
    ("Bale", "bal", True, "BAL"),
    ("Box", "box", True, "BOX"),
    ("Buckle", "bkl", True, "BKL"),
    ("Bundle", "bdl", True, "BDL"),
    ("Bunch", "bun", True, "BUN"),
    ("Billion Units", "bou", False, "BOU"),
    ("Can", "can", True, "CAN"),
    ("Centimetre", "cm", False, "CMS"),
    ("Cubic Centimetre", "ccm", False, "CCM"),
    ("Cubic Metre", "cbm", False, "CBM"),
    ("Dozen", "doz", True, "DOZ"),
    ("Drum", "drm", True, "DRM"),
    ("Great Gross", "ggr", True, "GGR"),
    ("Gross", "grs", True, "GRS"),
    ("Gross Yard", "gyd", False, "GYD"),
    ("Kilolitre", "klr", False, "KLR"),
    ("Kilometre", "km", False, "KME"),
    ("Metric Ton", "mts", False, "MTS"),
    ("Pair", "prs", True, "PRS"),
    ("Pieces", "pcs", True, "PCS"),
    ("Quintal", "qtl", False, "QTL"),
    ("Roll", "rol", True, "ROL"),
    ("Set", "set", True, "SET"),
    ("Square Foot", "sqft", False, "SQF"),
    ("Square Metre", "sqm", False, "SQM"),
    ("Square Yard", "sqyd", False, "SQY"),
    ("Tablet", "tbs", True, "TBS"),
    ("Ten Gross", "tgm", True, "TGM"),
    ("Thousand", "thd", True, "THD"),
    ("Tube", "tub", True, "TUB"),
    ("Unit", "unt", True, "UNT"),
    ("US Gallon", "gal", False, "UGS"),
    ("Yard", "yd", False, "YDS"),
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
    lock = serializers.SerializerMethodField()

    def get_lock(self, unit) -> dict | None:
        if self.context.get("list"):  # an export: no per-record "in use" checks
            return None
        # Pickers on every screen read the list: they skip the "in use" checks (a dozen
        # queries a unit); the Units screen asks for them with ?full=1.
        if self.context.get("lean"):
            return None
        return lock_status("unit", unit)

    class Meta:
        model = Unit
        fields = ["id", "name", "short_name", "gst_code", "whole_numbers", "is_active", "lock"]


def _save_unit(unit: Unit, data: dict) -> Unit:
    if "gst_code" in data:
        data["gst_code"] = data["gst_code"].strip().upper()
        # A new or changed code must be active in the central list; a unit keeps
        # the code it has even if that code is later disabled.
        code = data["gst_code"]
        if not code or (code != unit.gst_code and code not in gst_codes()):
            raise ValidationError({"gst_code": ["Pick a GST unit code from the list."]})
    elif not unit.gst_code:
        raise ValidationError({"gst_code": ["Pick a GST unit code from the list."]})
    for field, label in (("name", "name"), ("short_name", "short name")):
        if field in data:
            data[field] = duplicates.tidy(data[field])
            duplicates.check_name(
                Unit.objects.all(),
                data[field],
                field=field,
                exclude=unit.pk,
                kind="unit",
                message=f'There is already a unit with the {label} "{{name}}".',
            )
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
    if code not in gst_codes(active_only=False):
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
                choices=lambda: [f"{c} ({n})" for c, n in gst_codes().items()],
            )
        },
    )
)


class UnitListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        lean = request.query_params.get("full") != "1"
        rows = Unit.objects.order_by("name")
        return Response(UnitSerializer(rows, many=True, context={"lean": lean}).data)

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
        return Response([{"code": c, "name": n} for c, n in gst_codes().items()])
