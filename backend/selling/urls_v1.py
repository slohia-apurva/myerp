from django.urls import path

from selling import api, customer_mail

urlpatterns = [
    path("companies/<int:pk>/sales-orders/", api.OrderListView.as_view(), name="sales-orders"),
    path(
        "companies/<int:pk>/sales-orders/setup/",
        api.OrderSetupView.as_view(),
        name="sales-order-setup",
    ),
    path(
        "companies/<int:pk>/sales-orders/items/",
        api.OrderItemsView.as_view(),
        name="sales-order-items",
    ),
    path(
        "companies/<int:pk>/sales-orders/rate/",
        api.OrderRateView.as_view(),
        name="sales-order-rate",
    ),
    path(
        "companies/<int:pk>/sales-orders/credit/",
        api.CreditView.as_view(),
        name="sales-order-credit",
    ),
    path("sales-orders/<int:pk>/", api.OrderDetailView.as_view(), name="sales-order"),
    path("sales-orders/<int:pk>/submit/", api.OrderSubmitView.as_view(), name="sales-order-submit"),
    path("sales-orders/<int:pk>/cancel/", api.OrderCancelView.as_view(), name="sales-order-cancel"),
    path(
        "sales-orders/<int:pk>/lines/<int:line>/close/",
        api.OrderLineCloseView.as_view(),
        name="sales-order-line-close",
    ),
    path(
        "sales-orders/<int:pk>/pdf/", customer_mail.OrderPdfView.as_view(), name="sales-order-pdf"
    ),
    path(
        "sales-orders/<int:pk>/mail/",
        customer_mail.OrderMailView.as_view(),
        name="sales-order-mail",
    ),
]
