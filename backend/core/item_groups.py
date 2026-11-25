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
from core.locks import (
    account_uses,
    lock_status,
    refuse_key_changes,
    refuse_move_outside_top,
    root_group,
)
from core.models import Company, ItemGroup, ItemGroupAccount, Ledger
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


ACCOUNT_FIELDS = {
    "stock_ledger": "Stock Ledger",
    "cogs_ledger": "COGS/Expense Ledger",
    "sales_ledger": "Sales Ledger",
}


class AccountRowSerializer(serializers.Serializer):
    """One company's accounts on a main item group (write side)."""

    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    stock_ledger = serializers.PrimaryKeyRelatedField(
        queryset=Ledger.objects.all(), allow_null=True, required=False
    )
    cogs_ledger = serializers.PrimaryKeyRelatedField(
        queryset=Ledger.objects.all(), allow_null=True, required=False
    )
    sales_ledger = serializers.PrimaryKeyRelatedField(
        queryset=Ledger.objects.all(), allow_null=True, required=False
    )


def _account_rows(group: ItemGroup) -> list[dict]:
    """The accounts the group's items post to: its own rows when it is a main
    group, else its main group's (read only, inherited)."""
    top = root_group(group)
    rows = ItemGroupAccount.objects.filter(group=top).select_related(
        "company", "stock_ledger", "cogs_ledger", "sales_ledger"
    )
    out = []
    for r in rows.order_by("company__name"):
        out.append(
            {
                "company": r.company_id,
                "company_name": r.company.name,
                "stock_ledger": r.stock_ledger_id,
                "stock_ledger_name": r.stock_ledger.name if r.stock_ledger_id else "",
                "cogs_ledger": r.cogs_ledger_id,
                "cogs_ledger_name": r.cogs_ledger.name if r.cogs_ledger_id else "",
                "sales_ledger": r.sales_ledger_id,
                "sales_ledger_name": r.sales_ledger.name if r.sales_ledger_id else "",
                "locked": account_uses(top, r.company),
            }
        )
    return out


class ItemGroupSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=ItemGroup.objects.all(), allow_null=True, required=False
    )
    item_count = serializers.IntegerField(read_only=True, default=0)
    lock = serializers.SerializerMethodField()
    accounts = serializers.SerializerMethodField()
    accounts_in = AccountRowSerializer(many=True, required=False, write_only=True)
    accounts_from = serializers.SerializerMethodField()

    # Pickers on every screen read the list: they skip the "in use" checks and the
    # accounts (many queries a group); the Item groups screen asks with ?full=1.
    def get_lock(self, group) -> dict | None:
        if self.context.get("list"):  # an export: no per-record "in use" checks
            return None
        if self.context.get("lean"):
            return None
        return lock_status("item_group", group)

    def get_accounts(self, group) -> list | None:
        if self.context.get("lean"):
            return None
        return _account_rows(group)

    def get_accounts_from(self, group):
        """For a sub-group: the main group its accounts come from."""
        if self.context.get("lean") or group.parent_id is None:
            return None
        top = root_group(group)
        return {"id": top.pk, "name": top.name}

    class Meta:
        model = ItemGroup
        fields = [
            "id",
            "name",
            "parent",
            "notes",
            "is_active",
            "item_count",
            "lock",
            "accounts",
            "accounts_in",
            "accounts_from",
        ]


def _under(ledger: Ledger, group_code: str) -> bool:
    node = ledger.group
    while node is not None:
        if node.code == group_code:
            return True
        node = node.parent
    return False


def _check_account_ledger(company: Company, field: str, ledger: Ledger | None) -> None:
    if ledger is None:
        return
    label = ACCOUNT_FIELDS[field]
    if ledger.company_id != company.pk:
        raise ValidationError(
            {"accounts_in": [f"{label}: {ledger.name} is not a ledger of {company.name}."]}
        )
    if not ledger.is_active:
        raise ValidationError({"accounts_in": [f"{label}: {ledger.name} is disabled."]})
    if field == "stock_ledger" and not _under(ledger, "stock_in_hand"):
        raise ValidationError(
            {"accounts_in": [f"{label}: {ledger.name} must be under Stock-in-Hand."]}
        )
    if field == "sales_ledger":
        if ledger.group.nature != "income":
            raise ValidationError(
                {"accounts_in": [f"{label}: {ledger.name} must be an income ledger."]}
            )
        return
    if field != "stock_ledger" and ledger.group.nature != "expense":
        raise ValidationError(
            {"accounts_in": [f"{label}: {ledger.name} must be an expense ledger."]}
        )


def _save_accounts(group: ItemGroup, rows: list[dict]) -> None:
    """Replace the group's per-company accounts. Only a main group holds them, and
    a company's row that is locked (entries exist) stays as it is."""
    if group.parent_id is not None:
        if rows:
            raise ValidationError(
                {
                    "accounts_in": [
                        f"Accounts are set on the main group {root_group(group).name}; "
                        "this group uses them."
                    ]
                }
            )
        return
    seen: set[int] = set()
    clean = {}
    for r in rows:
        company = r["company"]
        if company.pk in seen:
            raise ValidationError({"accounts_in": [f"{company.name} is listed twice."]})
        seen.add(company.pk)
        for field in ACCOUNT_FIELDS:
            _check_account_ledger(company, field, r.get(field))
        clean[company.pk] = r
    existing = {a.company_id: a for a in group.accounts.select_related("company")}
    for company_id, row in existing.items():
        why = account_uses(group, row.company)
        if not why:
            continue
        new = clean.get(company_id)
        # A Sales Ledger still blank may be set on a row in use.
        same = new is not None and all(
            getattr(row, f"{f}_id") == (new.get(f).pk if new.get(f) else None)
            for f in ACCOUNT_FIELDS
            if not (f == "sales_ledger" and row.sales_ledger_id is None)
        )
        if not same:
            raise ValidationError(
                {
                    "accounts_in": [
                        f"Cannot change the accounts of {row.company.name}: this is in use "
                        f"({', '.join(why)})."
                    ]
                }
            )
    group.accounts.all().delete()
    ItemGroupAccount.objects.bulk_create(
        [
            ItemGroupAccount(
                group=group,
                company=r["company"],
                **{f: r.get(f) for f in ACCOUNT_FIELDS},
            )
            for r in clean.values()
            if any(r.get(f) for f in ACCOUNT_FIELDS)
        ]
    )


def _save_group(group: ItemGroup, data: dict) -> ItemGroup:
    accounts = data.pop("accounts_in", None)
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
    if "parent" in data:
        refuse_move_outside_top(
            "item_group", group, "parent", group.parent, data["parent"], "group"
        )
    for field in ("name", "parent", "notes", "is_active"):
        if field in data:
            setattr(group, field, data[field])
    try:
        group.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    group.save()
    if group.parent_id is not None and group.pk:
        # a group that now sits under another uses that main group's accounts
        for row in group.accounts.select_related("company"):
            if why := account_uses(group, row.company):
                raise ValidationError(
                    {"parent": [f"Its accounts for {row.company.name} are in use ({why[0]})."]}
                )
        group.accounts.all().delete()
    if accounts is not None:
        _save_accounts(group, accounts)
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
        exclude=("item_count", "accounts", "accounts_in", "accounts_from"),
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
        lean = request.query_params.get("full") != "1"
        return Response(ItemGroupSerializer(_groups(), many=True, context={"lean": lean}).data)

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
