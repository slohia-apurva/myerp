"""When a master counts as in use because of sales orders (core.locks). A draft
is not yet an entry; a submitted order (even one cancelled later) is."""

from core import locks
from selling.models import SalesOrder, SalesOrderCharge, SalesOrderLine


def _orders(**where) -> str:
    rows = SalesOrder.objects.filter(**where).exclude(status=SalesOrder.DRAFT)
    return locks._count(rows, "sales order")


def _line_orders(**where) -> str:
    lines = SalesOrderLine.objects.filter(**where).exclude(order__status=SalesOrder.DRAFT)
    return locks._count(SalesOrder.objects.filter(pk__in=lines.values("order")), "sales order")


def _charge_orders(**where) -> str:
    rows = SalesOrderCharge.objects.filter(**where).exclude(order__status=SalesOrder.DRAFT)
    return locks._count(SalesOrder.objects.filter(pk__in=rows.values("order")), "sales order")


locks.register("item", lambda item: _line_orders(item=item))
locks.register("item", lambda item: _charge_orders(item=item))
locks.register("unit", lambda unit: _line_orders(unit=unit))
locks.register("ledger", lambda ledger: _orders(customer=ledger))
locks.register("party", lambda party: _orders(customer__party=party))
locks.register("branch", lambda branch: _orders(branch=branch))
locks.register("branch", lambda branch: _orders(bill_from=branch))
locks.register("courier_account", lambda account: _orders(transporter=account))
locks.register("terms", lambda terms: _orders(terms_set=terms))
