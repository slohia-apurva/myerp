"""Reading another system's export files into a master's own import sheets.

ERPNext (Sidharth, 2026-11-21): the item master comes across from ERPNext's
own export of the Item list (Menu > Export, Excel, with the child tables
"UOMs" and "Taxes"), unchanged. Each item keeps its ERPNext code as its item
number. Item groups and brands are made in MyERP first and only matched by
name; units match by name or short name; HSN codes are checked against the
HSN list as on the form. Description and the planning figures (safety stock,
lead time, minimum order) are left out: they are set afresh in MyERP.

The sheets made here go through the ordinary import (core/exchange.py), so
every row meets the form's own checks. Rows keep the row numbers they have in
the ERPNext file, so a problem "row 37" is row 37 of the person's file.
"""

from __future__ import annotations

import re

from rest_framework.exceptions import ParseError

from core.models import Item

GOODS, SERVICE = "Goods", "Service"
GST_START = "01-07-2017"  # when a tax row gives no "Valid From"

# ERPNext column headings (labels, or field names) -> what they are.
PARENT = {
    "code": ("item code", "item_code", "id", "name"),
    "name": ("item name", "item_name"),
    "item_group": ("item group", "item_group"),
    "stock_unit": ("default unit of measure", "stock_uom", "stock uom"),
    "brand": ("brand",),
    "hsn": ("hsn/sac", "gst_hsn_code", "hsn code", "hsn"),
    "maintain_stock": ("maintain stock", "is_stock_item", "is stock item"),
    "allow_purchase": ("allow purchase", "is purchase item", "is_purchase_item"),
    "allow_sales": ("allow sales", "is sales item", "is_sales_item"),
    "batch_tracked": ("has batch no", "has_batch_no"),
    "disabled": ("disabled",),
}
CHILD = {
    "uom": ("uom (uoms)",),
    "factor": ("conversion factor (uoms)", "conversion_factor (uoms)"),
    "template": ("item tax template (taxes)", "item_tax_template (taxes)"),
    "valid_from": ("valid from (taxes)", "valid_from (taxes)"),
}
YES = {"1", "yes", "y", "true"}
NO = {"0", "no", "n", "false"}


