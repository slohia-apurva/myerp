"""Purchase orders count as entries for the Owner's "Reset data" tool."""

from buying.models import PurchaseOrder
from core.data_reset import register_entries


def _orders(company):
    rows = PurchaseOrder.objects.all()
    return rows.filter(company=company) if company else rows


register_entries("Purchase orders", lambda c: _orders(c).count(), lambda c: _orders(c).delete())
