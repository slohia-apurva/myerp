"""Stock entries keep files in the Attachments box (the e-way bill, the
transporter's receipt, the customer's challan)."""

from core import attachments


def _stock_transfer(request, pk: int) -> attachments.Found:
    from stock.transfers import _transfer, may

    if not may(request.user, "view"):
        raise attachments.NotFound("No such stock transfer.")
    return attachments.Found(_transfer(request, pk), may(request.user, "create"))


attachments.register("stock_transfer", _stock_transfer, "Stock Transfer")


def _customer_stock(kind: str):
    def find(request, pk: int) -> attachments.Found:
        from stock.customer import _entry
        from stock.transfers import may

        if not may(request.user, "view"):
            raise attachments.NotFound("No such stock entry.")
        e = _entry(request, pk)
        if e.kind != kind:
            raise attachments.NotFound("No such stock entry.")
        return attachments.Found(e, may(request.user, "create"))

    return find


# A customer's challan, a photo of the goods as they came.
attachments.register("stock_receipt", _customer_stock("receipt"), "Stock Receipt")
attachments.register("stock_delivery", _customer_stock("delivery"), "Stock Delivery")
