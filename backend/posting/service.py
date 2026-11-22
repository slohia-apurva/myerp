"""The one posting service (design rule 10). Every document that touches the
books calls `post` when it is submitted and `cancel` when it is cancelled;
nothing else writes GL entries or stock moves.

    result = post(voucher, stock=[StockLine(...)], gl=lambda values: [GLLine(...)])

Stock lines go first, because an issue's value is only known once its FIFO
lots are used; `gl` may be a function that receives those values (one per
stock line, signed) and returns the GL lines. The GL lines must balance.

Checks made here, for every document:
* the date is in an open month of a fiscal year (rule 7);
* GL: each line is a debit or a credit to an active ledger of the company,
  and the voucher balances (the database checks this again at commit);
* stock: quantity never goes below zero at a place and batch, on the entry's
  own date or on any later date (a backdated issue is checked against what
  later entries already took); a batch-tracked item names its batch (of that
  item); the place is in the voucher's branch;
* one posting or cancel at a time per item and branch: each takes a
  transaction lock on its items first, so two people issuing the same stock
  at the same moment cannot both pass the checks;
* FIFO (decision 0002): an issue uses the oldest lots of the item in the
  branch dated on or before it. A valued entry dated before a later issue of
  the same item and branch is refused for now, because it would change that
  issue's cost (the background repost of rule 8 is not built yet).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import connections
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from core import fiscal
from core.models import Batch, Branch, Company, Item, Ledger, WarehouseLocation
from posting.models import GLEntry, StockLot, StockLotUse, StockMove, StockRevaluation
from tenancy.context import require_tenant, tenant_atomic

PAISA = Decimal("0.01")
ZERO = Decimal("0")


def money(value) -> Decimal:
    """The one rounding rule for rupees (rule 5): half up to the paisa."""
    return Decimal(value).quantize(PAISA, rounding=ROUND_HALF_UP)


@dataclass
class Voucher:
    company: Company
    branch: Branch
    date: date
    type: str  # e.g. "goods_receipt"
    id: int
    number: str
    user: object = None  # the person submitting or cancelling


@dataclass
class GLLine:
    ledger: Ledger
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    remarks: str = ""


@dataclass
class StockLine:
    """`qty` is signed: + into the place, - out of it. A receipt gives its
    `rate`; an issue's rate comes from its FIFO lots. `valued=False` for goods
    that are not ours (customer-provided material): quantity only."""

    item: Item
    location: WarehouseLocation
    qty: Decimal
    rate: Decimal | None = None
    batch: Batch | None = None
    valued: bool = True
    # An issue that takes these lots first (goods sent back to the supplier go
    # out of the receipt's own lots); FIFO for any rest.
    lots: Sequence[int] = ()
    # A receipt that carries stock over at the value it left with (a stock
    # transfer): that value exactly, so no paisa is lost to the rate's rounding.
    value: Decimal | None = None


@dataclass
class Revalue:
    """Change the value of what is left of a lot, with no change in quantity
    (a bill at a different rate than the receipt). `value` is signed rupees."""

    lot: StockLot
    value: Decimal


@dataclass
class Posted:
    stock_values: list[Decimal] = field(default_factory=list)  # one per stock line, signed
    gl: list[GLEntry] = field(default_factory=list)
    stock: list[StockMove] = field(default_factory=list)


def _refuse(message: str, key: str = "detail"):
    raise ValidationError({key: [message]})


def _common(voucher: Voucher, user) -> dict:
    return {
        "voucher_type": voucher.type,
        "voucher_id": voucher.id,
        "voucher_no": voucher.number,
        "created_by": user,
    }


def _rows(voucher_type: str, voucher_id: int):
    return (
        GLEntry.objects.filter(voucher_type=voucher_type, voucher_id=voucher_id),
        StockMove.objects.filter(voucher_type=voucher_type, voucher_id=voucher_id),
    )


def is_posted(voucher_type: str, voucher_id: int) -> bool:
    gl, stock = _rows(voucher_type, voucher_id)
    return gl.exists() or stock.exists()


# Quantities


def on_hand(item: Item, location: WarehouseLocation, batch: Batch | None = None) -> Decimal:
    """Quantity of the item at the place (and batch, for a batch-tracked item)."""
    rows = StockMove.objects.filter(item=item, location=location, batch=batch)
    return rows.aggregate(q=Sum("qty"))["q"] or ZERO


def available(
    item: Item, location: WarehouseLocation, batch: Batch | None, on: date
) -> tuple[Decimal, Decimal, date | None]:
    """How much can leave the place on that day without the place going below
    zero then or on any later day. Returns (held that day, can leave, the later
    day that limits it or None)."""
    rows = StockMove.objects.filter(item=item, location=location, batch=batch)
    held = rows.filter(date__lte=on).aggregate(q=Sum("qty"))["q"] or ZERO
    low, low_day, run = held, None, held
    later = rows.filter(date__gt=on).values("date").annotate(q=Sum("qty")).order_by("date")
    for day in later:
        run += day["q"]
        if run < low:
            low, low_day = run, day["date"]
    return held, low, low_day


def _lock_stock(keys) -> None:
    """Hold a transaction lock per (item, branch) until commit, taken in one
    order so two postings cannot deadlock. Everything that reads stock to
    decide whether it may leave runs after this."""
    alias = require_tenant().db_alias
    with connections[alias].cursor() as cursor:
        for item_id, branch_id in sorted(set(keys)):
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s, %s)",
                [item_id % 2147483647, branch_id % 2147483647],
            )


def _where(location: WarehouseLocation, batch: Batch | None) -> str:
    return f"{location}" + (f", batch {batch.number}" if batch else "")


def _check_place(voucher: Voucher, line: StockLine) -> None:
    item, loc = line.item, line.location
    if loc.branch_id != voucher.branch.pk:
        _refuse(f"{loc} is not in {voucher.branch}.", "location")
    if loc.kind == WarehouseLocation.RACK:
        _refuse(f"{loc} is a rack: put the stock in one of its bins.", "location")
    if not item.maintain_stock:
        _refuse(f"{item.name} does not keep stock.", "item")
    if item.batch_tracked and line.batch is None:
        _refuse(f"{item.name} keeps batches: give the batch.", "batch")
    if not item.batch_tracked and line.batch is not None:
        _refuse(f"{item.name} does not keep batches.", "batch")
    if line.batch is not None and line.batch.item_id != item.pk:
        _refuse(f"Batch {line.batch.number} is not a batch of {item.name}.", "batch")
    if line.qty == 0:
        _refuse(f"The quantity of {item.name} cannot be 0.", "qty")


def _check_not_before_issues(voucher: Voucher, item: Item) -> None:
    later = StockMove.objects.filter(
        company=voucher.company,
        branch=voucher.branch,
        item=item,
        valued=True,
        qty__lt=0,
        date__gt=voucher.date,
    )
    if later.exists():
        last = later.order_by("-date").first()
        _refuse(
            f"{item.name} has already been issued on {last.date:%d-%m-%Y} in "
            f"{voucher.branch}. An entry dated before that would change that issue's cost; "
            "date it on or after that day."
        )


def _receive(voucher: Voucher, line: StockLine, common: dict) -> tuple[StockMove, Decimal]:
    if line.valued and line.value is not None:
        if line.value < 0:
            _refuse(f"The value of {line.item.name} cannot be below nil.", "rate")
        _check_not_before_issues(voucher, line.item)
        value = money(line.value)
        rate = (value / line.qty).quantize(Decimal("0.000001"))
    else:
        if line.valued:
            if line.rate is None or line.rate < 0:
                _refuse(f"Give the rate of {line.item.name}.", "rate")
            _check_not_before_issues(voucher, line.item)
        rate = line.rate if line.valued else ZERO
        value = money(line.qty * rate) if line.valued else ZERO
    move = StockMove.objects.create(
        company=voucher.company,
        branch=voucher.branch,
        location=line.location,
        item=line.item,
        batch=line.batch,
        date=voucher.date,
        qty=line.qty,
        rate=rate,
        value=value,
        valued=line.valued,
        **common,
    )
    if line.valued:
        StockLot.objects.create(
            company=voucher.company,
            branch=voucher.branch,
            item=line.item,
            date=voucher.date,
            rate=rate,
            qty_in=line.qty,
            value_in=value,
            qty_left=line.qty,
            value_left=value,
            move=move,
        )
    return move, value


def _issue(voucher: Voucher, line: StockLine, common: dict) -> tuple[StockMove, Decimal]:
    want = -line.qty
    held, can, limit = available(line.item, line.location, line.batch, voucher.date)
    where = _where(line.location, line.batch)
    if held < want:
        _refuse(
            f"Only {held.normalize():f} of {line.item.name} is at {where} on "
            f"{voucher.date:%d-%m-%Y}; {want.normalize():f} is wanted.",
            "qty",
        )
    if can < want:
        _refuse(
            f"{line.item.name} at {where} is already taken by later entries: on "
            f"{limit:%d-%m-%Y} only {max(can, ZERO).normalize():f} would be left for this "
            f"entry, and {want.normalize():f} is wanted. Date this entry on or after the "
            "stock came in for it, or cancel the later entries first.",
            "qty",
        )
    value = ZERO
    uses = []
    if line.valued:
        _check_not_before_issues(voucher, line.item)
        lots = (
            StockLot.objects.select_for_update()
            .filter(
                company=voucher.company,
                branch=voucher.branch,
                item=line.item,
                qty_left__gt=0,
                date__lte=voucher.date,
            )
            .order_by("date", "id")
        )
        if line.lots:
            first = set(line.lots)
            lots = sorted(lots, key=lambda lot: lot.pk not in first)
        left = want
        for lot in lots:
            if left <= 0:
                break
            take = min(left, lot.qty_left)
            # The last of a lot takes exactly what value it has left, so no paisa is lost.
            part = lot.value_left if take == lot.qty_left else money(take * lot.rate)
            lot.qty_left -= take
            lot.value_left -= part
            lot.save(update_fields=["qty_left", "value_left"])
            uses.append((lot, take, part))
            value += part
            left -= take
        if left > 0:
            _refuse(
                f"There is not enough valued stock of {line.item.name} in {voucher.branch} "
                f"on {voucher.date:%d-%m-%Y} to cost this issue.",
                "qty",
            )
    move = StockMove.objects.create(
        company=voucher.company,
        branch=voucher.branch,
        location=line.location,
        item=line.item,
        batch=line.batch,
        date=voucher.date,
        qty=line.qty,
        rate=(value / want).quantize(Decimal("0.000001")) if line.valued else ZERO,
        value=-value,
        valued=line.valued,
        **common,
    )
    StockLotUse.objects.bulk_create(
        [StockLotUse(move=move, lot=lot, qty=q, value=v) for lot, q, v in uses]
    )
    return move, -value


# GL


def _check_gl(voucher: Voucher, lines: Sequence[GLLine]) -> list[GLLine]:
    kept = []
    for line in lines:
        debit, credit = money(line.debit or 0), money(line.credit or 0)
        if debit < 0 or credit < 0:
            _refuse("A GL line cannot be negative; use the other side.")
        if debit and credit:
            _refuse(f"A GL line to {line.ledger} is either a debit or a credit, not both.")
        if not debit and not credit:
            continue  # a nil line (no charges, say) posts nothing
        if line.ledger.company_id != voucher.company.pk:
            _refuse(f"{line.ledger} is not a ledger of {voucher.company}.")
        if not line.ledger.is_active:
            _refuse(f"{line.ledger} is disabled.")
        kept.append(GLLine(line.ledger, debit, credit, line.remarks))
    dr = sum((x.debit for x in kept), ZERO)
    cr = sum((x.credit for x in kept), ZERO)
    if dr != cr:
        _refuse(f"The entry does not balance: debits {dr}, credits {cr}.")
    return kept


def post(
    voucher: Voucher,
    stock: Sequence[StockLine] = (),
    gl: Sequence[GLLine] | Callable[[list[Decimal]], Sequence[GLLine]] = (),
    revalue: Sequence[Revalue] = (),
) -> Posted:
    """Write a submitted document's stock moves and GL entries. Call it inside
    the document's `tenant_atomic()` so a refusal leaves nothing behind."""
    with tenant_atomic():
        return _post(voucher, stock, gl, revalue)


