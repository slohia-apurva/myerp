from django.urls import path

from manufacturing import boms

urlpatterns = [
    path("boms/", boms.BomListView.as_view(), name="boms"),
    path("boms/<int:pk>/", boms.BomDetailView.as_view(), name="bom"),
    path("boms/<int:pk>/make-default/", boms.BomMakeDefaultView.as_view(), name="bom-default"),
]
