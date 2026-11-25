"""Stock Receipt and Stock Delivery (Entry > Stock): a customer's own goods
coming in and going back (Sidharth, 2026-11-22, preview 9c in mockups/planning).

Stock Receipt   their goods arrive against their challan (their tea for job
                work, their packing material). Each line says where it is put,
                its batch (for an item that keeps batches) and how many bags;
                Submit numbers it (series "stock_receipt") and puts the goods in
                as THAT customer's stock (posting.StockMove.owner).
Stock Delivery  their goods go back to them unused. Bins and batches are picked
                by the pick rule from that customer's stock only, on every Save
                and again on Submit (series "stock_delivery"). Delivery Challan:
                "Returned to owner, not a sale".

Only items marked "Customer Provided". Quantity only: nothing in the books
(design: Customer Provided items never get accounting entries). A customer's
stock never mixes with ours or another customer's: an issue of it takes only
what that customer has at the place. Cancel moves the stock back.

Who may do what: the stock rights (stock.view, create, submit, cancel)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Max, Q, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import _plain
from core import attachments, numbering, paging
from core.api import Signed
from core.batches import save_batch
from core.companies import visible_companies
from core.items import picked as picked_items
from core.models import (
    PACKAGE_TYPES,
    Batch,
    Company,
    Item,
    ItemUnit,
    Ledger,
    LedgerGroup,
    Package,
    SalesPerson,
    WarehouseLocation,
)
from core.stores import sync_default_store
from posting import service
from posting.models import StockMove
from posting.service import StockLine, Voucher
from selling import picking
from selling import stock as places_of
from selling.delivery import _use_package
from selling.pick_lists import package_out
from shipping.models import CourierAccount
from stock.models import CustomerStock, CustomerStockBin, CustomerStockLine
from stock.transfers import (
    TRANSIT,
    _area,
    _branch,
    _company,
    _factor,
    _location_label,
    _place_name,
    _unit_name,
    may,
)
from tenancy.context import tenant_atomic

ZERO = Decimal("0")
RECEIPT, DELIVERY = CustomerStock.RECEIPT, CustomerStock.DELIVERY
# The voucher type in the stock ledger, the attachments' record type and the
# numbering series are all the same word.
KINDS = {RECEIPT: "stock_receipt", DELIVERY: "stock_delivery"}
NAMES = {RECEIPT: "Stock Receipt", DELIVERY: "Stock Delivery"}


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with stock entries.")


def customer_goods(item: Item) -> bool:
    return item.default_request_type == Item.CUSTOMER_PROVIDED


def held(company: Company, party, items, branch, area=None) -> dict[int, Decimal]:
    """What the customer has of each item at the place, in the stock unit."""
    rows = (
        StockMove.objects.filter(
            company=company,
            owner=party,
            item__in=items,
            location__in=places_of.places(branch, area),
        )
        .values("item")
        .annotate(q=Sum("qty"))
    )
    return {r["item"]: r["q"] or ZERO for r in rows}


# Reading ---------------------------------------------------------------------


def _entries(company):
    return CustomerStock.objects.filter(company=company).select_related(
        "company",
        "customer__party",
        "branch",
        "area",
        "transporter",
        "stores_person",
        "created_by",
        "submitted_by",
    )


def _bin_out(b: CustomerStockBin, factor: Decimal) -> dict:
    return {
        "id": b.pk,
        "location": b.location_id,
        "location_name": b.location.name,
        "batch": b.batch_id,
        "batch_number": b.batch.number if b.batch else "",
        "expiry": b.batch.expiry_date if b.batch else None,
        **package_out(b.package),
        "qty": _plain(b.qty),
        "qty_unit": picking.plain(b.qty / factor),
    }


def _line_out(e: CustomerStock, ln: CustomerStockLine) -> dict:
    factor = _factor(ln.item_id, ln.unit_id)
    bins = list(ln.bins.all())
    picked = sum((b.qty for b in bins), ZERO)
    out = {
        "id": ln.pk,
        "position": ln.position,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "hsn": ln.item.delivery_hsn or ln.item.hsn,
        "batch_tracked": ln.item.batch_tracked,
        "unit": ln.unit_id,
        "unit_name": _unit_name(ln.unit),
        "stock_unit_name": _unit_name(ln.item.stock_unit),
        "factor": picking.plain(factor),
        "qty": _plain(ln.qty),
        "location": ln.location_id,
        "location_name": _location_label(ln.location) if ln.location else "",
        "batch_number": ln.batch.number if ln.batch else ln.batch_number,
        "expiry_date": ln.batch.expiry_date if ln.batch else ln.expiry_date,
        "bags": ln.bags,
        "package_type": ln.package_type,
        "package_type_label": ln.get_package_type_display(),
    }
    if e.kind == DELIVERY:
        out["picked"] = picking.plain(picked / factor)
        out["short_picked"] = picked < ln.qty * factor
        out["bins"] = [_bin_out(b, factor) for b in bins]
    return out


def entry_out(e: CustomerStock, lines: bool = True) -> dict:
    data = {
        "id": e.pk,
        "company": e.company_id,
        "company_name": e.company.name,
        "kind": e.kind,
        "kind_label": e.get_kind_display(),
        "number": e.number,
        "status": e.status,
        "status_label": e.get_status_display(),
        "customer": e.customer_id,
        "customer_name": e.customer.name,
        "customer_gstin": e.customer.party.gstin if e.customer.party_id else "",
        "branch": e.branch_id,
        "branch_name": e.branch.name,
        "area": e.area_id,
        "place_name": _place_name(e.branch, e.area),
        "entry_date": e.entry_date,
        "challan_no": e.challan_no,
        "challan_date": e.challan_date,
        "reason": e.reason,
        "transporter": e.transporter_id,
        "transporter_name": e.transporter.name if e.transporter else "By Customer",
        "vehicle_no": e.vehicle_no,
        "eway_bill_no": e.eway_bill_no,
        "stores_person": e.stores_person_id,
        "stores_person_name": e.stores_person.name if e.stores_person else "",
        "notes": e.notes,
        "cancel_reason": e.cancel_reason,
        "created_by_name": e.created_by.display_name if e.created_by else "",
        "created_at": e.created_at,
        "submitted_at": e.submitted_at,
        "submitted_by_name": e.submitted_by.display_name if e.submitted_by else "",
    }
    if lines:
        rows = e.lines.select_related(
            "item__stock_unit", "unit", "batch", "location__parent__parent"
        ).prefetch_related("bins__location", "bins__batch", "bins__package")
        data["lines"] = [_line_out(e, ln) for ln in rows]
        data["packages"] = bags_of(e) if e.kind == RECEIPT else []
    else:
        data["items"] = ", ".join(ln.item.name for ln in e.lines.all())
    return data


def bags_of(e: CustomerStock) -> list[dict]:
    rows = Package.objects.filter(voucher_type=KINDS[e.kind], voucher_id=e.pk).select_related(
        "item__stock_unit", "batch", "location"
    )
    return [
        {
            "id": k.pk,
            "seq": k.seq,
            "number": k.number,
            "kind": k.kind,
            "kind_label": k.get_kind_display(),
            "item_name": k.item.name,
            "item_number": k.item.item_number,
            "batch": k.batch.number if k.batch_id else "",
            "expiry_date": k.batch.expiry_date if k.batch_id else None,
            "location": k.location_id,
            "location_name": str(k.location),
            "qty": _plain(k.qty),
            "left_qty": _plain(k.left_qty),
            "unit_name": _unit_name(k.item.stock_unit),
            "status": k.status,
            "status_label": k.get_status_display(),
            "position": k.position,
            "of_count": k.of_count,
        }
        for k in rows
    ]


def _fresh(e: CustomerStock) -> dict:
    return entry_out(_entries(e.company).get(pk=e.pk))


# Saving a draft ----------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    unit = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    location = serializers.IntegerField(required=False, allow_null=True)
    batch_number = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    expiry_date = serializers.DateField(required=False, allow_null=True)
    bags = serializers.IntegerField(required=False, min_value=0, default=0)
    package_type = serializers.ChoiceField(
        choices=[c for c, _ in PACKAGE_TYPES], required=False, default="bag"
    )


class EntrySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[RECEIPT, DELIVERY], required=False)
    # Taken from the items (Sidharth, 2026-11-23): each Customer Provided item
    # names its customer. Sent only while there is no item yet.
    customer = serializers.IntegerField(required=False, allow_null=True)
    branch = serializers.IntegerField()
    area = serializers.IntegerField(required=False, allow_null=True)
    entry_date = serializers.DateField()
    challan_no = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    challan_date = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    transporter = serializers.IntegerField(required=False, allow_null=True)
    vehicle_no = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    eway_bill_no = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    stores_person = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True)
    submit = serializers.BooleanField(required=False, default=False)


def _customer(company, value) -> Ledger:
    c = (
        Ledger.objects.filter(
            pk=value or 0, company=company, party_side="customer", party__isnull=False
        )
        .select_related("party")
        .first()
    )
    if c is None:
        raise ValidationError({"customer": ["Pick a customer of this company."]})
    return c


def put_places(branch):
    """Where a receipt can put goods: the branch's active areas and bins."""
    return (
        places_of.places(branch)
        .filter(is_active=True)
        .exclude(kind=WarehouseLocation.RACK)
        .select_related("parent__parent")
    )


