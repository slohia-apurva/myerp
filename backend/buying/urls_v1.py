from django.urls import path

from buying import api, debit_notes, invoices, receipts, returns, supplier_link, supplier_mail

urlpatterns = [
    # The supplier's page: no sign-in, reached by the private code in the mail.
    path("public/po/<str:token>/", supplier_link.PublicOrderView.as_view(), name="public-po"),
    path(
        "public/po/<str:token>/pdf/",
        supplier_link.PublicOrderPdfView.as_view(),
        name="public-po-pdf",
    ),
    path(
        "companies/<int:pk>/purchase-orders/", api.OrderListView.as_view(), name="purchase-orders"
    ),
    path(
        "companies/<int:pk>/purchase-orders/setup/",
        api.OrderSetupView.as_view(),
        name="purchase-order-setup",
    ),
    path(
        "companies/<int:pk>/purchase-orders/items/",
        api.OrderItemsView.as_view(),
        name="purchase-order-items",
    ),
    path(
        "companies/<int:pk>/purchase-orders/rate/",
        api.OrderRateView.as_view(),
        name="purchase-order-rate",
    ),
    path("purchase-orders/<int:pk>/", api.OrderDetailView.as_view(), name="purchase-order"),
    path(
        "purchase-orders/<int:pk>/pdf/",
        supplier_mail.OrderPdfView.as_view(),
        name="purchase-order-pdf",
    ),
    path(
        "purchase-orders/<int:pk>/mail/",
        supplier_mail.OrderMailView.as_view(),
        name="purchase-order-mail",
    ),
    path(
        "purchase-orders/<int:pk>/supplier-mail/",
        supplier_mail.SupplierMailView.as_view(),
        name="purchase-order-supplier-mail",
    ),
    path(
        "purchase-orders/<int:pk>/lines/<int:line>/close/",
        api.OrderLineCloseView.as_view(),
        name="purchase-order-line-close",
    ),
    path(
        "purchase-orders/<int:pk>/submit/",
        api.OrderSubmitView.as_view(),
        name="purchase-order-submit",
    ),
    path(
        "purchase-orders/<int:pk>/cancel/",
        api.OrderCancelView.as_view(),
        name="purchase-order-cancel",
    ),
    path(
        "companies/<int:pk>/goods-receipts/",
        receipts.ReceiptListView.as_view(),
        name="goods-receipts",
    ),
    path(
        "companies/<int:pk>/goods-receipts/setup/",
        receipts.ReceiptSetupView.as_view(),
        name="goods-receipt-setup",
    ),
    path(
        "companies/<int:pk>/goods-receipts/pending/",
        receipts.PendingOrdersView.as_view(),
        name="goods-receipt-pending",
    ),
    path("goods-receipts/<int:pk>/", receipts.ReceiptDetailView.as_view(), name="goods-receipt"),
    path(
        "goods-receipts/<int:pk>/submit/",
        receipts.ReceiptSubmitView.as_view(),
        name="goods-receipt-submit",
    ),
    path(
        "goods-receipts/<int:pk>/cancel/",
        receipts.ReceiptCancelView.as_view(),
        name="goods-receipt-cancel",
    ),
    path(
        "companies/<int:pk>/purchase-invoices/",
        invoices.InvoiceListView.as_view(),
        name="purchase-invoices",
    ),
    path(
        "companies/<int:pk>/purchase-invoices/draft-from/",
        invoices.InvoiceDraftFromView.as_view(),
        name="purchase-invoice-draft-from",
    ),
    path(
        "companies/<int:pk>/purchase-invoices/unbilled/",
        invoices.UnbilledView.as_view(),
        name="purchase-invoice-unbilled",
    ),
    path(
        "purchase-invoices/<int:pk>/", invoices.InvoiceDetailView.as_view(), name="purchase-invoice"
    ),
    path(
        "purchase-invoices/<int:pk>/cancel/",
        invoices.InvoiceCancelView.as_view(),
        name="purchase-invoice-cancel",
    ),
    path(
        "companies/<int:pk>/purchase-returns/",
        returns.ReturnListView.as_view(),
        name="purchase-returns",
    ),
    path(
        "companies/<int:pk>/purchase-returns/draft-from/",
        returns.ReturnDraftFromView.as_view(),
        name="purchase-return-draft-from",
    ),
    path(
        "companies/<int:pk>/purchase-returns/returnable/",
        returns.ReturnableView.as_view(),
        name="purchase-return-returnable",
    ),
    path("purchase-returns/<int:pk>/", returns.ReturnDetailView.as_view(), name="purchase-return"),
    path(
        "purchase-returns/<int:pk>/cancel/",
        returns.ReturnCancelView.as_view(),
        name="purchase-return-cancel",
    ),
    path("companies/<int:pk>/debit-notes/", debit_notes.NoteListView.as_view(), name="debit-notes"),
    path(
        "companies/<int:pk>/debit-notes/draft-from/",
        debit_notes.NoteDraftFromView.as_view(),
        name="debit-note-draft-from",
    ),
    path("debit-notes/<int:pk>/", debit_notes.NoteDetailView.as_view(), name="debit-note"),
    path(
        "debit-notes/<int:pk>/cancel/",
        debit_notes.NoteCancelView.as_view(),
        name="debit-note-cancel",
    ),
]
