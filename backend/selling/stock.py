"""Stock a sales order can draw on (Sidharth, 2026-11-19): when the order goes
out from an area, only that area and the racks and bins under it; when it goes
out from a branch, anywhere in the branch."""

from decimal import Decimal

from django.db.models import Q, Sum

from core.models import Branch, Item, WarehouseLocation
from posting.models import StockMove

ZERO = Decimal("0")


def places(branch: Branch, area: WarehouseLocation | None = None):
    """The locations stock may be taken from: the area, its racks and their bins;
    or every location of the branch but its In Transit place."""
    # Goods in transit to the branch are not there yet (stock.transfers).
    rows = WarehouseLocation.objects.filter(branch=branch).exclude(purpose="transit")
    if area is None:
        return rows
    return rows.filter(Q(pk=area.pk) | Q(parent=area) | Q(parent__parent=area))


def on_hand(items, branch: Branch, area: WarehouseLocation | None = None) -> dict[int, Decimal]:
    """Quantity of each item (in its stock unit) at the branch or area."""
    rows = (
        StockMove.objects.filter(item__in=items, location__in=places(branch, area))
        .values("item")
        .annotate(q=Sum("qty"))
    )
    return {r["item"]: r["q"] or ZERO for r in rows}


def in_unit(item: Item, qty: Decimal, unit_id: int) -> Decimal:
    """A stock-unit quantity in another of the item's units."""
    row = item.units.filter(unit_id=unit_id).first()
    factor = row.factor if row is not None and row.factor else Decimal("1")
    return qty / factor
