"""Own Use (Entry > Stock > Own Use): our own stock used inside the company,
for the office, the canteen, maintenance, R&D, or damaged and thrown away
(Sidharth, 2026-11-22, preview 9c in mockups/planning).

Draft   the lines; bins and batches are picked by the pick rule (earliest
        expiry first, held batches never) each time the draft is saved, from
        the Area or the whole branch. A draft counts as Reserved in the Stock
        Check. Each line is charged to the item's own "Expense Account" for the
        company (else its group's COGS/Expense ledger), or another expense
        ledger picked on the line.
Submit  gives the number (series "own_use"); the goods leave their bins at FIFO
        cost (voucher "own_use"): Dr each line's Expense Ledger, Cr the item
        group's Stock ledger.
Cancel  a draft is set aside; a submitted one puts the goods back and reverses
        the books.

Only our own goods: items marked "Customer Provided" are refused.
Who may do what: the stock rights (stock.view, create, submit, cancel)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import _plain
from core import attachments, numbering
from core.api import Signed
from core.companies import visible_companies
from core.models import Item, ItemUnit, Ledger, LedgerGroup, SalesPerson, WarehouseLocation
from posting import accounts, service
from posting import api as posting_api
from posting.models import StockLot
from posting.service import GLLine, StockLine, Voucher, money
from selling import picking
from selling.delivery import _use_package
from selling.pick_lists import package_out
from stock.customer import customer_goods
from stock.models import OwnUse, OwnUseBin, OwnUseLine
from stock.transfers import (
    TRANSIT,
    _area,
    _branch,
    _company,
    _factor,
    _place_name,
    _unit_name,
    free_at,
    may,
)
from tenancy.context import tenant_atomic

KIND = "own_use"  # the voucher type, the attachments' record type and the series
ZERO = Decimal("0")


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with stock entries.")


def default_ledger(company, item: Item) -> Ledger | None:
    """The item's Expense Account for the company, else its group's; None if
    neither is set."""
    try:
        return accounts.expense_ledger(company, item)
    except ValidationError:
        return None


def expense_ledgers(company):
    """What a line may be charged to: the company's active expense ledgers."""
    return (
        Ledger.objects.filter(company=company, is_active=True, group__nature=LedgerGroup.EXPENSE)
        .select_related("group")
        .order_by("name")
    )


def _ledger_of(e: OwnUse, ln: OwnUseLine) -> Ledger | None:
    return ln.expense_ledger or default_ledger(e.company, ln.item)


# Reading ---------------------------------------------------------------------


def _entries(company):
    return OwnUse.objects.filter(company=company).select_related(
        "company", "branch", "area", "stores_person", "created_by", "submitted_by"
    )


def _bin_out(b: OwnUseBin, factor: Decimal) -> dict:
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
        "cost": str(b.cost),
    }


def _line_out(e: OwnUse, ln: OwnUseLine) -> dict:
    factor = _factor(ln.item_id, ln.unit_id)
    bins = list(ln.bins.all())
    picked = sum((b.qty for b in bins), ZERO)
    ledger = _ledger_of(e, ln)
    return {
        "id": ln.pk,
        "position": ln.position,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "hsn": ln.item.hsn,
        "unit": ln.unit_id,
        "unit_name": _unit_name(ln.unit),
        "stock_unit_name": _unit_name(ln.item.stock_unit),
        "factor": picking.plain(factor),
        "qty": _plain(ln.qty),
        "picked": picking.plain(picked / factor),
        "short_picked": picked < ln.qty * factor,
        "expense_ledger": ln.expense_ledger_id,
        "ledger": ledger.pk if ledger else None,
        "ledger_name": ledger.name if ledger else "",
        "cost": str(ln.cost),
        "bins": [_bin_out(b, factor) for b in bins],
    }


