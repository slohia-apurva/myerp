"""Stock Transfer (Entry > Stock > Stock Transfer): goods moving between two
branches of one company (Sidharth, 2026-11-22, preview 9a in mockups/planning).

Only between branches with the same GSTIN: a move to a branch with another
GSTIN is a sale in GST law (design rule 13) and is refused here for now.

Draft      the lines; bins and batches are chosen by the pick rule
           (selling.picking: earliest expiry first, held batches never) each
           time the draft is saved, from the From Area or the whole branch. A
           draft counts in the Stock Check: Reserved at From, Incoming at To.
Dispatch   gives the number; the goods leave their bins at FIFO cost (voucher
           "stock_transfer" at From) and sit in To's "In Transit" place at that
           same value (voucher "stock_transfer_in" at To). Both branches keep the
           company's one Stock Ledger, so the books get nothing.
Receive    at To: what came goes from In Transit into the bins chosen
           (voucher "stock_transfer_receipt"); a shortfall needs a reason and
           goes out as a transit loss: Dr Stock Adjustment, Cr Stock.
Cancel     a draft, or one in transit (the goods go back to their bins). A
           received transfer cannot be cancelled: send the goods back.

Packages: a package taken whole moves with the goods (its place changes); one
opened on the way out stays at From, part used.

Who may do what: the stock rights (stock.view, create, submit, cancel)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import _money, _plain
from core import attachments, numbering
from core.api import Signed
from core.api import _company as _visible_company
from core.companies import visible_companies
from core.items import picked
from core.models import Branch, Item, ItemUnit, Package, WarehouseLocation
from core.stores import sync_default_store
from posting import accounts, service
from posting import api as posting_api
from posting.models import StockLot, StockMove
from posting.service import GLLine, StockLine, Voucher
from selling import picking
from selling import stock as places_of
from selling.delivery import _use_package
from selling.models import PickList, PickListLine
from selling.pick_lists import package_out
from shipping.models import CourierAccount
from stock.models import StockTransfer, StockTransferBin, StockTransferLine
from tenancy.context import tenant_atomic

KIND = "stock_transfer"  # the From branch's voucher, and the attachments' record type
KIND_IN = "stock_transfer_in"  # into To's In Transit place on Dispatch
KIND_RECEIPT = "stock_transfer_receipt"  # out of In Transit into To's bins on Receive
NUMBERS = "stock_transfer"  # the series on Settings › Numbering
ZERO = Decimal("0")
TRANSIT = "transit"  # WarehouseLocation.purpose of the In Transit place


def may(user, action: str) -> bool:
    return user.can(f"stock.{action}")


def _check(request, action: str) -> None:
    if not may(request.user, action):
        raise PermissionDenied("Your role may not do this with stock transfers.")


def _company(request, pk: int):
    company = _visible_company(request, pk)
    if "stock" not in company.modules:
        raise NotFound("This company does not use the Stock module.")
    return company


def _unit_name(unit) -> str:
    return unit.short_name or unit.name


def gstin(branch: Branch) -> str:
    """The GSTIN the branch trades under (its own, else the company's)."""
    return (branch.gstin or branch.company.gstin or "").upper()


def transit_place(branch: Branch) -> WarehouseLocation:
    """The branch's In Transit place, made the first time goods are sent to it.
    It is kept off every picker (not active) and out of the stock a branch can
    use; stock reports still show what sits there."""
    place = WarehouseLocation.objects.filter(
        branch=branch, kind=WarehouseLocation.AREA, purpose=TRANSIT
    ).first()
    if place is not None:
        return place
    name = "In Transit"
    if WarehouseLocation.objects.filter(
        branch=branch, kind=WarehouseLocation.AREA, name__iexact=name
    ).exists():
        name = "In Transit (Transfers)"
    return WarehouseLocation.objects.create(
        branch=branch,
        kind=WarehouseLocation.AREA,
        name=name,
        purpose=TRANSIT,
        is_active=False,
        notes="Goods sent here by stock transfer and not yet received.",
    )


def _factor(item_id: int, unit_id: int) -> Decimal:
    row = ItemUnit.objects.filter(item=item_id, unit=unit_id).first()
    return row.factor if row is not None and row.factor else Decimal("1")


def valued(item: Item) -> bool:
    """Customer-provided goods are never in the books: quantity only."""
    return item.default_request_type != Item.CUSTOMER_PROVIDED


# Reading ---------------------------------------------------------------------


def _transfers(company):
    return StockTransfer.objects.filter(company=company).select_related(
        "company",
        "from_branch__company",
        "from_area",
        "to_branch__company",
        "to_area",
        "transporter",
        "created_by",
        "dispatched_by",
        "received_by",
    )


def _place_name(branch: Branch, area: WarehouseLocation | None) -> str:
    return f"{branch.name} › {area.name}" if area else branch.name


def _bin_out(b: StockTransferBin, factor: Decimal) -> dict:
    return {
        "id": b.pk,
        "location": b.location_id,
        "location_name": b.location.name,
        "batch": b.batch_id,
        "batch_number": b.batch.number if b.batch else "",
        "expiry": b.batch.expiry_date if b.batch else None,
        **package_out(b.package),
        "whole_package": b.whole_package,
        "qty": _plain(b.qty),
        "qty_unit": picking.plain(b.qty / factor),
        "cost": str(b.cost),
        "received_qty": _plain(b.received_qty) if b.received_qty is not None else None,
        "put_location": b.put_location_id,
        "put_location_name": b.put_location.name if b.put_location else "",
    }


def _line_out(ln: StockTransferLine) -> dict:
    factor = _factor(ln.item_id, ln.unit_id)
    bins = list(ln.bins.all())
    picked = sum((b.qty for b in bins), ZERO)
    got = [b.received_qty for b in bins if b.received_qty is not None]
    return {
        "id": ln.pk,
        "position": ln.position,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "item_number": ln.item.item_number,
        "hsn": ln.item.delivery_hsn or ln.item.hsn,
        "unit": ln.unit_id,
        "unit_name": _unit_name(ln.unit),
        "stock_unit_name": _unit_name(ln.item.stock_unit),
        "factor": picking.plain(factor),
        "qty": _plain(ln.qty),
        "picked": picking.plain(picked / factor),
        "short_picked": picked < ln.qty * factor,
        "cost": str(ln.cost),
        "received": picking.plain(sum(got, ZERO) / factor) if got else None,
        "bins": [_bin_out(b, factor) for b in bins],
    }


def transfer_out(t: StockTransfer, lines: bool = True) -> dict:
    data = {
        "id": t.pk,
        "company": t.company_id,
        "number": t.number,
        "status": t.status,
        "status_label": t.get_status_display(),
        "from_branch": t.from_branch_id,
        "from_branch_name": t.from_branch.name,
        "from_area": t.from_area_id,
        "from_name": _place_name(t.from_branch, t.from_area),
        "from_gstin": gstin(t.from_branch),
        "to_branch": t.to_branch_id,
        "to_branch_name": t.to_branch.name,
        "to_area": t.to_area_id,
        "to_name": _place_name(t.to_branch, t.to_area),
        "to_gstin": gstin(t.to_branch),
        "transfer_date": t.transfer_date,
        "expected_date": t.expected_date,
        "transporter": t.transporter_id,
        "transporter_name": t.transporter.name if t.transporter else "",
        "vehicle_no": t.vehicle_no,
        "eway_bill_no": t.eway_bill_no,
        "reason": t.reason,
        "notes": t.notes,
        "value": str(t.value),
        "received_date": t.received_date,
        "shortfall_reason": t.shortfall_reason,
        "shortfall_value": str(t.shortfall_value),
        "cancel_reason": t.cancel_reason,
        "created_by_name": t.created_by.display_name if t.created_by else "",
        "created_at": t.created_at,
        "dispatched_at": t.dispatched_at,
        "dispatched_by_name": t.dispatched_by.display_name if t.dispatched_by else "",
        "received_at": t.received_at,
        "received_by_name": t.received_by.display_name if t.received_by else "",
    }
    if lines:
        rows = t.lines.select_related("item__stock_unit", "unit").prefetch_related(
            "bins__location", "bins__batch", "bins__package", "bins__put_location"
        )
        data["lines"] = [_line_out(ln) for ln in rows]
    else:
        data["items"] = ", ".join(ln.item.name for ln in t.lines.all())
    return data


def _fresh(t: StockTransfer) -> dict:
    return transfer_out(_transfers(t.company).get(pk=t.pk))


def brief(t: StockTransfer) -> dict:
    return {"id": t.pk, "number": t.number, "status": t.status}


# Saving a draft ----------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    unit = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))


class TransferSerializer(serializers.Serializer):
    from_branch = serializers.IntegerField()
    from_area = serializers.IntegerField(required=False, allow_null=True)
    to_branch = serializers.IntegerField()
    to_area = serializers.IntegerField(required=False, allow_null=True)
    transfer_date = serializers.DateField()
    expected_date = serializers.DateField(required=False, allow_null=True)
    transporter = serializers.IntegerField(required=False, allow_null=True)
    vehicle_no = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    eway_bill_no = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True)
    dispatch = serializers.BooleanField(required=False, default=False)


