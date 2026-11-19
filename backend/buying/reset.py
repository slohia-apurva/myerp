"""Purchase orders count as entries for the Owner's "Reset data" tool."""

from buying.models import (
    DebitNote,
    GoodsReceipt,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseReturn,
    TdsAdjustment,
)
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


def _notes(company):
    rows = DebitNote.objects.all()
    return rows.filter(company=company) if company else rows


def _returns(company):
    rows = PurchaseReturn.objects.all()
    return rows.filter(company=company) if company else rows


def _tds_adjustments(company):
    rows = TdsAdjustment.objects.all()
    return rows.filter(company=company) if company else rows


register_entries(
    "TDS adjustments",
    lambda c: _tds_adjustments(c).count(),
    lambda c: _tds_adjustments(c).delete(),
)
register_entries("Debit notes", lambda c: _notes(c).count(), lambda c: _notes(c).delete())
register_entries("Purchase returns", lambda c: _returns(c).count(), lambda c: _returns(c).delete())


def _delete_invoices(company) -> None:
    # Supplementary bills point at their original bill: they go first.
    _invoices(company).exclude(original=None).delete()
    _invoices(company).delete()


register_entries("Purchase invoices", lambda c: _invoices(c).count(), _delete_invoices)
register_entries("Packages", lambda c: _packages(c).count(), lambda c: _packages(c).delete())
register_entries("Goods receipts", lambda c: _receipts(c).count(), lambda c: _receipts(c).delete())
register_entries("Purchase orders", lambda c: _orders(c).count(), lambda c: _orders(c).delete())
