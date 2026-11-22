from django.urls import path

from stock import customer, own_use, transfers

urlpatterns = [
    path(
        "companies/<int:pk>/stock-transfers/",
        transfers.TransferListView.as_view(),
        name="stock-transfers",
    ),
    path(
        "companies/<int:pk>/stock-transfers/form/",
        transfers.TransferFormView.as_view(),
        name="stock-transfer-form",
    ),
    path(
        "stock-transfers/<int:pk>/", transfers.TransferDetailView.as_view(), name="stock-transfer"
    ),
    path(
        "stock-transfers/<int:pk>/dispatch/",
        transfers.TransferDispatchView.as_view(),
        name="stock-transfer-dispatch",
    ),
    path(
        "stock-transfers/<int:pk>/receive/",
        transfers.TransferReceiveView.as_view(),
        name="stock-transfer-receive",
    ),
    path(
        "stock-transfers/<int:pk>/cancel/",
        transfers.TransferCancelView.as_view(),
        name="stock-transfer-cancel",
    ),
    path(
        "stock-transfers/<int:pk>/stock-posting/",
        transfers.TransferPostingView.as_view(),
        name="stock-transfer-posting",
    ),
    path(
        "stock-transfers/<int:pk>/pdf/",
        transfers.TransferPdfView.as_view(),
        name="stock-transfer-pdf",
    ),
    path(
        "companies/<int:pk>/customer-stock/",
        customer.EntryListView.as_view(),
        name="customer-stock",
    ),
    path(
        "companies/<int:pk>/customer-stock/form/",
        customer.EntryFormView.as_view(),
        name="customer-stock-form",
    ),
    path("customer-stock/<int:pk>/", customer.EntryDetailView.as_view(), name="customer-stock-one"),
    path(
        "customer-stock/<int:pk>/submit/",
        customer.EntrySubmitView.as_view(),
        name="customer-stock-submit",
    ),
    path(
        "customer-stock/<int:pk>/cancel/",
        customer.EntryCancelView.as_view(),
        name="customer-stock-cancel",
    ),
    path(
        "customer-stock/<int:pk>/pdf/", customer.EntryPdfView.as_view(), name="customer-stock-pdf"
    ),
    path("companies/<int:pk>/own-use/", own_use.OwnUseListView.as_view(), name="own-use-list"),
    path("companies/<int:pk>/own-use/form/", own_use.OwnUseFormView.as_view(), name="own-use-form"),
    path("own-use/<int:pk>/", own_use.OwnUseDetailView.as_view(), name="own-use"),
    path("own-use/<int:pk>/submit/", own_use.OwnUseSubmitView.as_view(), name="own-use-submit"),
    path("own-use/<int:pk>/cancel/", own_use.OwnUseCancelView.as_view(), name="own-use-cancel"),
    path(
        "own-use/<int:pk>/ledger-posting/",
        own_use.OwnUsePostingView.as_view(),
        name="own-use-posting",
    ),
    path("own-use/<int:pk>/pdf/", own_use.OwnUsePdfView.as_view(), name="own-use-pdf"),
]