def _branch(company, value, field: str) -> Branch:
    b = Branch.objects.filter(pk=value or 0, company=company, no_stock=False).first()
    if b is None:
        raise ValidationError({field: ["Pick a branch of this company that keeps stock."]})
    return b


def _area(branch: Branch, value, field: str) -> WarehouseLocation | None:
    if not value:
        return None
    a = (
        WarehouseLocation.objects.filter(pk=value, branch=branch, kind=WarehouseLocation.AREA)
        .exclude(purpose=TRANSIT)
        .first()
    )
    if a is None:
        raise ValidationError({field: [f"Pick an area of {branch.name}."]})
    return a


def same_gstin_refusal(a: Branch, b: Branch) -> str:
    if gstin(a) == gstin(b):
        return ""
    return (
        f"{a.name} ({gstin(a) or 'no GSTIN'}) and {b.name} ({gstin(b) or 'no GSTIN'}) have "
        "different GSTINs. A move between them is a sale under GST (a tax invoice and a "
        "matching purchase), not a stock transfer; it cannot be made here yet."
    )


def _save(t: StockTransfer, data: dict) -> None:
    company = t.company
    fb = _branch(company, data["from_branch"], "from_branch")
    tb = _branch(company, data["to_branch"], "to_branch")
    if fb.pk == tb.pk:
        raise ValidationError({"to_branch": ["Pick a different branch to send the goods to."]})
    if text := same_gstin_refusal(fb, tb):
        raise ValidationError({"to_branch": [text]})
    expected = data.get("expected_date")
    if expected and expected < data["transfer_date"]:
        raise ValidationError({"expected_date": ["Expected arrival is before the transfer date."]})
    transporter = None
    if data.get("transporter"):
        transporter = CourierAccount.objects.filter(pk=data["transporter"], company=company).first()
        if transporter is None:
            raise ValidationError({"transporter": ["Pick a transporter from the list."]})
    t.from_branch, t.from_area = fb, _area(fb, data.get("from_area"), "from_area")
    t.to_branch, t.to_area = tb, _area(tb, data.get("to_area"), "to_area")
    t.transfer_date = data["transfer_date"]
    t.expected_date = expected
    t.transporter = transporter
    t.vehicle_no = data.get("vehicle_no", "").strip().upper().replace(" ", "")
    t.eway_bill_no = data.get("eway_bill_no", "").strip().replace(" ", "")
    t.reason = data.get("reason", "").strip()
    t.notes = data.get("notes", "").strip()
    errors, rows = [], []
    if not data["lines"]:
        errors.append("Add at least one item.")
    for k, row in enumerate(data["lines"], start=1):
        item = Item.objects.filter(pk=row["item"], is_active=True).first()
        if item is None:
            errors.append(f"Line {k}: pick an item from the list.")
            continue
        if not item.maintain_stock:
            errors.append(f"Line {k}: {item.name} does not keep stock.")
            continue
        if not valued(item):
            errors.append(
                f"Line {k}: {item.name} is a customer's own goods. A Stock Transfer moves only "
                "our own goods for now."
            )
            continue
        unit = ItemUnit.objects.filter(item=item, unit=row["unit"]).select_related("unit").first()
        if unit is None:
            errors.append(f"Line {k}: pick one of the units of {item.name}.")
            continue
        if unit.whole_numbers and row["qty"] != row["qty"].to_integral_value():
            errors.append(f"Line {k}: {item.name} is counted in whole {_unit_name(unit.unit)}.")
            continue
        rows.append((k, item, unit.unit, row["qty"]))
    if errors:
        raise ValidationError({"lines": errors})
    t.save()
    t.lines.all().delete()
    for k, item, unit, qty in rows:
        StockTransferLine.objects.create(transfer=t, position=k, item=item, unit=unit, qty=qty)
    pick(t)


