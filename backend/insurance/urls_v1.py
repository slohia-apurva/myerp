from django.urls import path

from insurance import api

urlpatterns = [
    path(
        "companies/<int:pk>/insurance-policies/",
        api.PolicyListView.as_view(),
        name="insurance-policies",
    ),
    path(
        "companies/<int:pk>/insurance-policies/setup/",
        api.PolicySetupView.as_view(),
        name="insurance-policy-setup",
    ),
    path("insurance-policies/<int:pk>/", api.PolicyDetailView.as_view(), name="insurance-policy"),
]
