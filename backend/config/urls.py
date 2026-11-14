from django.urls import include, path

from core.views import WhoAmIView
from tenancy.views import HealthView

urlpatterns = [
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/auth/", include("accounts.urls")),
    # Versioned API for screens and, later, the mobile app (decision 0011).
    path("api/v1/", include("accounts.urls_v1")),
    path("api/v1/", include("core.urls_v1")),
    path("api/v1/", include("audit.urls_v1")),
    path("api/v1/", include("shipping.urls_v1")),
    path("api/v1/", include("buying.urls_v1")),
    path("api/whoami/", WhoAmIView.as_view(), name="whoami"),
]
