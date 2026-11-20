"""Sales orders count as entries for the Owner's "Reset data" tool."""

from core.data_reset import register_entries
from selling.models import DeliveryNote, PickList, SalesInvoice, SalesOrder


def _orders(company):
    rows = SalesOrder.objects.all()
    return rows.filter(company=company) if company else rows


def _picks(company):
    rows = PickList.objects.all()
    return rows.filter(company=company) if company else rows


def _notes(company):
    rows = DeliveryNote.objects.all()
    return rows.filter(company=company) if company else rows


def _invoices(company):
    rows = SalesInvoice.objects.all()
    return rows.filter(company=company) if company else rows


# Invoices point at delivery notes, notes at pick lists, and those at sales orders,
# so they go first.
register_entries("Sales invoices", lambda c: _invoices(c).count(), lambda c: _invoices(c).delete())
register_entries("Delivery notes", lambda c: _notes(c).count(), lambda c: _notes(c).delete())
register_entries("Pick lists", lambda c: _picks(c).count(), lambda c: _picks(c).delete())
register_entries("Sales orders", lambda c: _orders(c).count(), lambda c: _orders(c).delete())
