"""Sales orders count as entries for the Owner's "Reset data" tool."""

from core.data_reset import register_entries
from selling.models import PickList, SalesOrder


def _orders(company):
    rows = SalesOrder.objects.all()
    return rows.filter(company=company) if company else rows


def _picks(company):
    rows = PickList.objects.all()
    return rows.filter(company=company) if company else rows


# Pick lists point at sales orders, so they go first.
register_entries("Pick lists", lambda c: _picks(c).count(), lambda c: _picks(c).delete())
register_entries("Sales orders", lambda c: _orders(c).count(), lambda c: _orders(c).delete())
