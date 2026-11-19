"""Sales orders count as entries for the Owner's "Reset data" tool."""

from core.data_reset import register_entries
from selling.models import SalesOrder


def _orders(company):
    rows = SalesOrder.objects.all()
    return rows.filter(company=company) if company else rows


register_entries("Sales orders", lambda c: _orders(c).count(), lambda c: _orders(c).delete())
