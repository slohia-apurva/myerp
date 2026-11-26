"""Masters with GL entries or stock moves against them are in use (core.locks)."""

from core import locks
from posting.models import GLEntry, StockMove


def _vouchers(rows, noun: str) -> str:
    n = rows.values("voucher_type", "voucher_id").distinct().count()
    return f"{n} {noun}{'' if n == 1 else 's'}" if n else ""


def _stock(**where) -> str:
    return _vouchers(StockMove.objects.filter(**where), "stock posting")


locks.register("ledger", lambda ledger: _vouchers(GLEntry.objects.filter(ledger=ledger), "entry"))
locks.register("item", lambda item: _stock(item=item))
locks.register("batch", lambda batch: _stock(batch=batch))
locks.register("unit", lambda unit: _stock(item__stock_unit=unit))
locks.register("branch", lambda branch: _stock(branch=branch))
locks.register("warehouse_location", lambda loc: _stock(location=loc))


def _group_use(group, company) -> str:
    """Once stock of a main group's items has been valued in a company, that
    company's Stock and COGS ledgers on the group stop changing. One query over
    the group's own tree (it used to load every moved item and walk its groups)."""
    from core.item_groups import descendant_ids

    if group.parent_id is not None:
        return ""  # only main groups hold accounts
    tree = {group.pk, *descendant_ids(group)}
    return _stock(company=company, valued=True, item__item_group_id__in=tree)


locks.register_account_use(_group_use)
