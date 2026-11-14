"""Warehouses: a physical warehouse is a branch of the company ticked
"Warehouse". It holds racks, a rack holds bins (the physical storage
locations), and the warehouse also has named areas such as receiving,
production and despatch (Sidharth, 2026-11-12). Stock entries will point at a
bin or an area."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check, _company
from core.companies import visible_companies
from core.locks import lock_status, refuse_key_changes
from core.models import Branch, WarehouseLocation
from tenancy.context import tenant_atomic

L = WarehouseLocation


class LocationSerializer(serializers.ModelSerializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False)
    parent = serializers.PrimaryKeyRelatedField(
        queryset=L.objects.all(), allow_null=True, required=False
    )
    purpose_label = serializers.CharField(source="get_purpose_display", read_only=True)
    bin_count = serializers.IntegerField(read_only=True, default=0)
    lock = serializers.SerializerMethodField()

    def get_lock(self, location) -> dict:
        return lock_status("warehouse_location", location)

    class Meta:
        model = L
        fields = [
            "id",
            "branch",
            "kind",
            "parent",
            "name",
            "purpose",
            "purpose_label",
            "notes",
            "is_active",
            "bin_count",
            "is_default",
            "lock",
        ]
        read_only_fields = ["is_default"]


class LocationExchangeSerializer(LocationSerializer):
    """The file names a bin's rack ("rack") instead of pointing at it."""

    rack = serializers.CharField(
        source="parent.name", required=False, allow_blank=True, default="", max_length=60
    )
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())

    class Meta(LocationSerializer.Meta):
        fields = [f for f in LocationSerializer.Meta.fields if f != "parent"] + ["rack"]


def _same_scope(branch: Branch, kind: str, parent):
    """The records a new name must differ from: the rack's bins, or the
    racks (areas) of the warehouse."""
    if parent is not None:
        return L.objects.filter(parent=parent)
    return L.objects.filter(branch=branch, kind=kind, parent__isnull=True)


def save_location(company, location: L | None, data: dict) -> L:
    """Add or change a rack, bin or area; the screen and imports both save
    here. `data` is validated serializer data."""
    new = location is None or location.pk is None
    location = location or L()
    data = dict(data)
    if isinstance(data.get("parent"), dict):  # from a file: the rack's name
        rack_name = duplicates.tidy(data.pop("parent").get("name", ""))
        data.pop("rack", None)
        data["parent"] = None
        if rack_name:
            branch = data.get("branch") or location.branch
            found = (
                L.objects.filter(branch=branch, kind=L.RACK, name__iexact=rack_name).first()
                if branch
                else None
            )
            if found is None:
                raise ValidationError({"rack": [f"There is no rack called {rack_name!r}."]})
            data["parent"] = found

    branch = data.get("branch", location.branch if location.pk else None)
    if branch is None:
        raise ValidationError({"branch": ["Pick the warehouse."]})
    if branch.company_id != company.pk:
        raise ValidationError({"branch": ["Pick a warehouse of this company."]})
    if branch.no_stock:
        raise ValidationError({"branch": [f"{branch.name} is ticked No stock."]})
    if not new and branch.pk != location.branch_id:
        raise ValidationError({"branch": ["A rack, bin or area cannot move to another warehouse."]})
    if new and not branch.is_active:
        raise ValidationError({"branch": [f"{branch.name} is closed."]})
    kind = data.get("kind", location.kind)
    if kind not in (L.RACK, L.BIN, L.AREA):
        raise ValidationError({"kind": ["Say whether this is a rack, a bin or an area."]})
    parent = data.get("parent", location.parent if location.pk else None)

    if kind == L.BIN:
        if parent is None:
            raise ValidationError({"parent": ["A bin sits on a rack. Pick the rack."]})
        if parent.kind != L.RACK or parent.branch_id != branch.pk:
            raise ValidationError({"parent": ["Pick a rack of this warehouse."]})
        if not parent.is_active and parent.pk != location.parent_id:
            raise ValidationError({"parent": [f"The rack {parent.name} is disabled."]})
    elif parent is not None:
        raise ValidationError({"parent": [f"A {kind} does not sit on a rack."]})

    purpose = data.get("purpose", location.purpose)
    if kind == L.AREA and not purpose:
        raise ValidationError({"purpose": ["Say what the area is for."]})
    if kind != L.AREA:
        purpose = ""

    if not new and location.is_default:
        if data.get("is_active") is False:
            raise ValidationError({"is_active": ["The default store cannot be disabled."]})
        if kind != location.kind or purpose != location.purpose:
            raise ValidationError({"kind": ["The default store stays a storage area."]})
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
    name = data.get("name", location.name)
    if not name:
        raise ValidationError({"name": ["Give it a name."]})
    if "name" in data or new:
        what = {L.RACK: "rack", L.BIN: "bin", L.AREA: "area"}[kind]
        duplicates.check_name(
            _same_scope(branch, kind, parent),
            name,
            exclude=location.pk,
            kind="warehouse_location",
            message=f"This {'rack' if kind == L.BIN else 'warehouse'} already has a {what} "
            'named "{name}".',
        )

    if not new:
        refuse_key_changes("warehouse_location", location, {**data, "kind": kind, "parent": parent})
    if data.get("is_active") is False and location.kind == L.RACK:
        open_bins = location.children.filter(is_active=True).count()
        if open_bins:
            raise ValidationError(
                {"is_active": [f"Disable its {open_bins} bin(s) first, or move the stock out."]}
            )
    if data.get("is_active") and kind == L.BIN and parent is not None and not parent.is_active:
        raise ValidationError({"is_active": [f"Enable the rack {parent.name} first."]})

    location.branch, location.kind, location.parent = branch, kind, parent
    location.name, location.purpose = name, purpose
    for field in ("notes", "is_active"):
        if field in data:
            setattr(location, field, data[field])
    try:
        location.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    location.save()
    return location


