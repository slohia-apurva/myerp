"""Price lists (Sidharth, 2026-11-14): named sets of rates, for selling or for
buying, each rate starting on a date, with lower rates for bigger quantities.

A customer picks a Selling list (Party.price_list) and may have rates of its
own for single items (PartyItemPrice, edited from the customer and from the
item; one set of data seen from both sides). Where the customer has any rate
for an item, only those are used for it; otherwise its price list, and
otherwise nothing (the item's own MRP is unchanged). Sales and purchase
documents call `rate_for` when they are built.
"""

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import Currency, Item, Party, PartyItemPrice, PriceList, PriceListLine, Unit
from tenancy.context import tenant_atomic

LINE_FIELDS = ["id", "item", "item_name", "unit", "unit_label", "min_qty", "rate", "from_date"]


def unit_label(unit: Unit) -> str:
    return f"{unit.name} ({unit.short_name})"


class LineSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit_label = serializers.SerializerMethodField()

    def get_unit_label(self, line) -> str:
        return unit_label(line.unit)

    class Meta:
        model = PriceListLine
        fields = LINE_FIELDS
        read_only_fields = ["id"]
        extra_kwargs = {"min_qty": {"required": False}}


def clean_lines(rows: list[dict], who: str) -> list[dict]:
    """Check a set of price lines: the unit is one the item has, the quantity
    and rate make sense, and no line repeats."""
    seen: set[tuple] = set()
    out = []
    unit_ids: dict[int, set[int]] = {}
    for row in rows:
        item, unit = row["item"], row["unit"]
        qty = row.get("min_qty") if row.get("min_qty") is not None else Decimal(1)
        if qty <= 0:
            raise ValidationError({who: [f"{item.name}: From Qty must be more than 0."]})
        if item.pk not in unit_ids:
            unit_ids[item.pk] = set(item.units.values_list("unit_id", flat=True))
        if unit.pk not in unit_ids[item.pk]:
            raise ValidationError(
                {who: [f"{item.name} is not kept in {unit_label(unit)}; pick one of its units."]}
            )
        who_for = row["party"].pk if row.get("party") else None
        key = (who_for, item.pk, unit.pk, qty, row["from_date"])
        if key in seen:
            raise ValidationError(
                {
                    who: [
                        f"{item.name} ({unit_label(unit)}) has two prices for the same "
                        f"quantity and date."
                    ]
                }
            )
        seen.add(key)
        out.append({**row, "min_qty": qty})
    return out


# Price lists ---------------------------------------------------------------


class PriceListSerializer(serializers.ModelSerializer):
    lines = LineSerializer(many=True, required=False)
    currency = serializers.SlugRelatedField(
        slug_field="code", queryset=Currency.objects.all(), allow_null=True, required=False
    )
    price_count = serializers.SerializerMethodField()
    party_count = serializers.IntegerField(read_only=True, default=0)  # customers and suppliers
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    lock = serializers.SerializerMethodField()

    class Meta:
        model = PriceList
        fields = [
            "id", "name", "kind", "kind_label", "currency", "is_active", "notes",
            "lines", "price_count", "party_count", "lock",
        ]  # fmt: skip

    def get_price_count(self, plist) -> int:
        return plist.lines.count()

    def get_lock(self, plist) -> dict | None:
        if self.context.get("list"):  # an export: no per-record "in use" checks
            return None
        from core.locks import lock_status

        return lock_status("price_list", plist)


def _save_list(plist: PriceList, data: dict) -> PriceList:
    lines = data.pop("lines", None)
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            PriceList.objects.all(),
            data["name"],
            exclude=plist.pk,
            kind="price_list",
            message='There is already a price list named "{name}".',
        )
    refuse_key_changes("price_list", plist, data)
    for field in ("name", "kind", "currency", "is_active", "notes"):
        if field in data:
            setattr(plist, field, data[field])
    try:
        plist.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    if lines is not None:
        lines = clean_lines(lines, "lines")
    plist.save()
    if lines is not None:
        plist.lines.all().delete()
        PriceListLine.objects.bulk_create(
            [
                PriceListLine(
                    price_list=plist,
                    item=r["item"],
                    unit=r["unit"],
                    min_qty=r["min_qty"],
                    rate=r["rate"],
                    from_date=r["from_date"],
                )
                for r in lines
            ]
        )
        recorder.touch(plist)
    return plist


