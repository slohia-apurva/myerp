"""Stock transfers count as entries for the Owner's "Reset data" tool."""

from core.data_reset import register_entries
from stock.models import CustomerStock, OwnUse, StockTransfer


def _transfers(company):
    rows = StockTransfer.objects.all()
    return rows.filter(company=company) if company else rows


register_entries(
    "Stock transfers", lambda c: _transfers(c).count(), lambda c: _transfers(c).delete()
)


def _customer(company):
    rows = CustomerStock.objects.all()
    return rows.filter(company=company) if company else rows


register_entries(
    "Stock receipts and deliveries (customer's goods)",
    lambda c: _customer(c).count(),
    lambda c: _customer(c).delete(),
)


def _own(company):
    rows = OwnUse.objects.all()
    return rows.filter(company=company) if company else rows


register_entries("Own use entries", lambda c: _own(c).count(), lambda c: _own(c).delete())
