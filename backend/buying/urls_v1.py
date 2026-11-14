from django.urls import path

from buying import api

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
]