def pick(t: StockTransfer) -> None:
    """Choose bins and batches for every line by the pick rule, from the From
    Area (or the whole From branch), replacing what the draft had."""
    StockTransferBin.objects.filter(line__transfer=t).delete()
    taken: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
    rows = []
    for ln in t.lines.select_related("item"):
        need = ln.qty * _factor(ln.item_id, ln.unit_id)
        for spot in picking.spots(ln.item, t.from_branch, t.from_area):
            if need <= 0:
                break
            key = (ln.item_id, spot.key)
            free = spot.free - taken[key]
            if free <= 0:
                continue
            take = min(free, need)
            taken[key] += take
            need -= take
            whole = spot.package is not None and take >= spot.package.left_qty
            rows.append(
                StockTransferBin(
                    line=ln,
                    location=spot.location,
                    batch=spot.batch,
                    package=spot.package,
                    whole_package=whole,
                    qty=take,
                )
            )
    StockTransferBin.objects.bulk_create(rows)


# Dispatch ----------------------------------------------------------------------


def _lines(t: StockTransfer) -> list[StockTransferLine]:
    return list(
        t.lines.select_related("item__item_group", "item__stock_unit", "unit").prefetch_related(
            "bins__location", "bins__batch", "bins__package", "bins__put_location"
        )
    )


