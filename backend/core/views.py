from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Company


class WhoAmIView(APIView):
    """Which tenant this request reached, and the companies it can see."""

    def get(self, request):
        return Response(
            {
                "tenant": request.tenant.slug,
                "name": request.tenant.name,
                "companies": list(Company.objects.values_list("name", flat=True)),
            }
        )
