"""What a document posted: its GL entries and stock moves, and the "Ledger
Posting" section every entry screen shows once saved (Sidharth, 2026-11-17)."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from core.api import EDIT, VIEW, Signed, _check
from core.companies import visible_companies
from core.models import Company, ItemGroup, ItemGroupAccount, Ledger, Package, WarehouseLocation
from core.notifications import notify
from posting import accounts
from posting.models import GLEntry, StockMove
from posting.service import money

ZERO = Decimal("0")


def ledger_row(ledger: Ledger | None, debit=ZERO, credit=ZERO, missing: str = "") -> dict:
    """One line of the "Ledger Posting" section. With no ledger, `missing` says
    which ledger is not set yet."""
    return {
        "ledger": ledger.pk if ledger else None,
        "ledger_name": ledger.name if ledger else missing,
        "group_name": ledger.group.name if ledger else "",
        "debit": str(money(debit)),
        "credit": str(money(credit)),
        "missing": ledger is None,
    }


def preview(rows: list[dict], note: str = "") -> dict:
    """What Submit will post, for a draft."""
    return {"posted": False, "reversed": False, "rows": rows, "note": note}


def posted(voucher_type: str, voucher_id: int) -> dict:
    """What a submitted entry posted, one line per ledger, debits first."""
    entries = GLEntry.objects.filter(voucher_type=voucher_type, voucher_id=voucher_id)
    sums: dict[int, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for e in entries.filter(is_reversal=False):
        sums[e.ledger_id][0] += e.debit
        sums[e.ledger_id][1] += e.credit
    ledgers = Ledger.objects.select_related("group").in_bulk(list(sums))
    rows = [ledger_row(ledgers[k], d, c) for k, (d, c) in sums.items()]
    rows.sort(key=lambda r: (r["debit"] == "0.00", r["ledger_name"].lower()))
    return {
        "posted": True,
        "reversed": entries.filter(is_reversal=True).exists(),
        "rows": rows,
        "note": "",
    }


class AskSerializer(serializers.Serializer):
    group = serializers.IntegerField()
    document = serializers.CharField(max_length=120)
    # The ledgers this entry needs ("Stock Ledger", ...): a goods receipt does
    # not need the Sales Ledger, so the notice does not ask for it.
    needs = serializers.ListField(child=serializers.CharField(max_length=60), required=False)


class AskLedgersView(APIView):
    """POST {group, document}: "Ask to set" on the missing-ledgers popup, for a
    person who may not change item groups. Everyone in the company whose role may
    change masters gets a notice under the bell, linking to the item group."""

    permission_classes = [Signed]

    def post(self, request, pk: int):
        _check(request, VIEW)
        company = visible_companies(request.user).filter(pk=pk).first()
        if company is None:
            raise NotFound("No such company.")
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = ItemGroup.objects.filter(pk=serializer.validated_data["group"]).first()
        if group is None:
            raise NotFound("No such item group.")
        missing = _missing_of(company, group)
        needs = serializer.validated_data.get("needs")
        if needs:
            missing = [label for label in missing if label in needs]
        if not missing:
            done = f"The ledgers of {group.name} are set now. Submit again."
            raise ValidationError({"detail": done})
        people = [u for u in _may_change_masters(company) if u.pk != request.user.pk]
        if not people:
            raise ValidationError({"detail": "Nobody else may change masters. Ask an Owner."})
        document = serializer.validated_data["document"]
        notify(
            people,
            company,
            f"Set ledgers on item group {group.name}",
            f"{request.user.display_name} could not submit {document}.\n\n"
            + "\n".join(f"• {label} of {group.name} not set" for label in missing)
            + f"\n\nCompany: {company.name}",
            f"#/item-groups?form={group.pk}&at=ledgers",
        )
        return Response({"asked": len(people)})


def _missing_of(company: Company, group: ItemGroup) -> list[str]:
    row = ItemGroupAccount.objects.filter(group=group, company=company).first()
    return [
        label
        for key, label in accounts.ACCOUNT_LABELS.items()
        if row is None or getattr(row, f"{key}_ledger_id") is None
    ]


def _may_change_masters(company: Company):
    return [
        u
        for u in User.objects.filter(is_active=True).prefetch_related("companies", "roles")
        if u.can(EDIT)
        and (u.is_owner or not u.companies.exists() or u.companies.filter(pk=company.pk).exists())
    ]


class PostingsView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        kind = request.query_params.get("voucher_type", "")
        try:
            pk = int(request.query_params.get("voucher_id", ""))
        except ValueError:
            return Response({"gl": [], "stock": []})
        gl = GLEntry.objects.filter(voucher_type=kind, voucher_id=pk).select_related("ledger")
        stock = StockMove.objects.filter(voucher_type=kind, voucher_id=pk).select_related(
            "item", "location__parent", "batch"
        )
        return Response(
            {
                "gl": [
                    {
                        "date": e.date,
                        "ledger": e.ledger_id,
                        "ledger_name": e.ledger.name,
                        "debit": e.debit,
                        "credit": e.credit,
                        "is_reversal": e.is_reversal,
                    }
                    for e in gl
                ],
                "stock": [
                    {
                        "date": m.date,
                        "item_number": m.item.item_number,
                        "item_name": m.item.name,
                        "location": str(m.location),
                        "batch": m.batch.number if m.batch_id else "",
                        "qty": m.qty,
                        "rate": m.rate,
                        "value": m.value,
                        "is_reversal": m.is_reversal,
                    }
                    for m in stock
                ],
            }
        )


class BinContentsView(APIView):
    """What is in a bin, rack or area now: each item and batch with its quantity, and
    the bags or boxes kept there. Opened by scanning the QR code on a bin label
    (Sidharth, 2026-11-15)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        place = (
            WarehouseLocation.objects.filter(
                pk=pk, branch__company__in=visible_companies(request.user)
            )
            .select_related("branch__company", "parent")
            .first()
        )
        if place is None:
            raise NotFound("No such bin.")
        places = [place, *place.children.all()]  # a rack shows its bins
        stock = (
            StockMove.objects.filter(location__in=places)
            .values(
                "location",
                "item",
                "item__name",
                "item__item_number",
                "item__stock_unit__short_name",
                "batch",
                "batch__number",
                "batch__expiry_date",
                "batch__status",
            )
            .annotate(qty=Sum("qty"))
            .exclude(qty=0)
            .order_by("item__name", "batch__number")
        )
        names = {p.pk: str(p) for p in places}
        bags = Package.objects.filter(
            location__in=places, status__in=(Package.IN_STOCK, Package.PART_USED)
        ).select_related("item", "batch", "item__stock_unit")
        return Response(
            {
                "id": place.pk,
                "code": f"LOC-{place.pk:06d}",
                "name": str(place),
                "kind": place.kind,
                "kind_label": place.get_kind_display(),
                "purpose_label": place.get_purpose_display() if place.purpose else "",
                "branch_name": place.branch.name,
                "company": place.branch.company_id,
                "company_name": place.branch.company.name,
                "stock": [
                    {
                        "location_name": names[s["location"]],
                        "item_name": s["item__name"],
                        "item_number": s["item__item_number"],
                        "batch": s["batch__number"] or "",
                        "expiry_date": s["batch__expiry_date"],
                        "batch_status": s["batch__status"] or "",
                        "qty": str(s["qty"]),
                        "unit_name": s["item__stock_unit__short_name"],
                    }
                    for s in stock
                ],
                "packages": [
                    {
                        "number": k.number,
                        "kind_label": k.get_kind_display(),
                        "location_name": names[k.location_id],
                        "item_name": k.item.name,
                        "batch": k.batch.number if k.batch_id else "",
                        "left_qty": str(k.left_qty),
                        "unit_name": k.item.stock_unit.short_name,
                        "status_label": k.get_status_display(),
                        "voucher_number": k.voucher_number,
                    }
                    for k in bags
                ],
            }
        )
