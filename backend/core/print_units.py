"""Quantities on prints (Sidharth, 2026-11-25): the quantity in the item's stock
unit ("240 Nos") with, under it, the quantity in the unit just above the stock
unit ("10 Case"); the rate is always per stock unit."""

from __future__ import annotations

from decimal import Decimal

from core.models import Item, ItemUnit

PLACES = Decimal("0.001")


def _plain(d: Decimal) -> str:
    text = f"{d:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _name(unit) -> str:
    return unit.short_name or unit.name


def next_unit(item: Item) -> ItemUnit | None:
    """The item's unit that holds its stock unit directly (a Case of 24 Nos);
    the smallest such when there are several."""
    return (
        ItemUnit.objects.filter(item=item, contains_unit_id=item.stock_unit_id)
        .exclude(unit_id=item.stock_unit_id)
        .select_related("unit")
        .order_by("factor", "id")
        .first()
    )


def in_stock_unit(line: dict, item: Item) -> dict:
    """A print line (qty, unit, rate in the unit ordered) moved to the stock
    unit, with "qty_alt" / "unit_alt" in the next unit up when the item has one."""
    row = ItemUnit.objects.filter(item=item, unit_id=line["unit"]).first()
    factor = row.factor if row is not None and row.factor else Decimal("1")
    qty = Decimal(str(line["qty"])) * factor
    out = {
        **line,
        "qty": _plain(qty.quantize(PLACES).normalize()),
        "unit_name": _name(item.stock_unit),
        "rate": str(Decimal(str(line["rate"])) / factor),
    }
    up = next_unit(item)
    if up is not None and up.factor:
        out["qty_alt"] = _plain((qty / up.factor).quantize(PLACES).normalize())
        out["unit_alt"] = _name(up.unit)
    return out
