"""When a master counts as in use because of stock entries (core.locks): a
dispatched transfer or a submitted receipt or delivery of a customer's goods
(even one cancelled later) is an entry; a draft is not."""

from core import locks
from stock.models import (
    CustomerStock,
    CustomerStockLine,
    OwnUse,
    OwnUseLine,
    StockTransfer,
    StockTransferLine,
)


def _transfers(**where) -> str:
    rows = StockTransfer.objects.filter(**where).exclude(status=StockTransfer.DRAFT)
    return locks._count(rows.exclude(number=""), "stock transfer")


def _line_transfers(**where) -> str:
    lines = StockTransferLine.objects.filter(**where).exclude(transfer__number="")
    return locks._count(
        StockTransfer.objects.filter(pk__in=lines.values("transfer")), "stock transfer"
    )


locks.register("item", lambda item: _line_transfers(item=item))
locks.register("unit", lambda unit: _line_transfers(unit=unit))
locks.register("branch", lambda branch: _transfers(from_branch=branch))
locks.register("branch", lambda branch: _transfers(to_branch=branch))
locks.register("courier_account", lambda account: _transfers(transporter=account))


def _customer(**where) -> str:
    return locks._count(CustomerStock.objects.filter(**where).exclude(number=""), "stock entry")


def _customer_lines(**where) -> str:
    lines = CustomerStockLine.objects.filter(**where).exclude(entry__number="")
    return locks._count(CustomerStock.objects.filter(pk__in=lines.values("entry")), "stock entry")


locks.register("item", lambda item: _customer_lines(item=item))
locks.register("unit", lambda unit: _customer_lines(unit=unit))
locks.register("branch", lambda branch: _customer(branch=branch))
locks.register("ledger", lambda ledger: _customer(customer=ledger))
locks.register("courier_account", lambda account: _customer(transporter=account))
locks.register("party", lambda party: _customer(customer__party=party))
locks.register("sales_person", lambda person: _customer(stores_person=person))


def _own(**where) -> str:
    return locks._count(OwnUse.objects.filter(**where).exclude(number=""), "own use entry")


def _own_lines(**where) -> str:
    lines = OwnUseLine.objects.filter(**where).exclude(entry__number="")
    return locks._count(OwnUse.objects.filter(pk__in=lines.values("entry")), "own use entry")


locks.register("item", lambda item: _own_lines(item=item))
locks.register("unit", lambda unit: _own_lines(unit=unit))
locks.register("branch", lambda branch: _own(branch=branch))
locks.register("ledger", lambda ledger: _own_lines(expense_ledger=ledger))
locks.register("sales_person", lambda person: _own(stores_person=person))
