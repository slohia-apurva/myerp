"""Sales orders keep files in the Attachments box (the customer's PO, for one)."""

from core import attachments
from selling.api import _order


def _sales_order(request, pk: int) -> attachments.Found:
    if not request.user.can("sales.view"):
        raise attachments.NotFound("No such sales order.")
    return attachments.Found(_order(request, pk), request.user.can("sales.create"))


attachments.register("sales_order", _sales_order, "Sales Order")
