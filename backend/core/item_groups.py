"""Item groups: the group's tree of item groups, shared by every company.
Each item sits in one group; groups nest to any depth like ledger groups."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import ItemGroup
from tenancy.context import tenant_atomic


def descendant_ids(group: ItemGroup) -> set[int]:
    """The ids of every group below this one."""
    found: set[int] = set()
    frontier = [group.pk]
    while frontier:
        kids = (
            set(ItemGroup.objects.filter(parent_id__in=frontier).values_list("pk", flat=True))
            - found
        )
        found |= kids
        frontier = list(kids)
    return found


class ItemGroupSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=ItemGroup.objects.all(), allow_null=True, required=False
    )
    item_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ItemGroup
        fields = ["id", "name", "parent", "notes", "is_active", "item_count"]


def _save_group(group: ItemGroup, data: dict) -> ItemGroup:
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            ItemGroup.objects.all(),
            data["name"],
            exclude=group.pk,
            kind="item_group",
            message='There is already an item group named "{name}".',
        )
    parent = data.get("parent")
    if (
        parent is not None
        and group.pk
        and (parent.pk == group.pk or parent.pk in descendant_ids(group))
    ):
        raise ValidationError({"parent": ["A group cannot sit under itself or a group below it."]})
    if parent is not None and not parent.is_active and parent.pk != group.parent_id:
        raise ValidationError({"parent": [f"{parent.name} is disabled."]})
    if parent is not None and parent.pk != group.parent_id and parent.items.exists():
        raise ValidationError(
            {
                "parent": [
                    f"{parent.name} already has items, and items sit only in groups without "
                    "sub-groups. Move its items to another group first."
                ]
            }
        )
    refuse_key_changes("item_group", group, data)
    for field in ("name", "parent", "notes", "is_active"):
        if field in data:
            setattr(group, field, data[field])
    try:
        group.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    group.save()
    return group


def _parent_cell(text: str) -> int:
    group = ItemGroup.objects.filter(name__iexact=text.strip()).first()
    if group is None:
        raise ValueError(
            f"there is no item group called {text!r}; "
            "list a parent group before the groups under it"
        )
    return group.pk


def _parent_name(pk) -> str:
    return (
        ItemGroup.objects.filter(pk=pk).values_list("name", flat=True).first() or "" if pk else ""
    )


exchange.register(
    exchange.Master(
        key="item-groups",
        label="Item groups",
        noun="item group",
        serializer=ItemGroupSerializer,
        queryset=lambda ctx: ItemGroup.objects.order_by("name"),
        save=lambda ctx, group, data: _save_group(group or ItemGroup(), data),
        exclude=("item_count",),
        codecs={
            "parent": exchange.Codec(
                to_cell=_parent_name,
                from_cell=_parent_cell,
                hint="Name of the group it sits under; leave blank for a main group",
            )
        },
    )
)


def _groups():
    return ItemGroup.objects.annotate(item_count=Count("items")).order_by("name")


class ItemGroupListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(ItemGroupSerializer(_groups(), many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = ItemGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = ItemGroup()
        _save_group(group, dict(serializer.validated_data))
        return Response(
            ItemGroupSerializer(_groups().get(pk=group.pk)).data, status=status.HTTP_201_CREATED
        )


class ItemGroupDetailView(APIView):
    """Edit only: item groups are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        group = ItemGroup.objects.select_for_update().filter(pk=pk).first()
        if group is None:
            raise NotFound("No such item group.")
        serializer = ItemGroupSerializer(group, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_group(group, dict(serializer.validated_data))
        return Response(ItemGroupSerializer(_groups().get(pk=group.pk)).data)
