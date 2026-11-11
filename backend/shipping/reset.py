"""Shipments count as entries for the Owner's "Reset data" tool: clearing a
company's entries clears its shipments and their tracking. Courier accounts
are set-up and stay."""

from core.data_reset import register_entries
from shipping.models import Shipment, TrackingEvent


def _shipments(company):
    rows = Shipment.objects.all()
    return rows.filter(company=company) if company else rows


def _delete(company) -> None:
    # Bulk deletes skip TrackingEvent.delete, which refuses single deletes.
    TrackingEvent.objects.filter(shipment__in=_shipments(company)).delete()
    _shipments(company).delete()


register_entries("Shipments", lambda c: _shipments(c).count(), _delete)
