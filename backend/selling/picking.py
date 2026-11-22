"""Choosing bins and batches for a sales order (Sidharth, 2026-11-19, preview 6).

The rule, approved with the previews:
- only places in the order's Despatch From (the area and the racks and bins in
  it, or the whole branch);
- earliest expiry first, then oldest received (a batch with no expiry comes
  after those with one);
- a batch held back (Quarantine or Rejected) is never picked;
- stock already on an open or picked pick list is kept aside.

Packages (Sidharth, 2026-11-20, previews 12a/12b): where a bin and batch hold
numbered bags or boxes, each is a place of its own, taken whole, lowest PK
number first; only the last one an item needs is opened. A package on another
open or picked list is not offered. Stock without package numbers (opening
stock, goods before packages) is "No package".

Quantities here are in the item's stock unit.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Min, Q, Sum

from core import numbering
from core.models import Batch, Item, ItemUnit, Package, WarehouseLocation
from posting.models import StockMove
from selling import stock
from selling.models import PickList, PickListLine, SalesOrder, SalesOrderLine

ZERO = Decimal("0")
FAR = datetime.date(9999, 12, 31)
HELD = (Batch.QUARANTINE, Batch.REJECTED)


@dataclass
class Spot:
    """Stock of one item in one place and batch (and package) that may be picked."""

    location: WarehouseLocation
    batch: Batch | None
    free: Decimal
    received: datetime.date | None
    package: Package | None = None

    @property
    def key(self) -> tuple[int, int | None, int | None]:
        return (
            self.location.pk,
            self.batch.pk if self.batch else None,
            self.package.pk if self.package else None,
        )

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
            self.package is None,
            self.package.seq if self.package else 0,
        )


def area_of(place: WarehouseLocation) -> WarehouseLocation | None:
    """The area a bin or rack stands in (or the place itself, if an area)."""
    seen = 0
    while place is not None and place.kind != WarehouseLocation.AREA and seen < 5:
        place = place.parent
        seen += 1
    return place


def package_label(pk: Package) -> str:
    return f"{pk.get_kind_display()} {pk.position} of {pk.of_count}"


def factor(line: SalesOrderLine) -> Decimal:
    """Stock units in one of the line's units."""
    row = ItemUnit.objects.filter(item=line.item_id, unit=line.unit_id).first()
    return row.factor if row is not None and row.factor else Decimal("1")


def pending(line: SalesOrderLine) -> Decimal:
    """What is still to go on the line, in its own unit."""
    if line.closed_at:
        return ZERO
    return max(line.qty - line.delivered_qty, ZERO)


def spots(
    item: Item, branch, area=None, leave_out: PickList | None = None, owner=None
) -> list[Spot]:
    """Where the item may be picked from, in the order the rule picks them. With
    an owner (a customer's core.Party), only that customer's own goods."""
    moves = StockMove.objects.filter(item=item, location__in=stock.places(branch, area))
    if owner is not None:
        moves = moves.filter(owner=owner)
    rows = moves.values("location", "batch").annotate(
        q=Sum("qty"), first=Min("date", filter=Q(qty__gt=0))
    )
    held = PickListLine.objects.filter(item=item, pick_list__status__in=PickList.HOLDING)
    if leave_out is not None:
        held = held.exclude(pick_list=leave_out)
    kept = {
        (r["location"], r["batch"]): r["q"]
        for r in held.values("location", "batch").annotate(q=Sum("qty"))
    }
    # A package on another list is not offered at all (Sidharth, 2026-11-20),
    # nor what is left in it beyond what that list takes.
    on_lists = {
        r["package"]: r["q"]
        for r in held.exclude(package=None).values("package").annotate(q=Sum("qty"))
    }
    busy = set(on_lists)
    rest: dict[tuple, Decimal] = {}
    for pk in Package.objects.filter(pk__in=busy, left_qty__gt=0):
        left = pk.left_qty - on_lists[pk.pk]
        if left > 0:
            key = (pk.location_id, pk.batch_id)
            rest[key] = rest.get(key, ZERO) + left
    places = {
        p.pk: p
        for p in WarehouseLocation.objects.filter(
            pk__in={r["location"] for r in rows}
        ).select_related("parent__parent")
    }
    batches = {b.pk: b for b in Batch.objects.filter(pk__in={r["batch"] for r in rows} - {None})}
    bags: dict[tuple, list[Package]] = {}
    for pk in Package.objects.filter(
        item=item,
        location__in=places,
        status__in=(Package.IN_STOCK, Package.PART_USED),
        left_qty__gt=0,
    ).exclude(pk__in=busy):
        bags.setdefault((pk.location_id, pk.batch_id), []).append(pk)
    out = []
    for r in rows:
        batch = batches.get(r["batch"]) if r["batch"] else None
        if batch is not None and batch.status in HELD:
            continue
        key = (r["location"], r["batch"])
        free = (r["q"] or ZERO) - kept.get(key, ZERO) - rest.get(key, ZERO)
        place = places[r["location"]]
        for pk in sorted(bags.get((r["location"], r["batch"]), []), key=lambda x: x.seq):
            take = min(pk.left_qty, free)
            if take <= 0:
                break
            out.append(Spot(place, batch, take, r["first"], pk))
            free -= take
        if free > 0:
            out.append(Spot(place, batch, free, r["first"]))
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
    fill(pick, lines)
    return pick


def fill(pick: PickList, lines: list[SalesOrderLine] | None = None) -> None:
    """Choose bins and batches for the lines in the list's Despatch From, by the
    rule, replacing any rows the list had (its own rows are not kept aside)."""
    if lines is None:
        lines = stock_lines(pick.order)
    pick.lines.all().delete()
    taken: dict[tuple[int, tuple], Decimal] = {}
    rows = []
    for ln in lines:
        need = pending(ln) * factor(ln)
        for spot in spots(ln.item, pick.branch, pick.area, pick):
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
                    package=spot.package,
                    qty=take,
                )
            )
    PickListLine.objects.bulk_create(rows)


def coverage(pick: PickList, branch, area=None) -> tuple[int, int]:
    """How many of the list's items could be picked in full at a place (stock
    there less what other lists keep aside), and how many there are."""
    lines = stock_lines(pick.order)
    need: dict[int, Decimal] = {}
    for ln in lines:
        need[ln.item_id] = need.get(ln.item_id, ZERO) + pending(ln) * factor(ln)
    items = {ln.item_id: ln.item for ln in lines}
    full = sum(
        1
        for item_id, want in need.items()
        if sum((s.free for s in spots(items[item_id], branch, area, pick)), ZERO) >= want
    )
    return full, len(need)


def plain(n: Decimal) -> str:
    n = n.quantize(Decimal("0.001")).normalize()
    return f"{n:f}"


def summary(pick: PickList) -> dict:
    """Per order line: ordered, picked and short (in the line's unit and the
    stock unit), and the sentence the order and the list show."""
    rows = list(pick.lines.select_related("location__parent__parent", "batch", "package"))
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