def _post(voucher, stock, gl, revalue) -> Posted:
    fiscal.assert_open(voucher.company, voucher.date)
    if voucher.branch.company_id != voucher.company.pk:
        _refuse(f"{voucher.branch} is not a branch of {voucher.company}.")
    if is_posted(voucher.type, voucher.id):
        _refuse(f"{voucher.number} has already been posted.")
    _lock_stock((line.item.pk, voucher.branch.pk) for line in stock)
    common = _common(voucher, voucher.user)
    out = Posted()
    for line in stock:
        _check_place(voucher, line)
        move, value = (_receive if line.qty > 0 else _issue)(voucher, line, common)
        out.stock.append(move)
        out.stock_values.append(value)
    revalued = [_revalue(voucher, r, common) for r in revalue if money(r.value)]
    lines = _check_gl(voucher, gl(out.stock_values) if callable(gl) else gl)
    out.gl = GLEntry.objects.bulk_create(
        [
            GLEntry(
                company=voucher.company,
                branch=voucher.branch,
                date=voucher.date,
                ledger=x.ledger,
                debit=x.debit,
                credit=x.credit,
                remarks=x.remarks,
                **common,
            )
            for x in lines
        ]
    )
    if not out.gl and not out.stock and not revalued:
        _refuse(f"{voucher.number} has nothing to post.")
    return out