def entry_out(e: OwnUse, lines: bool = True) -> dict:
    data = {
        "id": e.pk,
        "company": e.company_id,
        "number": e.number,
        "status": e.status,
        "status_label": e.get_status_display(),
        "branch": e.branch_id,
        "branch_name": e.branch.name,
        "area": e.area_id,
        "place_name": _place_name(e.branch, e.area),
        "entry_date": e.entry_date,
        "reason": e.reason,
        "stores_person": e.stores_person_id,
        "stores_person_name": e.stores_person.name if e.stores_person else "",
        "notes": e.notes,
        "value": str(e.value),
        "cancel_reason": e.cancel_reason,
        "created_by_name": e.created_by.display_name if e.created_by else "",
        "created_at": e.created_at,
        "submitted_at": e.submitted_at,
        "submitted_by_name": e.submitted_by.display_name if e.submitted_by else "",
    }
    if lines:
        rows = e.lines.select_related(
            "item__stock_unit", "item__item_group", "unit", "expense_ledger"
        ).prefetch_related("bins__location", "bins__batch", "bins__package")
        data["lines"] = [_line_out(e, ln) for ln in rows]
    else:
        data["items"] = ", ".join(ln.item.name for ln in e.lines.all())
    return data


def _fresh(e: OwnUse) -> dict:
    return entry_out(_entries(e.company).get(pk=e.pk))


# Saving a draft ----------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    unit = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    expense_ledger = serializers.IntegerField(required=False, allow_null=True)


class EntrySerializer(serializers.Serializer):
    branch = serializers.IntegerField()
    area = serializers.IntegerField(required=False, allow_null=True)
    entry_date = serializers.DateField()
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    stores_person = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True)
    submit = serializers.BooleanField(required=False, default=False)


def _save(e: OwnUse, data: dict) -> None:
    company = e.company
    e.branch = _branch(company, data["branch"], "branch")
    e.area = _area(e.branch, data.get("area"), "area")
    e.entry_date = data["entry_date"]
    person = None
    if data.get("stores_person"):
        person = SalesPerson.objects.filter(pk=data["stores_person"], is_stores=True).first()
        if person is None:
            raise ValidationError({"stores_person": ["Pick a stores person from the list."]})
    e.stores_person = person
    e.reason = data.get("reason", "").strip()
    e.notes = data.get("notes", "").strip()
    ledgers = {x.pk: x for x in expense_ledgers(company)}
    errors, rows = [], []
    if not data["lines"]:
        errors.append("Add at least one item.")
    for k, row in enumerate(data["lines"], start=1):
        item = Item.objects.filter(pk=row["item"], is_active=True).first()
        if item is None:
            errors.append(f"Line {k}: pick an item from the list.")
            continue
        if customer_goods(item):
            errors.append(
                f"Line {k}: {item.name} is a customer's own goods, not ours to use. Send it "
                "back on a Stock Delivery."
            )
            continue
        if not item.maintain_stock:
            errors.append(f"Line {k}: {item.name} does not keep stock.")
            continue
        unit = ItemUnit.objects.filter(item=item, unit=row["unit"]).select_related("unit").first()
        if unit is None:
            errors.append(f"Line {k}: pick one of the units of {item.name}.")
            continue
        if unit.whole_numbers and row["qty"] != row["qty"].to_integral_value():
            errors.append(f"Line {k}: {item.name} is counted in whole {_unit_name(unit.unit)}.")
            continue
        ledger = None
        if row.get("expense_ledger"):
            ledger = ledgers.get(row["expense_ledger"])
            if ledger is None:
                errors.append(f"Line {k}: pick an expense ledger of {company.name}.")
                continue
        rows.append((k, item, unit.unit, row["qty"], ledger))
    if errors:
        raise ValidationError({"lines": errors})
    e.save()
    e.lines.all().delete()
    for k, item, unit, qty, ledger in rows:
        OwnUseLine.objects.create(
            entry=e, position=k, item=item, unit=unit, qty=qty, expense_ledger=ledger
        )
    pick(e)


def pick(e: OwnUse) -> None:
    """Choose bins and batches for every line by the pick rule, from the Area
    (or the whole branch), replacing what the draft had."""
    OwnUseBin.objects.filter(line__entry=e).delete()
    taken: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    rows = []
    for ln in e.lines.select_related("item"):
        need = ln.qty * _factor(ln.item_id, ln.unit_id)
        for spot in picking.spots(ln.item, e.branch, e.area):
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
                OwnUseBin(
                    line=ln,
                    location=spot.location,
                    batch=spot.batch,
                    package=spot.package,
                    qty=take,
                )
            )
    OwnUseBin.objects.bulk_create(rows)