def problems(t: StockTransfer) -> list[dict]:
    """What stops Dispatch, each with its line: too little free stock to pick."""
    out = []
    if text := same_gstin_refusal(t.from_branch, t.to_branch):
        out.append({"line": None, "text": text})
    for ln in _lines(t):
        factor = _factor(ln.item_id, ln.unit_id)
        picked = sum((b.qty for b in ln.bins.all()), ZERO)
        want = ln.qty * factor
        if picked < want:
            out.append(
                {
                    "line": ln.position,
                    "text": f"Line {ln.position}, {ln.item.name}: only "
                    f"{picking.plain(picked / factor)} {_unit_name(ln.unit)} is free in "
                    f"{_place_name(t.from_branch, t.from_area)}; "
                    f"{picking.plain(ln.qty)} is to go.",
                }
            )
    return out


def _numbered(t: StockTransfer) -> list[tuple[int, Item]]:
    return [(ln.position, ln.item) for ln in _lines(t) if valued(ln.item)]


def refused(t: StockTransfer, user) -> Response | None:
    """Why Dispatch cannot go ahead, answered without raising so a draft just
    saved is kept ("id")."""
    if not may(user, "submit"):
        return None
    if found := attachments.refuse_submit(t, KIND):
        return found
    if found := problems(t):
        return Response(
            {"detail": "This transfer cannot be dispatched yet.", "problems": found, "id": t.pk},
            status=400,
        )
    return None


def _dispatch(t: StockTransfer, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may save drafts but not dispatch them.")
    attachments.require_file(t, KIND)
    pick(t)  # the stock as it is now: another entry may have taken some since
    if found := problems(t):
        raise ValidationError(
            {"detail": "This transfer cannot be dispatched yet.", "problems": found}
        )
    lines = _lines(t)
    t.number = numbering.next_document_number(t.company, NUMBERS, t.transfer_date, t.from_branch)
    transit = transit_place(t.to_branch)
    owners: list[tuple[StockTransferLine, StockTransferBin]] = []
    out: list[StockLine] = []
    for ln in lines:
        for b in ln.bins.all():
            out.append(
                StockLine(ln.item, b.location, -b.qty, batch=b.batch, valued=valued(ln.item))
            )
            owners.append((ln, b))
    sent = service.post(
        Voucher(t.company, t.from_branch, t.transfer_date, KIND, t.pk, t.number, user), stock=out
    )
    into = [
        StockLine(ln.item, transit, b.qty, batch=b.batch, valued=valued(ln.item), value=-value)
        for (ln, b), value in zip(owners, sent.stock_values, strict=True)
    ]
    service.post(
        Voucher(t.company, t.to_branch, t.transfer_date, KIND_IN, t.pk, t.number, user),
        stock=into,
    )
    line_cost: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for (ln, b), value in zip(owners, sent.stock_values, strict=True):
        b.cost = -value
        b.save(update_fields=["cost"])
        line_cost[ln.pk] += -value
        if b.package_id:
            if b.whole_package:
                Package.objects.filter(pk=b.package_id).update(location=transit)
            else:
                _use_package(b.package_id, b.qty)
    for ln in lines:
        ln.cost = line_cost[ln.pk]
        ln.save(update_fields=["cost"])
    t.value = sum(line_cost.values(), ZERO)
    t.status = StockTransfer.IN_TRANSIT
    t.dispatched_at = timezone.now()
    t.dispatched_by = user
    t.save()


# Receive ----------------------------------------------------------------------


class ReceiveRowSerializer(serializers.Serializer):
    bin = serializers.IntegerField()
    received_qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))
    put_location = serializers.IntegerField(required=False, allow_null=True)


