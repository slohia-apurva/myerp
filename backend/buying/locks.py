"""When a master counts as in use because of purchase orders (core.locks). A
draft is not yet an entry; a submitted order (even one cancelled later) is."""

from buying.models import (
    DebitNote,
    GoodsReceipt,
    GoodsReceiptPutaway,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderCharge,
    PurchaseOrderLine,
    PurchaseReturn,
    TdsAdjustment,
)
from core import locks


def _orders(**where) -> str:
    rows = PurchaseOrder.objects.filter(**where).exclude(status=PurchaseOrder.DRAFT)
    return locks._count(rows, "purchase order")


def _line_orders(**where) -> str:
    lines = PurchaseOrderLine.objects.filter(**where).exclude(order__status=PurchaseOrder.DRAFT)
    orders = PurchaseOrder.objects.filter(pk__in=lines.values("order"))
    return locks._count(orders, "purchase order")


def _charge_orders(**where) -> str:
    rows = PurchaseOrderCharge.objects.filter(**where).exclude(order__status=PurchaseOrder.DRAFT)
    orders = PurchaseOrder.objects.filter(pk__in=rows.values("order"))
    return locks._count(orders, "purchase order")


locks.register("item", lambda item: _line_orders(item=item))
locks.register("item", lambda item: _charge_orders(item=item))
locks.register("unit", lambda unit: _line_orders(unit=unit))
locks.register("ledger", lambda ledger: _orders(supplier=ledger))
locks.register("party", lambda party: _orders(supplier__party=party))
locks.register("branch", lambda branch: _orders(branch=branch))
locks.register("ledger", lambda ledger: _orders(agent=ledger))
locks.register("courier_account", lambda account: _orders(transporter=account))
locks.register("branch", lambda branch: _orders(bill_to=branch))
locks.register("terms", lambda terms: _orders(terms_set=terms))


def _receipts(**where) -> str:
    rows = GoodsReceipt.objects.filter(**where).exclude(status=GoodsReceipt.DRAFT)
    return locks._count(rows.distinct(), "goods receipt")


locks.register("ledger", lambda ledger: _receipts(supplier=ledger))
locks.register("branch", lambda branch: _receipts(branch=branch))
locks.register("courier_account", lambda account: _receipts(transporter=account))
locks.register(
    "warehouse_location",
    lambda loc: locks._count(
        GoodsReceipt.objects.filter(
            pk__in=GoodsReceiptPutaway.objects.filter(location=loc).values("line__receipt")
        ).exclude(status=GoodsReceipt.DRAFT),
        "goods receipt",
    ),
)


def _invoices(**where) -> str:
    rows = PurchaseInvoice.objects.filter(**where).exclude(status=PurchaseInvoice.DRAFT)
    return locks._count(rows.distinct(), "purchase invoice")


locks.register("ledger", lambda ledger: _invoices(supplier=ledger))
locks.register("branch", lambda branch: _invoices(branch=branch))
locks.register("item", lambda item: _invoices(lines__item=item))
locks.register("item", lambda item: _invoices(charges__item=item))
locks.register("item", lambda item: _invoices(expense_lines__item=item))


def _returns(**where) -> str:
    rows = PurchaseReturn.objects.filter(**where).exclude(status=PurchaseReturn.DRAFT)
    return locks._count(rows.distinct(), "purchase return")


def _notes(**where) -> str:
    rows = DebitNote.objects.filter(**where).exclude(status=DebitNote.DRAFT)
    return locks._count(rows.distinct(), "debit note")


locks.register("ledger", lambda ledger: _returns(supplier=ledger))
locks.register("branch", lambda branch: _returns(branch=branch))
locks.register("item", lambda item: _returns(lines__item=item))
locks.register("courier_account", lambda account: _returns(transporter=account))
locks.register("warehouse_location", lambda loc: _returns(lines__location=loc))
locks.register("ledger", lambda ledger: _notes(supplier=ledger))
locks.register("branch", lambda branch: _notes(branch=branch))
locks.register("item", lambda item: _notes(lines__item=item))


def _tds_adjustments(**where) -> str:
    rows = TdsAdjustment.objects.filter(**where).exclude(status=TdsAdjustment.DRAFT)
    return locks._count(rows.distinct(), "TDS adjustment")


locks.register("ledger", lambda ledger: _tds_adjustments(supplier=ledger))
locks.register("branch", lambda branch: _tds_adjustments(branch=branch))