# Submit --------------------------------------------------------------------------


def _lines(e: OwnUse) -> list[OwnUseLine]:
    return list(
        e.lines.select_related(
            "item__item_group", "item__stock_unit", "unit", "expense_ledger"
        ).prefetch_related("bins__location", "bins__batch", "bins__package")
    )


def problems(e: OwnUse) -> list[dict]:
    """What stops Submit, each with its line: too little free stock, or no
    expense ledger to charge it to."""
    out = []
    for ln in _lines(e):
        factor = _factor(ln.item_id, ln.unit_id)
        picked = sum((b.qty for b in ln.bins.all()), ZERO)
        if picked < ln.qty * factor:
            out.append(
                {
                    "line": ln.position,
                    "text": f"Line {ln.position}, {ln.item.name}: only "
                    f"{picking.plain(picked / factor)} {_unit_name(ln.unit)} is free in "
                    f"{_place_name(e.branch, e.area)}; {picking.plain(ln.qty)} is to be used.",
                }
            )
        if _ledger_of(e, ln) is None:
            out.append(
                {
                    "line": ln.position,
                    "text": f"Line {ln.position}, {ln.item.name}: pick the Expense Ledger. The "
                    f'item has no "Expense Account" for {e.company.name}, nor its item group '
                    "a COGS/Expense Ledger.",
                }
            )
    return out


def _stock_needs(e: OwnUse, lines) -> list[tuple[int, Item]]:
    return [(ln.position, ln.item) for ln in lines]


def refused(e: OwnUse, user) -> Response | None:
    """Why Submit cannot go ahead, answered without raising so a draft just
    saved is kept ("id")."""
    if not may(user, "submit"):
        return None
    if found := attachments.refuse_submit(e, KIND):
        return found
    if found := problems(e):
        return Response(
            {"detail": "This entry cannot be submitted yet.", "problems": found, "id": e.pk},
            status=400,
        )
    if found := accounts.accounts_refusal(
        e.company, user, _stock_needs(e, _lines(e)), needs=(accounts.STOCK,)
    ):
        return Response({**found, "id": e.pk}, status=400)
    return None


