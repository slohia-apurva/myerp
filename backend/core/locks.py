"""Masters in use: once a record has entries against it, its key fields stop
changing (Sidharth, 2026-11-11). Names, notes, contacts and Disable stay open.

Each master lists its key fields in KEY_FIELDS and says what counts as "in
use" by registering functions. Vouchers, stock movements and the like add themselves by
registering a function: `register("item", lambda item: "stock entries" if ... )`.
The save code of every master calls `refuse_key_changes` before it applies a
change.
"""

from collections.abc import Callable

from rest_framework.exceptions import ValidationError

# What each master will not let go once it is in use: field -> label.
KEY_FIELDS: dict[str, dict[str, str]] = {
    "unit": {"gst_code": "GST unit code", "whole_numbers": "whole numbers only"},
    "item": {
        "item_type": "type",
        "stock_unit": "stock unit",
        "hsn": "HSN",
        "batch_tracked": "batch tracking",
        "units": "units of measure",
    },
    "credit_term": {"parts": "parts"},
    "ledger_group": {"parent": "the group it sits under"},
    "ledger": {"group": "group", "currency": "currency", "bill_wise": "bill-wise"},
    "party": {
        "gst_type": "GST type",
        "gstin": "GSTIN",
        "pan": "PAN",
        "state_code": "state",
    },
    "company": {
        "fiscal_year_start_month": "financial year start",
        "books_start": "books beginning date",
    },
    "branch": {"gstin": "GSTIN", "state_code": "state"},
    "courier_account": {"carrier_id": "courier", "service": "service"},
}

# A function per master that returns why the record is in use, or "".
_USES: dict[str, list[Callable]] = {kind: [] for kind in KEY_FIELDS}


def register(kind: str, fn: Callable) -> None:
    """Add a way a master can be in use (a voucher type, say). `fn(record)`
    returns a short reason like "3 purchase invoices", or "" when unused."""
    _USES[kind].append(fn)


def uses(kind: str, record) -> list[str]:
    """Why this record is in use; an empty list means it is free to change."""
    if record is None or not record.pk:
        return []
    return [reason for fn in _USES[kind] if (reason := fn(record))]


def _count(qs, noun: str) -> str:
    n = qs.count()
    return f"{n} {noun}{'' if n == 1 else 's'}" if n else ""


def refuse_key_changes(kind: str, record, changes: dict) -> None:
    """Raise if `changes` (field -> new value) alter a key field of a record
    that is in use. Unchanged values pass, so a form that sends every field
    back is fine."""
    if record is None or not record.pk:
        return
    keys = KEY_FIELDS[kind]
    changed = [f for f, new in changes.items() if f in keys and _differs(record, f, new)]
    if not changed:
        return
    why = uses(kind, record)
    if not why:
        return
    reason = ", ".join(why)
    raise ValidationError(
        {
            f: [
                f"Cannot change the {keys[f]}: this is in use ({reason}). You can still disable it."
            ]
            for f in changed
        }
    )


def _differs(record, field: str, new) -> bool:
    old = getattr(record, field)
    if hasattr(old, "pk"):  # a related record, compare by id
        old = old.pk
    if hasattr(new, "pk"):
        new = new.pk
    if old is None and new in ("", None):
        return False
    return old != new


def _unit_uses(unit) -> str:
    from core.models import Item, ItemUnit

    items = Item.objects.filter(stock_unit=unit).values_list("pk", flat=True)
    in_chains = ItemUnit.objects.filter(unit=unit).values_list("item_id", flat=True)
    chained = ItemUnit.objects.filter(contains_unit=unit).values_list("item_id", flat=True)
    n = len({*items, *in_chains, *chained})
    return f"{n} item{'' if n == 1 else 's'}" if n else ""


def _term_uses(term) -> str:
    return _count(term.parties.all(), "customer or supplier")


register("unit", _unit_uses)
register("credit_term", _term_uses)

# Ledgers, groups, parties, companies, branches and items take no `register`
# here yet: opening balances are set-up data that stay editable, and nothing
# else posts against them. The first voucher or stock entry registers its own
# test for each (see the module note), and the lock starts working for it.