class ReceiveSerializer(serializers.Serializer):
    received_date = serializers.DateField()
    shortfall_reason = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    rows = ReceiveRowSerializer(many=True)


def receive_places(t: StockTransfer):
    """Where To can put the goods: its active areas and bins (not racks)."""
    return (
        places_of.places(t.to_branch)
        .filter(is_active=True)
        .exclude(kind=WarehouseLocation.RACK)
        .select_related("parent__parent")
    )


def default_put(t: StockTransfer) -> WarehouseLocation | None:
    """The To Area, else the branch's Receiving area (as for goods receipts), else
    its default store (made now if the branch has none yet)."""
    if t.to_area_id:
        return t.to_area
    sync_default_store(t.to_branch)
    places = WarehouseLocation.objects.filter(branch=t.to_branch, is_active=True)
    return (
        places.filter(kind=WarehouseLocation.AREA, purpose="receiving").order_by("name").first()
        or places.filter(is_default=True).first()
    )


def _transit_lots(t: StockTransfer) -> dict[int, list[int]]:
    """The lots each In Transit move made, by its order among the moves."""
    moves = StockMove.objects.filter(
        voucher_type=KIND_IN, voucher_id=t.pk, is_reversal=False
    ).order_by("id")
    lots = {lot.move_id: lot.pk for lot in StockLot.objects.filter(move__in=moves)}
    return {k: ([lots[m.pk]] if m.pk in lots else []) for k, m in enumerate(moves)}


def _receive(t: StockTransfer, data: dict, user) -> None:
    if not may(user, "submit"):
        raise PermissionDenied("Your role may not receive stock transfers.")
    day = data["received_date"]
    if day < t.transfer_date:
        raise ValidationError(
            {
                "received_date": [
                    f"The goods left on {t.transfer_date:%d-%m-%Y}; they cannot arrive before that."
                ]
            }
        )
    lines = _lines(t)
    bins = [b for ln in lines for b in ln.bins.all()]
    given = {r["bin"]: r for r in data["rows"]}
    fallback = default_put(t)
    places = {p.pk: p for p in receive_places(t)}
    errors = []
    for ln in lines:
        for b in ln.bins.all():
            row = given.get(b.pk)
            got = row["received_qty"] if row else b.qty
            if got > b.qty:
                errors.append(
                    f"Line {ln.position}, {ln.item.name}: {picking.plain(got)} received, more "
                    f"than the {picking.plain(b.qty)} sent from {b.location.name}."
                )
                continue
            put = places.get(row.get("put_location") or 0) if row else None
            if put is None and row and row.get("put_location"):
                errors.append(
                    f"Line {ln.position}, {ln.item.name}: pick a place in {t.to_branch.name}."
                )
                continue
            put = put or fallback
            if got and put is None:
                errors.append(
                    f"Line {ln.position}, {ln.item.name}: pick where in {t.to_branch.name} it goes."
                )
                continue
            b.received_qty, b.put_location = got, put
    if errors:
        raise ValidationError({"rows": errors})
    short = [b for b in bins if b.received_qty < b.qty]
    reason = data.get("shortfall_reason", "").strip()
    if short and not reason:
        raise ValidationError(
            {"shortfall_reason": ["Some goods did not arrive: say why (the transit loss)."]}
        )
    owner = {b.pk: ln for ln in lines for b in ln.bins.all()}
    if short:
        accounts.require_accounts(
            t.company,
            user,
            [(owner[b.pk].position, owner[b.pk].item) for b in short if valued(owner[b.pk].item)],
            needs=(accounts.STOCK,),
        )
    transit = transit_place(t.to_branch)
    lots = _transit_lots(t)
    moves: list[StockLine] = []
    for k, b in enumerate(bins):
        item = owner[b.pk].item
        moves.append(
            StockLine(
                item, transit, -b.qty, batch=b.batch, valued=valued(item), lots=lots.get(k, [])
            )
        )
    puts = [(b, k) for k, b in enumerate(bins) if b.received_qty]  # (bin, its issue's index)

    def gl(values):
        loss: dict[int, Decimal] = defaultdict(lambda: ZERO)
        ledgers = {}
        for k, b in enumerate(bins):
            item = owner[b.pk].item
            if b.received_qty < b.qty and valued(item):
                issued = -values[k]
                kept = _money(issued * b.received_qty / b.qty) if b.received_qty else ZERO
                led = accounts.stock_ledger(t.company, item)
                ledgers[led.pk] = led
                loss[led.pk] += issued - kept
        total = sum(loss.values(), ZERO)
        if not total:
            return []
        adj = accounts.system_ledger(t.company, accounts.STOCK_ADJUSTMENT)
        return [GLLine(adj, debit=total, remarks=f"Transit loss on {t.number}")] + [
            GLLine(ledgers[k], credit=v, remarks=f"Short received on {t.number}")
            for k, v in loss.items()
        ]

    # Each In Transit row leaves at the value it came in with (its own lot is
    # taken first); what arrives goes into the bins at that value, in part
    # when some is short.
    issued = _transit_values(t)
    into = []
    for b, k in puts:
        item = owner[b.pk].item
        value = issued[k]
        kept = value if b.received_qty == b.qty else _money(value * b.received_qty / b.qty)
        into.append(
            StockLine(
                item, b.put_location, b.received_qty, batch=b.batch, valued=valued(item),
                value=kept,
            )
        )  # fmt: skip
    voucher = Voucher(t.company, t.to_branch, day, KIND_RECEIPT, t.pk, t.number, user)
    posted = service.post(voucher, stock=[*moves, *into], gl=gl)
    loss_total = sum((e.debit for e in posted.gl), ZERO)
    for b in bins:
        b.save(update_fields=["received_qty", "put_location"])
        if b.package_id and b.whole_package:
            Package.objects.filter(pk=b.package_id).update(location=b.put_location or transit)
            if b.received_qty < b.qty:
                _use_package(b.package_id, b.qty - b.received_qty)
    t.received_date = day
    t.shortfall_reason = reason if short else ""
    t.shortfall_value = loss_total
    t.status = StockTransfer.RECEIVED
    t.received_at = timezone.now()
    t.received_by = user
    t.save()


