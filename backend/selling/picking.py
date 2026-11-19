"""Choosing bins and batches for a sales order (Sidharth, 2026-11-19, preview 6).

The rule, approved with the previews:
- only places in the order's Despatch From (the area and the racks and bins in
  it, or the whole branch);
- earliest expiry first, then oldest received (a batch with no expiry comes
  after those with one);
- a batch held back (Quarantine or Rejected) is never picked;
- stock already on an open or picked pick list is kept aside.

Quantities here are in the item's stock unit.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Min, Q, Sum

from core import numbering
from core.models import Batch, Item, ItemUnit, WarehouseLocation
from posting.models import StockMove
from selling import stock
from selling.models import PickList, PickListLine, SalesOrder, SalesOrderLine

ZERO = Decimal("0")
FAR = datetime.date(9999, 12, 31)
HELD = (Batch.QUARANTINE, Batch.REJECTED)


@dataclass
class Spot:
    """Stock of one item in one place and batch that may be picked."""

    location: WarehouseLocation
    batch: Batch | None
    free: Decimal
    received: datetime.date | None

    @property
    def key(self) -> tuple[int, int | None]:
        return (self.location.pk, self.batch.pk if self.batch else None)

    @property
    def expiry(self) -> datetime.date | None:
        return self.batch.expiry_date if self.batch else None

    def order(self):
        return (
            self.expiry is None,
            self.expiry or FAR,
            self.received or FAR,
            self.location.name.lower(),
            self.batch.number.lower() if self.batch else "",
        )


def factor(line: SalesOrderLine) -> Decimal:
    """Stock units in one of the line's units."""
    row = ItemUnit.objects.filter(item=line.item_id, unit=line.unit_id).first()
    return row.factor if row is not None and row.factor else Decimal("1")


def pending(line: SalesOrderLine) -> Decimal:
    """What is still to go on the line, in its own unit."""
    if line.closed_at:
        return ZERO
    return max(line.qty - line.delivered_qty, ZERO)


def spots(item: Item, branch, area=None, leave_out: PickList | None = None) -> list[Spot]:
    """Where the item may be picked from, in the order the rule picks them."""
    rows = (
        StockMove.objects.filter(item=item, location__in=stock.places(branch, area))
        .values("location", "batch")
        .annotate(q=Sum("qty"), first=Min("date", filter=Q(qty__gt=0)))
    )
    held = PickListLine.objects.filter(item=item, pick_list__status__in=PickList.HOLDING)
    if leave_out is not None:
        held = held.exclude(pick_list=leave_out)
    kept = {
        (r["location"], r["batch"]): r["q"]
        for r in held.values("location", "batch").annotate(q=Sum("qty"))
    }
    places = {
        p.pk: p for p in WarehouseLocation.objects.filter(pk__in={r["location"] for r in rows})
    }
    batches = {b.pk: b for b in Batch.objects.filter(pk__in={r["batch"] for r in rows} - {None})}
    out = []
    for r in rows:
        batch = batches.get(r["batch"]) if r["batch"] else None
        if batch is not None and batch.status in HELD:
            continue
        free = (r["q"] or ZERO) - kept.get((r["location"], r["batch"]), ZERO)
        if free > 0:
            out.append(Spot(places[r["location"]], batch, free, r["first"]))
    return sorted(out, key=Spot.order)


def stock_lines(order: SalesOrder) -> list[SalesOrderLine]:
    """The order's lines the stores pick: stock items with something to go."""
    return [
        ln
        for ln in order.lines.select_related("item", "unit")
        if ln.item.maintain_stock and pending(ln) > 0
    ]


def make(order: SalesOrder, user) -> PickList | None:
    """A new open pick list for what is still to go on the order, with bins and
    batches chosen by the rule. None when no line holds a stock item."""
    lines = stock_lines(order)
    if not lines:
        return None
    pick = PickList.objects.create(
        company=order.company,
        order=order,
        branch=order.branch,
        area=order.area,
        number=numbering.next_document_number(
            order.company, "pick_list", order.order_date, order.branch
        ),
        created_by=user,
    )
    taken: dict[tuple[int, tuple], Decimal] = {}
    rows = []
    for ln in lines:
        need = pending(ln) * factor(ln)
        for spot in spots(ln.item, order.branch, order.area):
            if need <= 0:
                break
            mine = (ln.item_id, spot.key)
            left = spot.free - taken.get(mine, ZERO)
            if left <= 0:
                continue
            take = min(left, need)
            taken[mine] = taken.get(mine, ZERO) + take
            need -= take
            rows.append(
                PickListLine(
                    pick_list=pick,
                    order_line=ln,
                    position=ln.position,
                    item=ln.item,
                    location=spot.location,
                    batch=spot.batch,
                    qty=take,
                )
            )
    PickListLine.objects.bulk_create(rows)
    return pick


def plain(n: Decimal) -> str:
    n = n.quantize(Decimal("0.001")).normalize()
    return f"{n:f}"


def summary(pick: PickList) -> dict:
    """Per order line: ordered, picked and short (in the line's unit and the
    stock unit), and the sentence the order and the list show."""
    rows = list(pick.lines.select_related("location", "batch"))
    items = []
    for ln in stock_lines_of(pick):
        f = factor(ln)
        want = pending(ln) * f
        got = sum((r.qty for r in rows if r.order_line_id == ln.pk), ZERO)
        short = max(want - got, ZERO)
        stock_name = ln.item.stock_unit.short_name or ln.item.stock_unit.name
        unit_name = ln.unit.short_name or ln.unit.name
        items.append(
            {
                "line": ln,
                "factor": f,
                "want": want,
                "got": got,
                "short": short,
                "unit_name": unit_name,
                "stock_unit_name": stock_name,
                "rows": [r for r in rows if r.order_line_id == ln.pk],
            }
        )
    full = sum(1 for i in items if i["short"] <= 0)
    shorts = [
        f"{i['line'].item.name}: ordered {plain(i['want'] / i['factor'])} {i['unit_name']}, "
        f"found {plain(i['got'] / i['factor'])} {i['unit_name']}"
        + (f" ({plain(i['got'])} {i['stock_unit_name']})" if i["factor"] != 1 else "")
        + f", short {plain(i['short'] / i['factor'])} {i['unit_name']}"
        + (f" ({plain(i['short'])} {i['stock_unit_name']})" if i["factor"] != 1 else "")
        for i in items
        if i["short"] > 0
    ]
    if not items:
        text = "Nothing to pick."
    elif not shorts:
        text = f"All in stock: {len(items)} of {len(items)} items fully picked."
    else:
        text = (
            f"Not all in stock: {full} of {len(items)} items fully picked from stock. "
            + "; ".join(shorts)
            + "."
        )
    return {"items": items, "full": full, "count": len(items), "all_in": not shorts, "text": text}


def stock_lines_of(pick: PickList) -> list[SalesOrderLine]:
    """The order lines this list covers: those it has rows for, and stock lines
    with something to go (so a line with nothing found still shows as short).
    A picked or cancelled list keeps what it had."""
    have = set(pick.lines.values_list("order_line", flat=True))
    lines = pick.order.lines.select_related("item", "item__stock_unit", "unit")
    if pick.status != PickList.OPEN:
        return [ln for ln in lines if ln.pk in have or (ln.item.maintain_stock and ln.qty > 0)]
    return [ln for ln in lines if ln.pk in have or (ln.item.maintain_stock and pending(ln) > 0)]
