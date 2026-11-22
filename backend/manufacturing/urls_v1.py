from django.urls import path

from manufacturing import boms, orders, picks

urlpatterns = [
    path("boms/", boms.BomListView.as_view(), name="boms"),
    path("boms/<int:pk>/", boms.BomDetailView.as_view(), name="bom"),
    path("boms/<int:pk>/make-default/", boms.BomMakeDefaultView.as_view(), name="bom-default"),
    path(
        "companies/<int:pk>/manufacturing-orders/",
        orders.OrderListView.as_view(),
        name="manufacturing-orders",
    ),
    path(
        "companies/<int:pk>/manufacturing-orders/form/",
        orders.OrderFormView.as_view(),
        name="manufacturing-order-form",
    ),
    path(
        "companies/<int:pk>/manufacturing-orders/materials/",
        orders.OrderMaterialsView.as_view(),
        name="manufacturing-order-materials",
    ),
    path("manufacturing-orders/<int:pk>/", orders.OrderDetailView.as_view(), name="mo"),
    path("manufacturing-orders/<int:pk>/submit/", orders.OrderSubmitView.as_view()),
    path("manufacturing-orders/<int:pk>/cancel/", orders.OrderCancelView.as_view()),
    path("manufacturing-orders/<int:pk>/close/", orders.OrderCloseView.as_view()),
    path("manufacturing-orders/<int:pk>/pdf/", orders.OrderPdfView.as_view()),
    path("manufacturing-orders/<int:pk>/picks/", picks.PicksView.as_view()),
    path("manufacturing-orders/<int:pk>/pick-again/", picks.PickAgainView.as_view()),
    path("manufacturing-orders/<int:pk>/places/", picks.PlacesView.as_view()),
    path("manufacturing-orders/<int:pk>/pick-list/", picks.PickPdfView.as_view()),
]