def _transit_values(t: StockTransfer) -> list[Decimal]:
    """What each In Transit row is worth: the value it was put there with."""
    rows = StockMove.objects.filter(voucher_type=KIND_IN, voucher_id=t.pk, is_reversal=False)
    return [m.value for m in rows.order_by("id")]


# Cancel -----------------------------------------------------------------------


def _cancel(t: StockTransfer, user, reason: str) -> None:
    if t.status == StockTransfer.RECEIVED:
        raise ValidationError(
            {
                "detail": f"{t.number} has been received at {t.to_branch.name}. Send the goods "
                "back on a new transfer instead."
            }
        )
    if t.status == StockTransfer.IN_TRANSIT:
        service.cancel(KIND_IN, t.pk, user)
        service.cancel(KIND, t.pk, user)
        for b in StockTransferBin.objects.filter(line__transfer=t).exclude(package=None):
            if b.whole_package:
                Package.objects.filter(pk=b.package_id).update(location=b.location)
            else:
                _use_package(b.package_id, -b.qty)
    t.status = StockTransfer.CANCELLED
    t.cancel_reason = reason[:200]
    t.save()


# The "Stock Posting" section ---------------------------------------------------


def _bins_text(bins) -> str:
    return ", ".join(dict.fromkeys(b.location.name for b in bins)) or "the bins picked"


def stock_posting(t: StockTransfer) -> dict:
    """Two steps, each with what moves in the stock ledger and the books: what
    will happen on a draft, what did once done."""
    lines = _lines(t)
    bins = [b for ln in lines for b in ln.bins.all()]
    to_transit = f"{t.to_branch.name} › In Transit"
    dispatch = {
        "step": "Dispatch",
        "done": t.status in (StockTransfer.IN_TRANSIT, StockTransfer.RECEIVED),
        "stock": f"Out of {t.from_branch.name} › {_bins_text(bins)}, into {to_transit} at the "
        "same FIFO lot rates",
        "books": "Nothing: the goods stay in the company's own Stock Ledger. Branch-wise stock "
        "value still shows where they are.",
        "value": str(t.value) if t.value else "",
    }
    if t.status == StockTransfer.RECEIVED:
        puts = [b.put_location for b in bins if b.received_qty and b.put_location]
        into = ", ".join(dict.fromkeys(p.name for p in puts)) or "-"
        receive_stock = f"Out of {to_transit}, into {t.to_branch.name} › {into}"
        rows = posting_api.posted(KIND_RECEIPT, t.pk)["rows"]
        books = (
            "Transit loss: "
            + "; ".join(
                f"{'Dr' if r['debit'] != '0.00' else 'Cr'} {r['ledger_name']} "
                f"₹{r['debit'] if r['debit'] != '0.00' else r['credit']}"
                for r in rows
            )
            if rows
            else "Nothing: everything sent arrived."
        )
    else:
        receive_stock = f"Out of {to_transit}, into the places picked on receipt"
        books = "Nothing, unless less arrives: the shortfall goes Dr Stock Adjustment, Cr Stock."
    receive = {
        "step": "Receive",
        "done": t.status == StockTransfer.RECEIVED,
        "stock": receive_stock,
        "books": books,
        "value": str(t.shortfall_value) if t.shortfall_value else "",
    }
    return {
        "steps": [dispatch, receive],
        "cancelled": t.status == StockTransfer.CANCELLED,
    }


