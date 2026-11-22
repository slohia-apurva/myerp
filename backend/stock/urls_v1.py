from django.urls import path

from stock import transfers

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
]
