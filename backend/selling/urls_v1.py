from django.urls import path

from selling import api, customer_mail, delivery, pick_lists

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
    path(
        "sales-orders/<int:pk>/pick-list/",
        pick_lists.OrderPickView.as_view(),
        name="sales-order-pick-list",
    ),
    path("companies/<int:pk>/pick-lists/", pick_lists.PickListView.as_view(), name="pick-lists"),
    path("pick-lists/<int:pk>/", pick_lists.PickDetailView.as_view(), name="pick-list"),
    path(
        "pick-lists/<int:pk>/submit/", pick_lists.PickSubmitView.as_view(), name="pick-list-submit"
    ),
    path(
        "pick-lists/<int:pk>/cancel/", pick_lists.PickCancelView.as_view(), name="pick-list-cancel"
    ),
    path(
        "pick-lists/<int:pk>/places/", pick_lists.PickPlacesView.as_view(), name="pick-list-places"
    ),
    path(
        "pick-lists/<int:pk>/despatch/",
        pick_lists.PickDespatchView.as_view(),
        name="pick-list-despatch",
    ),
    path("pick-lists/<int:pk>/pdf/", pick_lists.PickPdfView.as_view(), name="pick-list-pdf"),
    path(
        "pick-lists/<int:pk>/delivery-note/",
        delivery.NoteFromPickView.as_view(),
        name="pick-list-delivery-note",
    ),
    path(
        "companies/<int:pk>/delivery-notes/", delivery.NoteListView.as_view(), name="delivery-notes"
    ),
    path("delivery-notes/<int:pk>/", delivery.NoteDetailView.as_view(), name="delivery-note"),
    path(
        "delivery-notes/<int:pk>/submit/",
        delivery.NoteSubmitView.as_view(),
        name="delivery-note-submit",
    ),
    path(
        "delivery-notes/<int:pk>/cancel/",
        delivery.NoteCancelView.as_view(),
        name="delivery-note-cancel",
    ),
    path(
        "delivery-notes/<int:pk>/ledger-posting/",
        delivery.NoteLedgerPostingView.as_view(),
        name="delivery-note-posting",
    ),
    path(
        "delivery-notes/<int:pk>/places/",
        delivery.NotePlacesView.as_view(),
        name="delivery-note-places",
    ),
    path("delivery-notes/<int:pk>/pdf/", delivery.NotePdfView.as_view(), name="delivery-note-pdf"),
]
