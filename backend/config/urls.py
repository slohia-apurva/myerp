from django.urls import include, path

from core.views import WhoAmIView
from tenancy.views import HealthView

urlpatterns = [
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/whoami/", WhoAmIView.as_view(), name="whoami"),
]
