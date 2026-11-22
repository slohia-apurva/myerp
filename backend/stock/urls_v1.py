from django.urls import path

from stock import customer, transfers

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
]
