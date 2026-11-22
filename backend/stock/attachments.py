"""Stock transfers keep files in the Attachments box (the e-way bill, the
transporter's receipt)."""

from core import attachments


def _stock_transfer(request, pk: int) -> attachments.Found:
    from stock.transfers import _transfer, may

    if not may(request.user, "view"):
        raise attachments.NotFound("No such stock transfer.")
    return attachments.Found(_transfer(request, pk), may(request.user, "create"))


attachments.register("stock_transfer", _stock_transfer, "Stock Transfer")
