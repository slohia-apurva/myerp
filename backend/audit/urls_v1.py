from django.urls import path

from audit import api

urlpatterns = [path("audit/", api.AuditLogView.as_view(), name="audit")]
