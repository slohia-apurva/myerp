"""When a master counts as in use because of sales orders (core.locks). A draft
is not yet an entry; a submitted order (even one cancelled later) is."""

from core import locks
from selling.models import (
    CreditNote,
    CreditNoteLine,
    DeliveryNote,
    DeliveryNoteLine,
    SalesInvoice,
    SalesInvoiceCharge,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderCharge,
    SalesOrderLine,
)


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


def _notes(**where) -> str:
    rows = DeliveryNote.objects.filter(**where).exclude(status=DeliveryNote.DRAFT)
    return locks._count(rows, "delivery note")


def _line_notes(**where) -> str:
    lines = DeliveryNoteLine.objects.filter(**where).exclude(note__status=DeliveryNote.DRAFT)
    return locks._count(DeliveryNote.objects.filter(pk__in=lines.values("note")), "delivery note")


locks.register("item", lambda item: _line_notes(item=item))
locks.register("unit", lambda unit: _line_notes(unit=unit))
locks.register("ledger", lambda ledger: _notes(customer=ledger))
locks.register("party", lambda party: _notes(customer__party=party))
locks.register("branch", lambda branch: _notes(branch=branch))
locks.register("courier_account", lambda account: _notes(transporter=account))


def _invoices(**where) -> str:
    rows = SalesInvoice.objects.filter(**where).exclude(status=SalesInvoice.DRAFT)
    return locks._count(rows, "sales invoice")


def _line_invoices(model, **where) -> str:
    lines = model.objects.filter(**where).exclude(invoice__status=SalesInvoice.DRAFT)
    return locks._count(
        SalesInvoice.objects.filter(pk__in=lines.values("invoice")), "sales invoice"
    )


locks.register("item", lambda item: _line_invoices(SalesInvoiceLine, item=item))
locks.register("item", lambda item: _line_invoices(SalesInvoiceCharge, item=item))
locks.register("unit", lambda unit: _line_invoices(SalesInvoiceLine, unit=unit))
locks.register("ledger", lambda ledger: _invoices(customer=ledger))
locks.register("party", lambda party: _invoices(customer__party=party))
locks.register("branch", lambda branch: _invoices(bill_from=branch))
locks.register("courier_account", lambda account: _invoices(transporter=account))


def _credit_notes(**where) -> str:
    rows = CreditNote.objects.filter(**where).exclude(status=CreditNote.DRAFT)
    return locks._count(rows, "credit note")


def _line_credit_notes(**where) -> str:
    lines = CreditNoteLine.objects.filter(**where).exclude(note__status=CreditNote.DRAFT)
    return locks._count(CreditNote.objects.filter(pk__in=lines.values("note")), "credit note")


locks.register("item", lambda item: _line_credit_notes(item=item))
locks.register("unit", lambda unit: _line_credit_notes(unit=unit))
locks.register("ledger", lambda ledger: _credit_notes(customer=ledger))
locks.register("party", lambda party: _credit_notes(customer__party=party))
locks.register("branch", lambda branch: _credit_notes(bill_from=branch))