def _count_parties(request=None):
    return PriceList.objects.annotate(
        party_count=Count("parties", distinct=True) + Count("suppliers", distinct=True)
    )


exchange.register(
    exchange.Master(
        key="price-lists",
        label="Price lists",
        noun="price list",
        serializer=PriceListSerializer,
        queryset=lambda ctx: PriceList.objects.prefetch_related(
            "lines__item", "lines__unit"
        ).order_by("name"),
        save=lambda ctx, plist, data: _save_list(plist or PriceList(), data),
        exclude=("price_count", "party_count", "kind_label", "lock"),
        labels={
            "kind": "Type",
            "lines": "Prices",
            "lines.item": "Item",
            "lines.unit": "Unit",
            "lines.min_qty": "From qty",
            "lines.rate": "Rate",
            "lines.from_date": "From date",
        },
        hints={"lines.rate": "Before GST"},
    )
)


class PriceListListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        rows = _count_parties().prefetch_related("lines__item", "lines__unit").order_by("name")
        return Response(PriceListSerializer(rows, many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = PriceListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plist = PriceList()
        _save_list(plist, dict(serializer.validated_data))
        return Response(PriceListSerializer(plist).data, status=status.HTTP_201_CREATED)


class PriceListDetailView(APIView):
    """Edit only: price lists are never deleted, only disabled."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        plist = PriceList.objects.select_for_update().filter(pk=pk).first()
        if plist is None:
            raise NotFound("No such price list.")
        serializer = PriceListSerializer(plist, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_list(plist, dict(serializer.validated_data))
        return Response(PriceListSerializer(plist).data)


# A customer's own prices, from the customer and from the item ---------------


class PartyPriceSerializer(LineSerializer):
    party = serializers.PrimaryKeyRelatedField(queryset=Party.objects.all())
    side = serializers.ChoiceField(choices=PriceList.KINDS, required=False)
    party_name = serializers.CharField(source="party.name", read_only=True)

    class Meta:
        model = PartyItemPrice
        fields = [*LINE_FIELDS, "party", "party_name", "side"]
        validators = []  # a set is replaced as a whole; clean_lines refuses repeats
        read_only_fields = ["id"]
        extra_kwargs = {"min_qty": {"required": False}}


def _replace_party_prices(qs, rows: list[dict], who: str, side: str) -> None:
    rows = clean_lines(rows, who)
    qs.filter(side=side).delete()
    PartyItemPrice.objects.bulk_create(
        [
            PartyItemPrice(
                side=side,
                party=r["party"],
                item=r["item"],
                unit=r["unit"],
                min_qty=r["min_qty"],
                rate=r["rate"],
                from_date=r["from_date"],
            )
            for r in rows
        ]
    )


def _side(request) -> str:
    """ "selling" (customers) unless ?side=buying (suppliers)."""
    side = request.query_params.get("side", PriceList.SELLING)
    if side not in (PriceList.SELLING, PriceList.BUYING):
        raise ValidationError({"side": ["Use selling or buying."]})
    return side


class PartyPricesView(APIView):
    """GET or PUT one customer's (or, with ?side=buying, supplier's) own prices; PUT
    replaces the set."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        qs = PartyItemPrice.objects.filter(party_id=pk, side=_side(request))
        return Response(
            PartyPriceSerializer(qs.select_related("item", "unit", "party"), many=True).data
        )

    @tenant_atomic()
    def put(self, request, pk: int):
        _check(request, EDIT)
        party = Party.objects.select_for_update().filter(pk=pk).first()
        if party is None:
            raise NotFound("No such customer or supplier.")
        rows = [{**r, "party": party.pk} for r in (request.data or [])]
        serializer = PartyPriceSerializer(data=rows, many=True)
        serializer.is_valid(raise_exception=True)
        side = _side(request)
        _replace_party_prices(
            PartyItemPrice.objects.filter(party=party), serializer.validated_data, "prices", side
        )
        qs = PartyItemPrice.objects.filter(party=party, side=side)
        return Response(
            PartyPriceSerializer(qs.select_related("item", "unit", "party"), many=True).data
        )


class ItemPricesView(APIView):
    """GET or PUT the prices customers (side=selling) or suppliers (side=buying) have for
    one item."""

    permission_classes = [Signed]
    side = PriceList.SELLING

    def get(self, request, pk: int):
        _check(request, VIEW)
        qs = PartyItemPrice.objects.filter(item_id=pk, side=self.side)
        qs = qs.select_related("item", "unit", "party")
        return Response(PartyPriceSerializer(qs.order_by("party__name"), many=True).data)

    @tenant_atomic()
    def put(self, request, pk: int):
        _check(request, EDIT)
        item = Item.objects.select_for_update().filter(pk=pk).first()
        if item is None:
            raise NotFound("No such item.")
        rows = [{**r, "item": item.pk} for r in (request.data or [])]
        serializer = PartyPriceSerializer(data=rows, many=True)
        serializer.is_valid(raise_exception=True)
        _replace_party_prices(
            PartyItemPrice.objects.filter(item=item), serializer.validated_data, "prices", self.side
        )
        qs = PartyItemPrice.objects.filter(item=item, side=self.side)
        qs = qs.select_related("item", "unit", "party")
        return Response(PartyPriceSerializer(qs.order_by("party__name"), many=True).data)


class ItemSupplierPricesView(ItemPricesView):
    """The same for suppliers' prices of one item."""

    side = PriceList.BUYING


# Finding a rate (used by sales and purchase documents when they are built) ---


def _in_force(lines, qty: Decimal, on: datetime.date):
    """The latest-started rate of the biggest From Qty slab not above qty."""
    started = [ln for ln in lines if ln.from_date <= on and ln.min_qty <= qty]
    if not started:
        return None
    biggest = max(ln.min_qty for ln in started)
    return max((ln for ln in started if ln.min_qty == biggest), key=lambda ln: ln.from_date)


def rate_for(
    party: Party | None,
    item: Item,
    unit: Unit,
    qty,
    on: datetime.date,
    side: str = PriceList.SELLING,
) -> Decimal | None:
    """The rate for `qty` of `item` in `unit` on a date: the customer's (side
    "selling") or supplier's (side "buying") own prices for the item once one
    has started (if none fits the quantity, no rate), otherwise its price list,
    otherwise None."""
    return find_rate(party, item, unit, qty, on, side)[0]


def find_rate(
    party: Party | None,
    item: Item,
    unit: Unit,
    qty,
    on: datetime.date,
    side: str = PriceList.SELLING,
) -> tuple[Decimal | None, str]:
    """`rate_for` with where the rate came from, for the screen to say: "own"
    (the party's own Item Prices), the price list's name, or "" (no rate)."""
    qty = Decimal(qty)
    list_id = None
    if party is not None:
        list_id = party.price_list_id if side == PriceList.SELLING else party.buying_price_list_id
        own = list(PartyItemPrice.objects.filter(party=party, side=side, item=item, unit=unit))
        if own:
            line = _in_force(own, qty, on)
            if line is not None:
                return line.rate, "own"
            if any(ln.from_date <= on for ln in own):
                return None, ""
    if list_id:
        theirs = PriceListLine.objects.filter(price_list_id=list_id, item=item, unit=unit)
        line = _in_force(list(theirs.select_related("price_list")), qty, on)
        if line is not None:
            return line.rate, line.price_list.name
    return None, ""