def default_put(e: CustomerStock) -> WarehouseLocation | None:
    """The Area, else the branch's Receiving area, else its default store."""
    if e.area_id:
        return e.area
    sync_default_store(e.branch)
    places = WarehouseLocation.objects.filter(branch=e.branch, is_active=True)
    return (
        places.filter(kind=WarehouseLocation.AREA, purpose="receiving").order_by("name").first()
        or places.filter(is_default=True).first()
    )


def customer_of_items(company, data: dict) -> Ledger:
    """The company's ledger for the customer the entry's items belong to."""
    ids = [row["item"] for row in data["lines"]]
    items = {i.pk: i for i in Item.objects.filter(pk__in=ids).select_related("customer")}
    party = next(
        (
            items[i].customer
            for i in ids
            if i in items and customer_goods(items[i]) and items[i].customer_id
        ),
        None,
    )
    if party is None:
        return _customer(company, data.get("customer"))
    ledger = (
        Ledger.objects.filter(company=company, party_side="customer", party=party)
        .select_related("party")
        .first()
    )
    if ledger is None:
        raise ValidationError(
            {"customer": [f"{party.name} has no customer ledger in this company. Add it first."]}
        )
    return ledger


def _save(e: CustomerStock, data: dict) -> None:
    company = e.company
    e.customer = customer_of_items(company, data)
    e.branch = _branch(company, data["branch"], "branch")
    e.area = _area(e.branch, data.get("area"), "area")
    e.entry_date = data["entry_date"]
    challan_date = data.get("challan_date")
    if challan_date and challan_date > e.entry_date:
        raise ValidationError({"challan_date": ["The challan is dated after the goods came."]})
    e.challan_no = data.get("challan_no", "").strip()
    e.challan_date = challan_date
    transporter = None
    if data.get("transporter"):
        transporter = CourierAccount.objects.filter(pk=data["transporter"], company=company).first()
        if transporter is None:
            raise ValidationError({"transporter": ["Pick a transporter from the list."]})
    person = None
    if data.get("stores_person"):
        person = SalesPerson.objects.filter(pk=data["stores_person"], is_stores=True).first()
        if person is None:
            raise ValidationError({"stores_person": ["Pick a stores person from the list."]})
    e.transporter, e.stores_person = transporter, person
    e.vehicle_no = data.get("vehicle_no", "").strip().upper().replace(" ", "")
    e.eway_bill_no = data.get("eway_bill_no", "").strip().replace(" ", "")
    e.reason = data.get("reason", "").strip()
    e.notes = data.get("notes", "").strip()
    places = {p.pk: p for p in put_places(e.branch)} if e.kind == RECEIPT else {}
    errors, rows = [], []
    if not data["lines"]:
        errors.append("Add at least one item.")
    for k, row in enumerate(data["lines"], start=1):
        item = Item.objects.filter(pk=row["item"], is_active=True).first()
        if item is None:
            errors.append(f"Line {k}: pick an item from the list.")
            continue
        if not customer_goods(item):
            errors.append(
                f'Line {k}: {item.name} is not marked "Customer Provided". Only a customer\'s '
                "own goods come in or go back on this entry."
            )
            continue
        if not item.maintain_stock:
            errors.append(f"Line {k}: {item.name} does not keep stock.")
            continue
        if item.customer_id != e.customer.party_id:
            whose = item.customer.name if item.customer_id else "no customer yet"
            errors.append(
                f"Line {k}: {item.name} belongs to {whose}, not {e.customer.name}. One entry "
                "holds one customer's goods (set the customer on the item in Masters › Items)."
            )
            continue
        unit = ItemUnit.objects.filter(item=item, unit=row["unit"]).select_related("unit").first()
        if unit is None:
            errors.append(f"Line {k}: pick one of the units of {item.name}.")
            continue
        if unit.whole_numbers and row["qty"] != row["qty"].to_integral_value():
            errors.append(f"Line {k}: {item.name} is counted in whole {_unit_name(unit.unit)}.")
            continue
        place, number = None, ""
        if e.kind == RECEIPT:
            if row.get("location"):
                place = places.get(row["location"])
                if place is None:
                    errors.append(f"Line {k}: pick a place in {e.branch.name}.")
                    continue
            number = row.get("batch_number", "").strip()
            if number and not item.batch_tracked:
                errors.append(f"Line {k}: {item.name} does not keep batches.")
                continue
        rows.append((k, item, unit.unit, row, place, number))
    if errors:
        raise ValidationError({"lines": errors})
    e.save()
    e.lines.all().delete()
    for k, item, unit, row, place, number in rows:
        CustomerStockLine.objects.create(
            entry=e,
            position=k,
            item=item,
            unit=unit,
            qty=row["qty"],
            location=place,
            batch_number=number,
            expiry_date=row.get("expiry_date") if number else None,
            bags=(row.get("bags") or 0) if e.kind == RECEIPT else 0,
            package_type=row.get("package_type") or "bag",
        )
    if e.kind == DELIVERY:
        pick(e)


