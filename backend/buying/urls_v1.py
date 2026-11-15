from django.urls import path

from buying import api, receipts

urlpatterns = [
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
]