def _key(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


def _find(header: list[str], names: dict) -> dict[str, int]:
    keys = [_key(h) for h in header]
    at = {}
    for what, options in names.items():
        for option in options:  # the first heading listed wins ("Item Code" before "ID")
            if option in keys:
                at[what] = keys.index(option)
                break
    return at


def _rate(template: str) -> str:
    """The GST rate an ERPNext Item Tax Template stands for, from its name:
    "GST 5% - AO" is 5. Exempt and nil-rated templates are 0. Anything else
    is passed on as it is, and the import says it is not a number."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", template) or re.search(r"(\d+(?:\.\d+)?)", template)
    if m:
        return m[1]
    low = template.lower()
    if any(word in low for word in ("exempt", "nil", "non-gst", "non gst", "zero")):
        return "0"
    return template


def _flip(text: str) -> str:
    """ERPNext's "Disabled" as MyERP's "Active"."""
    low = text.strip().lower()
    if low in YES:
        return "No"
    if low in NO:
        return "Yes"
    return text


def item_tables(tables: list) -> tuple[list, list[str]]:
    """ERPNext's Item export as the sheets of MyERP's item import, and notes
    for the person on what was left out."""
    from core import exchange

    rows = tables[0][1] if tables else []
    head_at = next(
        (
            i
            for i, row in enumerate(rows[:30])
            if {"item name", "item_name"} & {_key(c) for c in row}
        ),
        None,
    )
    if head_at is None:
        raise ParseError(
            'This is not an ERPNext Item export: no "Item Name" column was found. '
            'In ERPNext open the Item list, Menu > Export, tick "Select All", and choose Excel.'
        )
    header = rows[head_at]
    at, child = _find(header, PARENT), _find(header, CHILD)
    if "code" not in at:
        raise ParseError('The ERPNext file needs its "Item Code" (or "ID") column.')

    master = exchange.MASTERS["items"]
    sheets = master.sheets()
    label = {c.field: c.label for c in sheets[0].columns}
    sheet_of = {s.field: s for s in sheets[1:]}
    units_sheet, rates_sheet = sheet_of["units"], sheet_of["gst_rates"]
    unit_label = {c.field: c.label for c in units_sheet.columns}
    rate_label = {c.field: c.label for c in rates_sheet.columns}

    fields = ["item_number", "name"]
    if "hsn" in at:
        fields.append("item_type")
    for what in (
        "item_group",
        "stock_unit",
        "hsn",
        "brand",
        "maintain_stock",
        "allow_purchase",
        "allow_sales",
        "batch_tracked",
    ):
        if what in at:
            fields.append(what)
    if "disabled" in at:
        fields.append("is_active")
    main_head = [exchange.ID_LABEL] + [label[f] for f in fields]
    units_head = [
        units_sheet.link_label,
        unit_label["unit"],
        unit_label["contains_qty"],
        unit_label["contains_unit"],
    ]
    rates_head = [rates_sheet.link_label, rate_label["valid_from"], rate_label["rate"]]

    # Items already in MyERP: found by number, else by name (the few made
    # by hand before the import get their ERPNext codes).
    by_number = {n.lower(): pk for pk, n in Item.objects.values_list("pk", "item_number")}
    by_name = {n.lower(): pk for pk, n in Item.objects.values_list("pk", "name")}

    def cell(row: list[str], what: str, where: dict = at) -> str:
        i = where.get(what)
        return row[i].strip() if i is not None and i < len(row) else ""

    blank: list[str] = []
    main = [blank] * head_at + [main_head]
    units = [blank] * head_at + [units_head]
    rates = [blank] * head_at + [rates_head]
    no_rate: list[str] = []
    current = None  # (name, stock unit, rates seen) of the item the child rows belong to
    for row in rows[head_at + 1 :]:
        code = cell(row, "code")
        main_row = units_row = rates_row = blank
        if code:
            name = cell(row, "name")
            stock = cell(row, "stock_unit")
            pk = by_number.get(code.lower()) or by_name.get(name.lower())
            values = {
                "item_number": code,
                "name": name,
                "item_type": SERVICE if cell(row, "hsn").startswith("99") else GOODS,
                "is_active": _flip(cell(row, "disabled")),
            }
            main_row = [str(pk or "")] + [values.get(f, cell(row, f)) for f in fields]
            if current is not None and not current[2]:
                no_rate.append(current[3])
            current = (name, stock, set(), code)
        if current is not None:
            name, stock, seen, _ = current
            uom = cell(row, "uom", child)
            if uom and _key(uom) != _key(stock):
                units_row = [name, uom, cell(row, "factor", child), stock]
            template = cell(row, "template", child)
            if template:
                pair = (cell(row, "valid_from", child) or GST_START, _rate(template))
                if pair not in seen:
                    seen.add(pair)
                    rates_row = [name, *pair]
        main.append(main_row)
        units.append(units_row)
        rates.append(rates_row)
    if current is not None and not current[2]:
        no_rate.append(current[3])

    out = [(master.label, main)]
    notes = []
    if "uom" in child:
        out.append((units_sheet.title, units))
    else:
        notes.append(
            'The file has no "UOMs" table, so only each item\'s default unit came across. '
            'Tick the child table "UOMs" when exporting to bring the other units.'
        )
    if "template" in child:
        out.append((rates_sheet.title, rates))
        if no_rate:
            shown = ", ".join(no_rate[:10]) + (" …" if len(no_rate) > 10 else "")
            notes.append(
                f"{len(no_rate)} item{'s' if len(no_rate) != 1 else ''} had no GST rate in "
                f'ERPNext (empty "Taxes" table) and come in without one: {shown}. '
                "Add the rate on the item before billing it."
            )
    else:
        notes.append(
            'The file has no "Taxes" table, so no GST rates came across. '
            'Tick the child table "Taxes" when exporting to bring them.'
        )
    used = set(at.values()) | set(child.values())
    left = [
        h
        for i, h in enumerate(header)
        if h.strip()
        and i not in used
        and _key(h) not in ("id", "name")
        and not _key(h).startswith("id (")
    ]
    if left:
        shown = ", ".join(left[:8]) + (" …" if len(left) > 8 else "")
        notes.append(f"{len(left)} other ERPNext columns were left out: {shown}.")
    return out, notes
