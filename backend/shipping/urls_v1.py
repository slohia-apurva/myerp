from django.urls import path

from shipping import api

urlpatterns = [
    path("carriers/", api.CarrierListView.as_view(), name="carriers"),
    path(
        "companies/<int:pk>/courier-accounts/",
        api.CourierAccountListView.as_view(),
        name="courier-accounts",
    ),
    path(
        "courier-accounts/<int:pk>/", api.CourierAccountDetailView.as_view(), name="courier-account"
    ),
    path("companies/<int:pk>/shipments/", api.ShipmentListView.as_view(), name="shipments"),
    path("shipments/<int:pk>/", api.ShipmentDetailView.as_view(), name="shipment"),
    path("shipments/<int:pk>/events/", api.ShipmentEventView.as_view(), name="shipment-events"),
    path("shipments/<int:pk>/cancel/", api.ShipmentCancelView.as_view(), name="shipment-cancel"),
]
