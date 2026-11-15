"""Purchase orders count as entries for the Owner's "Reset data" tool."""

from buying.models import GoodsReceipt, PurchaseInvoice, PurchaseOrder
from core.data_reset import register_entries
from core.models import Package


def _orders(company):
    rows = PurchaseOrder.objects.all()
    return rows.filter(company=company) if company else rows


def _receipts(company):
    rows = GoodsReceipt.objects.all()
    return rows.filter(company=company) if company else rows


def _packages(company):
    rows = Package.objects.all()
    return rows.filter(company=company) if company else rows


def _invoices(company):
    rows = PurchaseInvoice.objects.all()
    return rows.filter(company=company) if company else rows


register_entries(
    "Purchase invoices", lambda c: _invoices(c).count(), lambda c: _invoices(c).delete()
)
register_entries("Packages", lambda c: _packages(c).count(), lambda c: _packages(c).delete())
register_entries("Goods receipts", lambda c: _receipts(c).count(), lambda c: _receipts(c).delete())
register_entries("Purchase orders", lambda c: _orders(c).count(), lambda c: _orders(c).delete())