# Views -----------------------------------------------------------------------


def _transfer(request, pk: int, lock: bool = False) -> StockTransfer:
    rows = StockTransfer.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    t = rows.select_related(
        "company", "from_branch__company", "to_branch__company", "from_area", "to_area"
    ).first()
    if t is None or "stock" not in t.company.modules:
        raise NotFound("No such stock transfer.")
    return t


VIEWS = (
    StockTransfer.DRAFT,
    StockTransfer.IN_TRANSIT,
    StockTransfer.RECEIVED,
    StockTransfer.CANCELLED,
)


class TransferListView(APIView):
    """GET ?view=draft|in_transit|received|cancelled|all&q=text&branch=ID: the
    company's transfers (branch: from or to it). POST: a new draft (with
    "dispatch": true, dispatched at once)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        company = _company(request, pk)
        rows = _transfers(company).prefetch_related("lines__item")
        view = request.query_params.get("view", "all")
        if view in VIEWS:
            rows = rows.filter(status=view)
        if branch := request.query_params.get("branch"):
            rows = rows.filter(Q(from_branch=branch) | Q(to_branch=branch))
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(from_branch__name__icontains=word)
                | Q(to_branch__name__icontains=word)
                | Q(lines__item__name__icontains=word)
            ).distinct()
        return Response([transfer_out(t, lines=False) for t in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "create")
        company = _company(request, pk)
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        t = StockTransfer(company=company, created_by=request.user)
        _save(t, data)
        if data.get("dispatch"):
            if answer := refused(t, request.user):
                return answer
            _dispatch(t, request.user)
        return Response(_fresh(t), status=status.HTTP_201_CREATED)


class TransferDetailView(APIView):
    """GET one transfer; PATCH a draft (with "dispatch": true, also dispatch it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(_fresh(_transfer(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, "create")
        t = _transfer(request, pk, lock=True)
        if t.status != StockTransfer.DRAFT:
            raise ValidationError(
                {"detail": "A dispatched transfer cannot be changed. Cancel it and make a new one."}
            )
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(t, data)
        if data.get("dispatch"):
            if answer := refused(t, request.user):
                return answer
            _dispatch(t, request.user)
        return Response(_fresh(t))


class TransferDispatchView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        t = _transfer(request, pk, lock=True)
        if t.status != StockTransfer.DRAFT:
            raise ValidationError({"detail": "This transfer is not a draft."})
        if answer := refused(t, request.user):
            return answer
        _dispatch(t, request.user)
        return Response(_fresh(t))


class TransferReceiveView(APIView):
    """GET: where the goods may be put at To, and the default place. POST
    {received_date, shortfall_reason, rows: [{bin, received_qty, put_location}]}."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        t = _transfer(request, pk)
        put = default_put(t)
        return Response(
            {
                "default": put.pk if put else None,
                "places": [
                    {
                        "id": p.pk,
                        "label": _location_label(p),
                        "kind": p.kind,
                    }
                    for p in receive_places(t)
                ],
            }
        )

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        t = _transfer(request, pk, lock=True)
        if t.status != StockTransfer.IN_TRANSIT:
            raise ValidationError({"detail": "Only a transfer in transit can be received."})
        serializer = ReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _receive(t, dict(serializer.validated_data), request.user)
        return Response(_fresh(t))


def _location_label(p: WarehouseLocation) -> str:
    if p.kind == WarehouseLocation.BIN and p.parent is not None:
        area = p.parent.parent
        rack = f"{p.parent.name} › {p.name}"
        return f"{area.name} › {rack}" if area else rack
    return p.name


class TransferCancelView(APIView):
    """POST {reason}: a draft is dropped; one in transit goes back to its bins."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "cancel")
        t = _transfer(request, pk, lock=True)
        if t.status == StockTransfer.CANCELLED:
            raise ValidationError({"detail": "This transfer is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(t, request.user, reason)
        return Response(_fresh(t))


class TransferPostingView(APIView):
    """GET: the "Stock Posting" section."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        return Response(stock_posting(_transfer(request, pk)))


class TransferFormView(APIView):
    """GET ?branch=ID&area=ID: what the form needs: the stock branches and their
    areas (with GSTIN), the transporters, and the stock items with their units
    and what is free at the From place (in the stock unit)."""

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
        branch = next(
            (b for b in branches if str(b.pk) == request.query_params.get("branch")), None
        )
        area = None
        if branch is not None and request.query_params.get("area"):
            area = next(
                (
                    a
                    for a in areas
                    if a.branch_id == branch.pk and str(a.pk) == request.query_params["area"]
                ),
                None,
            )
        items = list(
            picked(
                Item.objects.filter(is_active=True, maintain_stock=True).exclude(
                    default_request_type=Item.CUSTOMER_PROVIDED
                ),
                request.query_params,
            )
            .select_related("stock_unit")
            .prefetch_related("units__unit")
            .order_by("name")
        )
        held = free_at(items, branch, area) if branch else {}
        return Response(
            {
                "branches": [
                    {
                        "id": b.pk,
                        "name": b.name,
                        "gstin": gstin(b),
                        "is_active": b.is_active,
                        "areas": [
                            {"id": a.pk, "name": a.name, "is_active": a.is_active}
                            for a in areas
                            if a.branch_id == b.pk
                        ],
                    }
                    for b in branches
                ],
                "transporters": [
                    {"id": c.pk, "name": c.name}
                    for c in CourierAccount.objects.filter(company=company, is_active=True)
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
                        "in_stock": _plain(held.get(i.pk, ZERO)) if branch else None,
                    }
                    for i in items
                ],
            }
        )


def free_at(items, branch: Branch, area) -> dict[int, Decimal]:
    """What each item has at the place less what open pick lists keep aside."""
    have = places_of.on_hand(items, branch, area)
    kept = (
        PickListLine.objects.filter(
            item__in=items,
            pick_list__status__in=PickList.HOLDING,
            location__in=places_of.places(branch, area),
        )
        .values("item")
        .annotate(q=Sum("qty"))
    )
    for r in kept:
        have[r["item"]] = have.get(r["item"], ZERO) - (r["q"] or ZERO)
    return have


class TransferPdfView(APIView):
    """GET (&download=1): the Delivery Challan for the goods on the road (not for
    sale: a branch transfer), with HSN, quantity and value at cost."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from core import printout

        _check(request, "view")
        t = _transfer(request, pk)
        data = _fresh(t)
        scope = " · ".join(
            x
            for x in [
                f"From {data['from_name']} (GSTIN {data['from_gstin']})"
                if data["from_gstin"]
                else f"From {data['from_name']}",
                f"To {data['to_name']}",
                data["transfer_date"].strftime("%d-%m-%Y"),
                data["transporter_name"],
                data["vehicle_no"] and f"Vehicle {data['vehicle_no']}",
                data["eway_bill_no"] and f"E-way bill {data['eway_bill_no']}",
                "Not for sale: branch transfer",
            ]
            if x
        )
        rows = [
            [
                str(ln["position"]),
                ln["item_name"],
                ln["hsn"],
                f"{ln['qty']} {ln['unit_name']}",
                "; ".join(
                    b["location_name"] + (f" · {b['batch_number']}" if b["batch_number"] else "")
                    for b in ln["bins"]
                ),
                ln["cost"] if t.status != StockTransfer.DRAFT else "",
            ]
            for ln in data["lines"]
        ]
        if t.status != StockTransfer.DRAFT:
            rows.append(["", "Total", "", "", "", data["value"]])
        sheet = {
            "title": "",
            "columns": ["#", "Item", "HSN", "Qty", "Taken From", "Value at Cost ₹"],
            "rows": rows,
            "text": [2],
        }
        title = f"Delivery Challan {data['number'] or 'Draft'}"
        response = printout.pdf_response(title, scope, [sheet], data["number"] or "stock-transfer")
        if request.query_params.get("download") != "1":
            response["Content-Disposition"] = response["Content-Disposition"].replace(
                "attachment", "inline"
            )
        return response
