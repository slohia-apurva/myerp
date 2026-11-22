"""When a master counts as in use because of BOMs and manufacturing orders
(core.locks): an item made or used by a BOM keeps its units (the BOM's
quantities are in them); a BOM version, an item, a unit or a branch on a
submitted manufacturing order (even one cancelled later) is in use."""

from core import locks
from manufacturing.models import Bom, ManufacturingOrder, ManufacturingOrderLine


def _item_boms(item) -> str:
    rows = Bom.objects.filter(item=item) | Bom.objects.filter(lines__item=item)
    return locks._count(rows.distinct(), "BOM")


def _orders(**where) -> str:
    return locks._count(
        ManufacturingOrder.objects.filter(**where).exclude(number=""), "manufacturing order"
    )


def _order_lines(**where) -> str:
    lines = ManufacturingOrderLine.objects.filter(**where).exclude(order__number="")
    return locks._count(
        ManufacturingOrder.objects.filter(pk__in=lines.values("order")), "manufacturing order"
    )


locks.register("item", _item_boms)
locks.register("bom", lambda bom: _orders(bom=bom))
locks.register("item", lambda item: _orders(item=item))
locks.register("item", lambda item: _order_lines(item=item))
locks.register("unit", lambda unit: _orders(unit=unit))
locks.register("unit", lambda unit: _order_lines(unit=unit))
locks.register("branch", lambda branch: _orders(branch=branch))