def pick(e: CustomerStock) -> None:
    """Choose bins and batches of the customer's own stock for every delivery
    line by the pick rule (earliest expiry first), replacing what it had."""
    CustomerStockBin.objects.filter(line__entry=e).delete()
    taken: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    owner = e.customer.party
    rows = []
    for ln in e.lines.select_related("item"):
        need = ln.qty * _factor(ln.item_id, ln.unit_id)
        for spot in picking.spots(ln.item, e.branch, e.area, owner=owner):
            if need <= 0:
                break
            key = (ln.item_id, spot.key)
            free = spot.free - taken[key]
            if free <= 0:
                continue
            take = min(free, need)
            taken[key] += take
            need -= take
            rows.append(
                CustomerStockBin(
                    line=ln,
                    location=spot.location,
                    batch=spot.batch,
                    package=spot.package,
                    qty=take,
                )
            )
    CustomerStockBin.objects.bulk_create(rows)


# Submit --------------------------------------------------------------------------


def _lines(e: CustomerStock) -> list[CustomerStockLine]:
    return list(
        e.lines.select_related("item__stock_unit", "unit", "location").prefetch_related(
            "bins__location", "bins__batch", "bins__package"
        )
    )


def problems(e: CustomerStock) -> list[dict]:
    """What stops Submit, each with its line."""
    out = []
    fallback = default_put(e) if e.kind == RECEIPT else None
    for ln in _lines(e):
        if e.kind == RECEIPT:
            if ln.item.batch_tracked and not ln.batch_number:
                out.append(
                    {
                        "line": ln.position,
                        "text": f"Line {ln.position}, {ln.item.name}: give the batch "
                        "(the customer's lot number, or one of our own).",
                    }
                )
            if ln.location is None and fallback is None:
                out.append(
                    {
                        "line": ln.position,
                        "text": f"Line {ln.position}, {ln.item.name}: pick where in "
                        f"{e.branch.name} it is put.",
                    }
                )
            continue
        factor = _factor(ln.item_id, ln.unit_id)
        picked = sum((b.qty for b in ln.bins.all()), ZERO)
        if picked < ln.qty * factor:
            out.append(
                {
                    "line": ln.position,
                    "text": f"Line {ln.position}, {ln.item.name}: {e.customer.name} has only "
                    f"{picking.plain(picked / factor)} {_unit_name(ln.unit)} free in "
                    f"{_place_name(e.branch, e.area)}; {picking.plain(ln.qty)} is to go back.",
                }
            )
    return out


