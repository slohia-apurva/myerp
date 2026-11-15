"""Purchase orders and goods receipts keep files in the Attachments box."""

from buying import invoices, receipts
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


attachments.register("purchase_order", _purchase_order, "Purchase Order")
attachments.register("goods_receipt", _goods_receipt, "Goods Receipt")
attachments.register("purchase_invoice", _purchase_invoice, "Purchase Invoice")