def _locations(company):
    return (
        L.objects.filter(branch__company=company)
        .select_related("branch", "parent")
        .annotate(bin_count=Count("children", filter=Q(children__is_active=True)))
        .order_by("name")
    )


def _exchange_save(ctx, location, data):
    return save_location(ctx.company, location, data)


exchange.register(
    exchange.Master(
        key="warehouse-locations",
        label="Racks, bins and areas",
        noun="rack, bin or area",
        serializer=LocationExchangeSerializer,
        # Racks before the bins on them, so a file can be loaded back in.
        queryset=lambda ctx: _locations(ctx.company).order_by("branch__name", "kind", "name"),
        save=_exchange_save,
        per_company=True,
        exclude=("bin_count", "purpose_label", "is_default"),
        labels={"branch": "Warehouse", "rack": "On rack", "purpose": "Area is for"},
        hints={
            "kind": "Rack, Bin or Area",
            "rack": "Only for a bin: the name of its rack. List a rack before its bins.",
            "purpose": "Only for an area: what it is for (Receiving, Production, Despatch...)",
            "branch": "The branch (one that is not ticked No stock)",
        },
    )
)


def warehouse_tree(company) -> list[dict]:
    """Every warehouse branch with its racks (and their bins) and areas."""
    rows = list(_locations(company))
    out = []
    for branch in company.branches.filter(no_stock=False).order_by("name"):
        mine = [r for r in rows if r.branch_id == branch.pk]
        bins: dict[int, list] = {}
        for r in mine:
            if r.kind == L.BIN:
                bins.setdefault(r.parent_id, []).append(r)
        racks = []
        for r in mine:
            if r.kind == L.RACK:
                racks.append(
                    {
                        **LocationSerializer(r).data,
                        "bins": LocationSerializer(bins.get(r.pk, []), many=True).data,
                    }
                )
        areas = LocationSerializer([r for r in mine if r.kind == L.AREA], many=True).data
        out.append(
            {
                "id": branch.pk,
                "name": branch.name,
                "city": branch.city,
                "is_active": branch.is_active,
                "racks": racks,
                "areas": areas,
            }
        )
    return out


class WarehouseListView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(warehouse_tree(_company(request, pk)))


class LocationListView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = LocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        location = save_location(company, None, serializer.validated_data)
        return Response(
            LocationSerializer(_locations(company).get(pk=location.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class LocationDetailView(APIView):
    """Edit only: racks, bins and areas are never deleted, only disabled."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        location = L.objects.select_for_update().select_related("branch").filter(pk=pk).first()
        if location is None or not visible_companies(request.user).filter(
            pk=location.branch.company_id
        ):
            raise NotFound("No such rack, bin or area.")
        serializer = LocationSerializer(location, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        save_location(location.branch.company, location, serializer.validated_data)
        return Response(
            LocationSerializer(_locations(location.branch.company).get(pk=location.pk)).data
        )