def _submit(e: OwnUse, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    attachments.require_file(e, KIND)
    pick(e)  # the stock as it is now: another entry may have taken some since
    if found := problems(e):
        raise ValidationError({"detail": "This entry cannot be submitted yet.", "problems": found})
    lines = _lines(e)
    accounts.require_accounts(e.company, user, _stock_needs(e, lines), needs=(accounts.STOCK,))
    e.number = numbering.next_document_number(e.company, KIND, e.entry_date, e.branch)
    owners: list[tuple[OwnUseLine, OwnUseBin]] = []
    out: list[StockLine] = []
    for ln in lines:
        for b in ln.bins.all():
            out.append(StockLine(ln.item, b.location, -b.qty, batch=b.batch))
            owners.append((ln, b))

    def gl(values):
        dr: dict[int, Decimal] = defaultdict(lambda: ZERO)
        cr: dict[int, Decimal] = defaultdict(lambda: ZERO)
        ledgers = {}
        for (ln, _), value in zip(owners, values, strict=True):
            charge = _ledger_of(e, ln)
            stock = accounts.stock_ledger(e.company, ln.item)
            ledgers[charge.pk], ledgers[stock.pk] = charge, stock
            dr[charge.pk] += -value
            cr[stock.pk] += -value
        note = f"Own use {e.number}" + (f": {e.reason}" if e.reason else "")
        return [GLLine(ledgers[k], debit=v, remarks=note) for k, v in dr.items()] + [
            GLLine(ledgers[k], credit=v, remarks=note) for k, v in cr.items()
        ]

    posted = service.post(
        Voucher(e.company, e.branch, e.entry_date, KIND, e.pk, e.number, user), stock=out, gl=gl
    )
    line_cost: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for (ln, b), value in zip(owners, posted.stock_values, strict=True):
        b.cost = -value
        b.save(update_fields=["cost"])
        line_cost[ln.pk] += -value
        if b.package_id:
            _use_package(b.package_id, b.qty)
    for ln in lines:
        ln.cost = line_cost[ln.pk]
        ln.save(update_fields=["cost"])
    e.value = sum(line_cost.values(), ZERO)
    e.status = OwnUse.SUBMITTED
    e.submitted_at = timezone.now()
    e.submitted_by = user
    e.save()


# Cancel -----------------------------------------------------------------------


def _cancel(e: OwnUse, user, reason: str) -> None:
    if e.status == OwnUse.SUBMITTED:
        service.cancel(KIND, e.pk, user)
        for b in OwnUseBin.objects.filter(line__entry=e).exclude(package=None):
            _use_package(b.package_id, -b.qty)
    e.status = OwnUse.CANCELLED
    e.cancel_reason = reason[:200]
    e.save()


# The "Ledger Posting" section ---------------------------------------------------


def _estimate(e: OwnUse, ln: OwnUseLine) -> Decimal:
    """What a draft line will cost: its quantity at the FIFO lots of the branch
    as they stand today (the exact cost is fixed on Submit)."""
    need = sum((b.qty for b in ln.bins.all()), ZERO)
    total = ZERO
    lots = StockLot.objects.filter(
        company=e.company, branch=e.branch, item=ln.item, qty_left__gt=0, date__lte=e.entry_date
    ).order_by("date", "id")
    for lot in lots:
        if need <= 0:
            break
        take = min(need, lot.qty_left)
        total += lot.value_left if take == lot.qty_left else money(take * lot.rate)
        need -= take
    return total


def ledger_posting(e: OwnUse) -> dict:
    if e.status != OwnUse.DRAFT:
        return posting_api.posted(KIND, e.pk)
    dr: dict = defaultdict(lambda: ZERO)
    cr: dict = defaultdict(lambda: ZERO)
    names: dict = {}
    for ln in _lines(e):
        cost = _estimate(e, ln)
        charge = _ledger_of(e, ln)
        key = charge.pk if charge else f"x{ln.position}"
        names[key] = charge or "Expense Ledger not set"
        dr[key] += cost
        try:
            stock = accounts.stock_ledger(e.company, ln.item)
            skey = stock.pk
            names[skey] = stock
        except ValidationError:
            group = accounts.main_group(ln.item)
            skey = f"s{group.pk if group else ln.position}"
            names[skey] = f"Stock Ledger of {group} not set"
        cr[skey] += cost

    def row(key, debit=ZERO, credit=ZERO):
        x = names[key]
        if isinstance(x, Ledger):
            return posting_api.ledger_row(x, debit, credit)
        return posting_api.ledger_row(None, debit, credit, missing=x)

    rows = [row(k, debit=v) for k, v in dr.items()] + [row(k, credit=v) for k, v in cr.items()]
    return posting_api.preview(rows, "At today's FIFO cost; the exact cost is fixed on Submit. ")


# Views -----------------------------------------------------------------------


def _entry(request, pk: int, lock: bool = False) -> OwnUse:
    rows = OwnUse.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    e = rows.select_related("company", "branch__company", "area").first()
    if e is None or "stock" not in e.company.modules:
        raise NotFound("No such own use entry.")
    return e


class OwnUseListView(APIView):
    """GET ?view=draft|submitted|cancelled|all&q=text&branch=ID. POST: a new
    draft (with "submit": true, submitted at once)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        rows = _entries(company).prefetch_related("lines__item")
        view = request.query_params.get("view", "all")
        if view in dict(OwnUse.STATUSES):
            rows = rows.filter(status=view)
        if branch := request.query_params.get("branch"):
            rows = rows.filter(branch=branch)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(reason__icontains=word)
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
        e = OwnUse(company=company, created_by=request.user)
        _save(e, data)
        if data.get("submit"):
            if answer := refused(e, request.user):
                return answer
            _submit(e, request.user)
        return Response(_fresh(e), status=status.HTTP_201_CREATED)


class OwnUseDetailView(APIView):
    """GET one entry; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(_fresh(_entry(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        e = _entry(request, pk, lock=True)
        if e.status != OwnUse.DRAFT:
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


class OwnUseSubmitView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        e = _entry(request, pk, lock=True)
        if e.status != OwnUse.DRAFT:
            raise ValidationError({"detail": "This entry is not a draft."})
        if answer := refused(e, request.user):
            return answer
        _submit(e, request.user)
        return Response(_fresh(e))


class OwnUseCancelView(APIView):
    """POST {reason}: a draft is set aside; a submitted one puts the goods back
    and reverses the books."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        e = _entry(request, pk, lock=True)
        if e.status == OwnUse.CANCELLED:
            raise ValidationError({"detail": "This entry is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(e, request.user, reason)
        return Response(_fresh(e))


class OwnUsePostingView(APIView):
    """GET: the "Ledger Posting" section."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(ledger_posting(_entry(request, pk)))


class OwnUseFormView(APIView):
    """GET ?branch=ID&area=ID: the stock branches and their areas, the stores
    people, the expense ledgers, and our own stock items with their units, each
    one's default Expense Ledger and what is free at the place."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        branches = list(company.branches.filter(no_stock=False).order_by("name"))
        areas = (
            WarehouseLocation.objects.filter(branch__company=company, kind=WarehouseLocation.AREA)
            .exclude(purpose=TRANSIT)
            .order_by("name")
        )
        params = request.query_params
        branch = next((b for b in branches if str(b.pk) == params.get("branch")), None)
        area = None
        if branch is not None and params.get("area"):
            area = next(
                (a for a in areas if a.branch_id == branch.pk and str(a.pk) == params["area"]),
                None,
            )
        items = list(
            Item.objects.filter(is_active=True, maintain_stock=True)
            .exclude(default_request_type=Item.CUSTOMER_PROVIDED)
            .select_related("stock_unit", "item_group")
            .prefetch_related("units__unit")
            .order_by("name")
        )
        held = free_at(items, branch, area) if branch else {}
        ledgers = accounts.expense_ledgers_for(company, items)
        return Response(
            {
                "branches": [
                    {
                        "id": b.pk,
                        "name": b.name,
                        "is_active": b.is_active,
                        "areas": [
                            {"id": a.pk, "name": a.name, "is_active": a.is_active}
                            for a in areas
                            if a.branch_id == b.pk
                        ],
                    }
                    for b in branches
                ],
                "stores_people": [
                    {"id": p.pk, "name": p.name}
                    for p in SalesPerson.objects.filter(is_stores=True, is_active=True).order_by(
                        "name"
                    )
                ],
                "ledgers": [
                    {"id": x.pk, "name": x.name, "group_name": x.group.name}
                    for x in expense_ledgers(company)
                ],
                "items": [
                    {
                        "id": i.pk,
                        "name": i.name,
                        "item_number": i.item_number,
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
                        "ledger": (d := ledgers.get(i.pk)) and d.pk,
                        "ledger_name": d.name if d else "",
                        "in_stock": _plain(held.get(i.pk, ZERO)) if branch else None,
                    }
                    for i in items
                ],
            }
        )


class OwnUsePdfView(APIView):
    """GET (&download=1): the Issue Slip: what was taken, from where, charged
    to which ledger, at what cost."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from core import printout

        _check(request, "view")
        e = _entry(request, pk)
        data = _fresh(e)
        done = e.status == OwnUse.SUBMITTED
        scope = " · ".join(
            x
            for x in [
                data["place_name"],
                data["entry_date"].strftime("%d-%m-%Y"),
                data["reason"],
                data["stores_person_name"] and f"Issued by {data['stores_person_name']}",
                "Own use inside the company, not a sale",
            ]
            if x
        )
        rows = [
            [
                str(ln["position"]),
                ln["item_name"],
                f"{ln['qty']} {ln['unit_name']}",
                "; ".join(
                    b["location_name"] + (f" · {b['batch_number']}" if b["batch_number"] else "")
                    for b in ln["bins"]
                ),
                ln["ledger_name"],
                ln["cost"] if done else "",
            ]
            for ln in data["lines"]
        ]
        if done:
            rows.append(["", "Total", "", "", "", data["value"]])
        sheet = {
            "title": "",
            "columns": ["#", "Item", "Qty", "Taken From", "Expense Ledger", "Cost ₹"],
            "rows": rows,
        }
        title = f"Issue Slip {data['number'] or 'Draft'}"
        response = printout.pdf_response(title, scope, [sheet], data["number"] or KIND)
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
