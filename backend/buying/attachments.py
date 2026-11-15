"""Purchase orders and goods receipts keep files in the Attachments box."""

from buying import debit_notes, invoices, receipts, returns
from buying.api import _order
from core import attachments


def _purchase_order(request, pk: int) -> attachments.Found:
    if not request.user.can("purchase.view"):
        raise attachments.NotFound("No such purchase order.")
    return attachments.Found(_order(request, pk), request.user.can("purchase.create"))


def _goods_receipt(request, pk: int) -> attachments.Found:
    if not receipts.can(request.user, "view"):
        raise attachments.NotFound("No such goods receipt.")
    return attachments.Found(receipts._receipt(request, pk), receipts.can(request.user, "create"))


def _purchase_invoice(request, pk: int) -> attachments.Found:
    if not request.user.can("purchase.view"):
        raise attachments.NotFound("No such purchase invoice.")
    return attachments.Found(invoices._invoice(request, pk), request.user.can("purchase.create"))


def _purchase_return(request, pk: int) -> attachments.Found:
    if not receipts.can(request.user, "view"):
        raise attachments.NotFound("No such purchase return.")
    return attachments.Found(returns._return(request, pk), receipts.can(request.user, "create"))


def _debit_note(request, pk: int) -> attachments.Found:
    if not request.user.can("purchase.view"):
        raise attachments.NotFound("No such debit note.")
    return attachments.Found(debit_notes._note(request, pk), request.user.can("purchase.create"))


attachments.register("purchase_order", _purchase_order, "Purchase Order")
attachments.register("goods_receipt", _goods_receipt, "Goods Receipt")
attachments.register("purchase_invoice", _purchase_invoice, "Purchase Invoice")
attachments.register("purchase_return", _purchase_return, "Purchase Return")
attachments.register("debit_note", _debit_note, "Debit Note")