def refused(e: CustomerStock, user) -> Response | None:
    """Why Submit cannot go ahead, answered without raising so a draft just
    saved is kept ("id")."""
    if not may(user, "submit"):
        return None
    if found := attachments.refuse_submit(e, KINDS[e.kind]):
        return found
    if found := problems(e):
        return Response(
            {"detail": "This entry cannot be submitted yet.", "problems": found, "id": e.pk},
            status=400,
        )
    return None


def _batch(ln: CustomerStockLine) -> Batch | None:
    if not ln.item.batch_tracked:
        return None
    found = Batch.objects.filter(item=ln.item, number__iexact=ln.batch_number).first()
    if found is not None:
        return found
    return save_batch(
        Batch(),
        {
            "item": ln.item,
            "number": ln.batch_number,
            "expiry_date": ln.expiry_date,
            "status": Batch.RELEASED,
            "notes": "Made by a stock receipt (customer's goods)",
        },
    )


def _submit(e: CustomerStock, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    kind = KINDS[e.kind]
    attachments.require_file(e, kind)
    if e.kind == DELIVERY:
        pick(e)  # the stock as it is now: another entry may have taken some since
    if found := problems(e):
        raise ValidationError({"detail": "This entry cannot be submitted yet.", "problems": found})
    lines = _lines(e)
    e.number = numbering.next_document_number(e.company, kind, e.entry_date, e.branch)
    owner = e.customer.party
    out: list[StockLine] = []
    if e.kind == RECEIPT:
        fallback = default_put(e)
        for ln in lines:
            ln.batch = _batch(ln)
            ln.location = ln.location or fallback
            ln.save(update_fields=["batch", "location"])
            qty = ln.qty * _factor(ln.item_id, ln.unit_id)
            out.append(
                StockLine(ln.item, ln.location, qty, batch=ln.batch, valued=False, owner=owner)
            )
    else:
        for ln in lines:
            for b in ln.bins.all():
                out.append(
                    StockLine(ln.item, b.location, -b.qty, batch=b.batch, valued=False, owner=owner)
                )
    service.post(Voucher(e.company, e.branch, e.entry_date, kind, e.pk, e.number, user), stock=out)
    if e.kind == RECEIPT:
        _make_bags(e, lines)
    else:
        for ln in lines:
            for b in ln.bins.all():
                if b.package_id:
                    _use_package(b.package_id, b.qty)
    e.status = CustomerStock.SUBMITTED
    e.submitted_at = timezone.now()
    e.submitted_by = user
    e.save()


def _make_bags(e: CustomerStock, lines: list[CustomerStockLine]) -> None:
    """Each bag or box gets its own number, PK-000241 and on, running per company
    as for goods receipts; the line's quantity is shared equally among its bags."""
    with_bags = [ln for ln in lines if ln.bags]
    if not with_bags:
        return
    Company.objects.select_for_update().get(pk=e.company_id)  # one numberer at a time
    seq = Package.objects.filter(company=e.company).aggregate(m=Max("seq"))["m"] or 0
    total = sum(ln.bags for ln in with_bags)
    made, n = [], 0
    for ln in with_bags:
        qty = ln.qty * _factor(ln.item_id, ln.unit_id)
        each = (qty / ln.bags).quantize(Decimal("0.000001"))
        for k in range(ln.bags):
            seq += 1
            n += 1
            this = each if k < ln.bags - 1 else qty - each * (ln.bags - 1)
            made.append(
                Package(
                    company=e.company,
                    seq=seq,
                    number=f"PK-{seq:06d}",
                    kind=ln.package_type,
                    item=ln.item,
                    batch=ln.batch,
                    location=ln.location,
                    qty=this,
                    left_qty=this,
                    voucher_type=KINDS[e.kind],
                    voucher_id=e.pk,
                    voucher_number=e.number,
                    position=n,
                    of_count=total,
                )
            )
    Package.objects.bulk_create(made)


# Cancel -----------------------------------------------------------------------


def _cancel(e: CustomerStock, user, reason: str) -> None:
    if e.status == CustomerStock.SUBMITTED:
        service.cancel(KINDS[e.kind], e.pk, user)
        if e.kind == RECEIPT:
            Package.objects.filter(voucher_type=KINDS[e.kind], voucher_id=e.pk).update(
                status=Package.CANCELLED, left_qty=ZERO
            )
        else:
            for b in CustomerStockBin.objects.filter(line__entry=e).exclude(package=None):
                _use_package(b.package_id, -b.qty)
    e.status = CustomerStock.CANCELLED
    e.cancel_reason = reason[:200]
    e.save()


# Views -----------------------------------------------------------------------


def _entry(request, pk: int, lock: bool = False) -> CustomerStock:
    rows = CustomerStock.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    e = rows.select_related("company", "customer__party", "branch__company", "area").first()
    if e is None or "stock" not in e.company.modules:
        raise NotFound("No such stock entry.")
    return e


def _kind(value) -> str:
    if value not in KINDS:
        raise ValidationError({"kind": ["Say receipt or delivery."]})
    return value


class EntryListView(APIView):
    """GET ?kind=receipt|delivery&view=draft|submitted|cancelled|all&q=text&
    customer=ID: the company's entries of that kind. POST: a new draft (with
    "submit": true, submitted at once)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        kind = _kind(request.query_params.get("kind"))
        rows = _entries(company).filter(kind=kind).prefetch_related("lines__item")
        view = request.query_params.get("view", "all")
        if view in dict(CustomerStock.STATUSES):
            rows = rows.filter(status=view)
        if customer := request.query_params.get("customer"):
            rows = rows.filter(customer=customer)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(customer__name__icontains=word)
                | Q(challan_no__icontains=word)
                | Q(lines__item__name__icontains=word)
            ).distinct()
        return Response([entry_out(e, lines=False) for e in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        company = _company(request, pk)
        serializer = EntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        e = CustomerStock(company=company, kind=_kind(data.get("kind")), created_by=request.user)
        _save(e, data)
        if data.get("submit"):
            if answer := refused(e, request.user):
                return answer
            _submit(e, request.user)
        return Response(_fresh(e), status=status.HTTP_201_CREATED)


class EntryDetailView(APIView):
    """GET one entry; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(_fresh(_entry(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        e = _entry(request, pk, lock=True)
        if e.status != CustomerStock.DRAFT:
            raise ValidationError(
                {"detail": "A submitted entry cannot be changed. Cancel it and make a new one."}
            )
        serializer = EntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(e, data)
        if data.get("submit"):
            if answer := refused(e, request.user):
                return answer
            _submit(e, request.user)
        return Response(_fresh(e))


class EntrySubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        e = _entry(request, pk, lock=True)
        if e.status != CustomerStock.DRAFT:
            raise ValidationError({"detail": "This entry is not a draft."})
        if answer := refused(e, request.user):
            return answer
        _submit(e, request.user)
        return Response(_fresh(e))


class EntryCancelView(APIView):
    """POST {reason}: a draft is dropped; a submitted one moves the stock back."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        e = _entry(request, pk, lock=True)
        if e.status == CustomerStock.CANCELLED:
            raise ValidationError({"detail": "This entry is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(e, request.user, reason)
        return Response(_fresh(e))


class EntryFormView(APIView):
    """GET ?kind=&customer=ID&branch=ID&area=ID: what the form needs: the
    customers, the stock branches with their areas and put-away places, the
    transporters and stores people, and the Customer Provided items with their
    units and (with a customer and branch) what that customer holds there."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        branches = list(company.branches.filter(no_stock=False).order_by("name"))
        places = (
            WarehouseLocation.objects.filter(branch__company=company)
            .exclude(kind=WarehouseLocation.RACK)
            .exclude(purpose=TRANSIT)
            .select_related("parent__parent")
            .order_by("name")
        )
        params = request.query_params
        branch = next((b for b in branches if str(b.pk) == params.get("branch")), None)
        area = None
        if branch is not None and params.get("area"):
            area = next(
                (
                    p
                    for p in places
                    if p.branch_id == branch.pk
                    and p.kind == WarehouseLocation.AREA
                    and str(p.pk) == params["area"]
                ),
                None,
            )
        customers = list(
            Ledger.objects.filter(company=company, party_side="customer", party__isnull=False)
            .select_related("party")
            .order_by("name")
        )
        customer = next((c for c in customers if str(c.pk) == params.get("customer")), None)
        items = list(
            picked_items(
                Item.objects.filter(
                    is_active=True, maintain_stock=True, default_request_type=Item.CUSTOMER_PROVIDED
                ),
                params,
            )
            .select_related("stock_unit", "customer")
            .prefetch_related("units__unit")
            .order_by("name")
        )
        ledger_of = {c.party_id: c for c in customers}
        have = held(company, customer.party, items, branch, area) if customer and branch else {}
        return Response(
            {
                # Where "Create …" in the customer picker adds a new customer's ledger.
                "customer_group": LedgerGroup.objects.filter(company=company, code="sundry_debtors")
                .values_list("pk", flat=True)
                .first(),
                "customers": [
                    {"id": c.pk, "name": c.name, "is_active": c.is_active} for c in customers
                ],
                "branches": [
                    {
                        "id": b.pk,
                        "name": b.name,
                        "is_active": b.is_active,
                        "areas": [
                            {"id": p.pk, "name": p.name, "is_active": p.is_active}
                            for p in places
                            if p.branch_id == b.pk and p.kind == WarehouseLocation.AREA
                        ],
                        "places": [
                            {"id": p.pk, "label": _location_label(p)}
                            for p in places
                            if p.branch_id == b.pk and p.is_active
                        ],
                    }
                    for b in branches
                ],
                "transporters": [
                    {"id": c.pk, "name": c.name}
                    for c in CourierAccount.objects.filter(company=company, is_active=True)
                ],
                "stores_people": []
                if paging.lean_setup(request.query_params)
                else [
                    {"id": p.pk, "name": p.name}
                    for p in SalesPerson.objects.filter(is_stores=True, is_active=True).order_by(
                        "name"
                    )
                ],
                "package_types": [{"id": c, "name": n} for c, n in PACKAGE_TYPES],
                "items": [
                    {
                        "id": i.pk,
                        "name": i.name,
                        "item_number": i.item_number,
                        "batch_tracked": i.batch_tracked,
                        # Whose goods (the item's customer) and that customer's ledger here.
                        "owner_name": i.customer.name if i.customer else "",
                        "customer": ledger_of[i.customer_id].pk
                        if i.customer_id in ledger_of
                        else None,
                        "stock_unit": i.stock_unit_id,
                        "stock_unit_name": _unit_name(i.stock_unit),
                        "units": [
                            {
                                "unit": u.unit_id,
                                "name": _unit_name(u.unit),
                                "whole_numbers": u.whole_numbers,
                                "factor": _plain(u.factor),
                            }
                            for u in i.units.all()
                        ],
                        "held": _plain(have.get(i.pk, ZERO)) if customer and branch else None,
                    }
                    for i in items
                ],
            }
        )


class EntryPdfView(APIView):
    """GET (&download=1): the Receipt Slip of a Stock Receipt, or the Delivery
    Challan of a Stock Delivery ("Returned to owner, not a sale")."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from core import printout

        _check(request, "view")
        e = _entry(request, pk)
        data = _fresh(e)
        receipt = e.kind == RECEIPT
        challan = data["challan_no"] and (
            f"Customer's challan {data['challan_no']}"
            + (f" of {data['challan_date']:%d-%m-%Y}" if data["challan_date"] else "")
        )
        scope = " · ".join(
            x
            for x in [
                f"{'From' if receipt else 'To'} {data['customer_name']}"
                + (f" (GSTIN {data['customer_gstin']})" if data["customer_gstin"] else ""),
                f"{'At' if receipt else 'From'} {data['place_name']}",
                data["entry_date"].strftime("%d-%m-%Y"),
                challan if receipt else "",
                f"Transporter {data['transporter_name']}",
                data["vehicle_no"] and f"Vehicle {data['vehicle_no']}",
                data["eway_bill_no"] and f"E-way bill {data['eway_bill_no']}",
                data["reason"],
                "The customer's own goods, held for them" if receipt else "",
                "" if receipt else "Returned to owner, not a sale",
            ]
            if x
        )

        def where(ln) -> str:
            if receipt:
                return ln["location_name"] + (
                    f" · {ln['batch_number']}" if ln["batch_number"] else ""
                )
            return "; ".join(
                b["location_name"] + (f" · {b['batch_number']}" if b["batch_number"] else "")
                for b in ln["bins"]
            )

        rows = [
            [
                str(ln["position"]),
                ln["item_name"],
                ln["hsn"],
                f"{ln['qty']} {ln['unit_name']}",
                where(ln),
                *([str(ln["bags"] or "")] if receipt else []),
            ]
            for ln in data["lines"]
        ]
        sheet = {
            "title": "",
            "columns": ["#", "Item", "HSN", "Qty", "Put In" if receipt else "Taken From"]
            + (["Bags"] if receipt else []),
            "rows": rows,
            "text": [2],
        }
        title = f"{'Receipt Slip' if receipt else 'Delivery Challan'} {data['number'] or 'Draft'}"
        response = printout.pdf_response(title, scope, [sheet], data["number"] or KINDS[e.kind])
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
