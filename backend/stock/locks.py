"""When a master counts as in use because of stock transfers (core.locks): a
dispatched transfer (even one cancelled later) is an entry; a draft is not."""

from core import locks
from stock.models import StockTransfer, StockTransferLine


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
