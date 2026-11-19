"""Sales orders keep files in the Attachments box (the customer's PO, for one)."""

from core import attachments
from selling.api import _order


def _sales_order(request, pk: int) -> attachments.Found:
    if not request.user.can("sales.view"):
        raise attachments.NotFound("No such sales order.")
    return attachments.Found(_order(request, pk), request.user.can("sales.create"))


attachments.register("sales_order", _sales_order, "Sales Order")


def _pick_list(request, pk: int) -> attachments.Found:
    from selling.pick_lists import _pick, may

    if not may(request.user, "view"):
        raise attachments.NotFound("No such pick list.")
    return attachments.Found(_pick(request, pk), may(request.user, "create"))


attachments.register("pick_list", _pick_list, "Pick List")
