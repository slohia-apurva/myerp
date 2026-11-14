"""When a master counts as in use because of purchase orders (core.locks). A
draft is not yet an entry; a submitted order (even one cancelled later) is."""

from buying.models import PurchaseOrder, PurchaseOrderLine
from core import locks


def _orders(**where) -> str:
    rows = PurchaseOrder.objects.filter(**where).exclude(status=PurchaseOrder.DRAFT)
    return locks._count(rows, "purchase order")


def _line_orders(**where) -> str:
    lines = PurchaseOrderLine.objects.filter(**where).exclude(order__status=PurchaseOrder.DRAFT)
    orders = PurchaseOrder.objects.filter(pk__in=lines.values("order"))
    return locks._count(orders, "purchase order")


locks.register("item", lambda item: _line_orders(item=item))
locks.register("unit", lambda unit: _line_orders(unit=unit))
locks.register("ledger", lambda ledger: _orders(supplier=ledger))
locks.register("party", lambda party: _orders(supplier__party=party))
locks.register("branch", lambda branch: _orders(branch=branch))
locks.register("ledger", lambda ledger: _orders(agent=ledger))
locks.register("courier_account", lambda account: _orders(transporter=account))
locks.register("branch", lambda branch: _orders(bill_to=branch))
