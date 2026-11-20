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


def _delivery_note(request, pk: int) -> attachments.Found:
    from selling.delivery import _note
    from selling.pick_lists import may

    if not may(request.user, "view"):
        raise attachments.NotFound("No such delivery note.")
    return attachments.Found(_note(request, pk), may(request.user, "create"))


attachments.register("delivery_note", _delivery_note, "Delivery Note")


def _sales_invoice(request, pk: int) -> attachments.Found:
    from selling.invoices import _invoice, may

    if not may(request.user, "view"):
        raise attachments.NotFound("No such sales invoice.")
    return attachments.Found(_invoice(request, pk), may(request.user, "create"))


attachments.register("sales_invoice", _sales_invoice, "Sales Invoice")