def _revalue(voucher: Voucher, r: Revalue, common: dict) -> StockRevaluation:
    lot = StockLot.objects.select_for_update().get(pk=r.lot.pk)
    value = money(r.value)
    if lot.company_id != voucher.company.pk or lot.branch_id != voucher.branch.pk:
        _refuse("Stock of another branch cannot be revalued here.")
    if lot.qty_left <= 0:
        _refuse(f"No stock is left in the lot of {lot.item} to revalue.")
    if lot.value_left + value < 0:
        _refuse(f"The stock of {lot.item} cannot be valued below nil.")
    lot.value_left += value
    lot.rate = (lot.value_left / lot.qty_left).quantize(Decimal("0.000001"))
    lot.save(update_fields=["value_left", "rate"])
    return StockRevaluation.objects.create(
        company=voucher.company,
        branch=voucher.branch,
        item_id=lot.item_id,
        lot=lot,
        date=voucher.date,
        value=value,
        qty_left=lot.qty_left,
        **common,
    )


def cancel(voucher_type: str, voucher_id: int, user=None) -> None:
    """Reverse everything a document posted, on its own date (rule 2). Refused
    if its month is locked, if it was cancelled already, or if stock it
    brought in has since been used, or would leave too little for a later entry."""
    with tenant_atomic():
        _cancel(voucher_type, voucher_id, user)


