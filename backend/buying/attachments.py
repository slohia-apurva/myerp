"""Purchase orders and goods receipts keep files in the Attachments box."""

from buying import receipts
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


attachments.register("purchase_order", _purchase_order)
attachments.register("goods_receipt", _goods_receipt)
