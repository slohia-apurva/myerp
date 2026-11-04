from django.db import connections
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.router import PLATFORM_ALIAS


class HealthView(APIView):
    """Platform-level health check; works without a tenant."""

    def get(self, request):
        with connections[PLATFORM_ALIAS].cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})
