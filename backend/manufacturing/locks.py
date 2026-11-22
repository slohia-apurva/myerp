"""When a master counts as in use because of BOMs (core.locks): an item made
or used by a BOM keeps its units (the BOM's quantities are in them). A BOM
itself is in use once a Manufacturing Order uses it; they register their own
test when they are built."""

from core import locks
from manufacturing.models import Bom


def _item_boms(item) -> str:
    rows = Bom.objects.filter(item=item) | Bom.objects.filter(lines__item=item)
    return locks._count(rows.distinct(), "BOM")


locks.register("item", _item_boms)
