"""Units of measure: the group's list, shared by every company. Items pick
their units from it (spec 00, "Item units of measure")."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import EDIT, VIEW, Signed, _check
from core.models import Unit
from tenancy.context import tenant_atomic

# name, short name, whole numbers only. The group starts with these.
STANDARD_UNITS = [
    ("Nos", "nos", True),
    ("Packet", "pkt", True),
    ("Inner box", "ibox", True),
    ("Carton", "ctn", True),
    ("Pallet", "plt", True),
    ("Bag", "bag", True),
    ("Bottle", "btl", True),
    ("Kilogram", "kg", False),
    ("Gram", "g", False),
    ("Tonne", "t", False),
    ("Litre", "l", False),
    ("Millilitre", "ml", False),
    ("Metre", "m", False),
]


def seed_units(Unit) -> None:
    """Add the standard units the group lacks. Takes the model so that
    migrations can pass their historical version."""
    have = {n.lower() for n in Unit.objects.values_list("name", flat=True)}
    have_short = {n.lower() for n in Unit.objects.values_list("short_name", flat=True)}
    for name, short, whole in STANDARD_UNITS:
        if name.lower() in have or short.lower() in have_short:
            continue
        Unit.objects.create(name=name, short_name=short, whole_numbers=whole)


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name", "short_name", "whole_numbers", "is_active"]


def _save_unit(unit: Unit, data: dict) -> None:
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
    for field in ("name", "short_name", "whole_numbers", "is_active"):
        if field in data:
            setattr(unit, field, data[field])
    try:
        unit.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    unit.save()


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
