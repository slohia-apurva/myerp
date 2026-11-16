"""An item's own "Expense Account" per company (Sidharth, 2026-11-16, preview
82): where a purchase bill without goods receipt books the item. A company
with no row uses the item's main group's COGS/Expense ledger."""

from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import EDIT, VIEW, Signed, _check
from core.companies import visible_companies
from core.models import Company, Item, ItemAccount, ItemGroupAccount, Ledger
from tenancy.context import tenant_atomic


def _rows(item: Item, user) -> list[dict]:
    from posting.accounts import main_group

    rows = ItemAccount.objects.filter(item=item).select_related("expense_ledger")
    own = {a.company_id: a for a in rows}
    group = main_group(item)
    by_group = {}
    if group is not None:
        by_group = {
            a.company_id: a.cogs_ledger.name
            for a in ItemGroupAccount.objects.filter(
                group=group, cogs_ledger__isnull=False
            ).select_related("cogs_ledger")
        }
    out = []
    for company in visible_companies(user).order_by("name"):
        row = own.get(company.pk)
        out.append(
            {
                "company": company.pk,
                "company_name": company.name,
                "expense_ledger": row.expense_ledger_id if row else None,
                "expense_ledger_name": row.expense_ledger.name if row else "",
                "group_ledger_name": by_group.get(company.pk, ""),
            }
        )
    return out


class RowSerializer(serializers.Serializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    expense_ledger = serializers.PrimaryKeyRelatedField(
        queryset=Ledger.objects.select_related("group"), allow_null=True
    )


class ItemAccountsView(APIView):
    """GET or PUT one item's Expense Account in each company the person works in."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        item = Item.objects.filter(pk=pk).first()
        if item is None:
            raise NotFound("No such item.")
        return Response(_rows(item, request.user))

    @tenant_atomic()
    def put(self, request, pk: int):
        _check(request, EDIT)
        item = Item.objects.select_for_update().filter(pk=pk).first()
        if item is None:
            raise NotFound("No such item.")
        serializer = RowSerializer(data=request.data or [], many=True)
        serializer.is_valid(raise_exception=True)
        allowed = set(visible_companies(request.user).values_list("pk", flat=True))
        for row in serializer.validated_data:
            company, ledger = row["company"], row["expense_ledger"]
            if company.pk not in allowed:
                continue
            current = ItemAccount.objects.filter(item=item, company=company).first()
            if ledger is None:
                if current:
                    current.delete()
                continue
            label = f"Expense Account for {company.name}"
            if ledger.company_id != company.pk:
                raise ValidationError(
                    {"accounts": [f"{label}: {ledger.name} is not a ledger of {company.name}."]}
                )
            if ledger.group.nature != "expense":
                raise ValidationError(
                    {"accounts": [f"{label}: {ledger.name} must be an expense ledger."]}
                )
            if current and current.expense_ledger_id == ledger.pk:
                continue
            if not ledger.is_active:
                raise ValidationError({"accounts": [f"{label}: {ledger.name} is disabled."]})
            if current:
                current.expense_ledger = ledger
                current.save(update_fields=["expense_ledger"])
            else:
                ItemAccount.objects.create(item=item, company=company, expense_ledger=ledger)
        return Response(_rows(item, request.user))
