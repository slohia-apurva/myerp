"""Manufacturing orders count as entries for the Owner's "Reset data" tool
(BOMs are masters and stay)."""

from core.data_reset import register_entries
from manufacturing.models import ManufacturingOrder


def _orders(company):
    rows = ManufacturingOrder.objects.all()
    return rows.filter(company=company) if company else rows


register_entries(
    "Manufacturing orders", lambda c: _orders(c).count(), lambda c: _orders(c).delete()
)