def _cancel(voucher_type: str, voucher_id: int, user=None) -> None:
    gl, stock = _rows(voucher_type, voucher_id)
    originals_gl = list(gl.filter(is_reversal=False))
    originals_stock = list(stock.filter(is_reversal=False).select_related("item", "location"))
    first = (originals_gl or originals_stock or [None])[0]
    if first is None:
        _refuse("This entry has not been posted.")
    if gl.filter(is_reversal=True).exists() or stock.filter(is_reversal=True).exists():
        _refuse(f"{first.voucher_no} has already been cancelled.")
    company = first.company
    fiscal.assert_open(company, first.date)
    common = {
        "voucher_type": voucher_type,
        "voucher_id": voucher_id,
        "voucher_no": first.voucher_no,
        "created_by": user,
        "is_reversal": True,
    }
    _lock_stock((m.item_id, m.branch_id) for m in originals_stock)
    taking: dict[tuple, Decimal] = {}  # what earlier lines of this cancel already take back
    for move in originals_stock:
        if move.qty > 0:
            key = (move.item_id, move.location_id, move.batch_id, move.date)
            taking[key] = taking.get(key, ZERO) + move.qty
            _, can, _ = available(move.item, move.location, move.batch, move.date)
            if can < taking[key]:
                _refuse(
                    f"{move.item.name} received by {move.voucher_no} has since been moved or "
                    "used; cancel those entries first.",
                )
            if move.valued:
                lot = StockLot.objects.select_for_update().get(move=move)
                if lot.qty_left != lot.qty_in:
                    _refuse(
                        f"{move.item.name} received by {move.voucher_no} has since been "
                        "issued; cancel those entries first.",
                    )
                lot.qty_left, lot.value_left = ZERO, ZERO
                lot.save(update_fields=["qty_left", "value_left"])
        else:
            for use in move.lot_uses.select_related("lot"):
                lot = StockLot.objects.select_for_update().get(pk=use.lot_id)
                lot.qty_left += use.qty
                lot.value_left += use.value
                lot.save(update_fields=["qty_left", "value_left"])
    revalued = StockRevaluation.objects.filter(
        voucher_type=voucher_type, voucher_id=voucher_id, is_reversal=False
    )
    for rv in revalued:
        lot = StockLot.objects.select_for_update().get(pk=rv.lot_id)
        if lot.qty_left != rv.qty_left:
            _refuse(
                f"{lot.item} revalued by {rv.voucher_no} has since been issued; "
                "cancel those entries first."
            )
        lot.value_left -= rv.value
        if lot.qty_left:
            lot.rate = (lot.value_left / lot.qty_left).quantize(Decimal("0.000001"))
        lot.save(update_fields=["value_left", "rate"])
        StockRevaluation.objects.create(
            company=rv.company,
            branch=rv.branch,
            item=rv.item,
            lot=lot,
            date=rv.date,
            value=-rv.value,
            qty_left=lot.qty_left,
            **common,
        )
    StockMove.objects.bulk_create(
        [
            StockMove(
                company=m.company,
                branch=m.branch,
                location=m.location,
                item=m.item,
                batch=m.batch,
                date=m.date,
                qty=-m.qty,
                rate=m.rate,
                value=-m.value,
                valued=m.valued,
                **common,
            )
            for m in originals_stock
        ]
    )
    GLEntry.objects.bulk_create(
        [
            GLEntry(
                company=e.company,
                branch=e.branch,
                date=e.date,
                ledger=e.ledger,
                debit=e.credit,
                credit=e.debit,
                remarks=e.remarks,
                **common,
            )
            for e in originals_gl
        ]
    )


# Reading


def gl_balance(ledger: Ledger, upto: date | None = None) -> Decimal:
    """Debit positive: the opening balance plus every GL entry up to the date."""
    rows = GLEntry.objects.filter(ledger=ledger)
    if upto is not None:
        rows = rows.filter(date__lte=upto)
    sums = rows.aggregate(d=Sum("debit"), c=Sum("credit"))
    return ledger.opening_signed + (sums["d"] or ZERO) - (sums["c"] or ZERO)


def stock_value(company: Company, item: Item | None = None, branch: Branch | None = None):
    """Rupee value of stock on hand, from the stock ledger."""
    rows = StockMove.objects.filter(company=company, valued=True)
    if item is not None:
        rows = rows.filter(item=item)
    if branch is not None:
        rows = rows.filter(branch=branch)
    revalued = StockRevaluation.objects.filter(company=company)
    if item is not None:
        revalued = revalued.filter(item=item)
    if branch is not None:
        revalued = revalued.filter(branch=branch)
    return (rows.aggregate(v=Sum("value"))["v"] or ZERO) + (
        revalued.aggregate(v=Sum("value"))["v"] or ZERO
    )
