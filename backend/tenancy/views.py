from django.db import connections
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.router import PLATFORM_ALIAS


class HealthView(APIView):
    """Platform-level health check; works without a tenant."""

    # No tenant is selected here, so there is no user or session to look up.
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        with connections[PLATFORM_ALIAS].cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})
