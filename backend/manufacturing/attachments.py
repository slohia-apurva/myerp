"""A manufacturing order keeps files in the Attachments box (batch sheet,
QC report, photos)."""

from core import attachments


def _order(request, pk: int) -> attachments.Found:
    from manufacturing.orders import _order as find
    from manufacturing.orders import may

    if not may(request.user, "view"):
        raise attachments.NotFound("No such manufacturing order.")
    return attachments.Found(find(request, pk), may(request.user, "create"))


attachments.register("manufacturing_order", _order, "Manufacturing Order")
