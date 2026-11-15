"""Look a GSTIN up on the GST portal, through a GST Suvidha Provider (GSP).

The portal has no public lookup, so this needs a provider account. Until one
is connected (settings.GSTIN_LOOKUP_PROVIDER, a dotted path to a function that
takes a GSTIN and returns a dict), the endpoint says it is not set up, and
the screens still work: the state and PAN come from the number itself.

The provider function returns any of: legal_name, trade_name, status,
gst_type, address, pincode, city, or raises LookupFailed (or NotSetUp). State and
PAN are worked out here, and the city is the PIN's city from the central
PIN list (as an address takes it on save), else the provider's city.
The connected provider is core.gstinapi (gstinapi.in), which reads its key
from the GSTINAPI_KEY environment variable.
"""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.module_loading import import_string
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import india
from core.api import VIEW, Signed, _check
from tenancy.models import PinCode


class NotSetUp(APIException):
    status_code = 503
    default_detail = (
        "GST lookup is not set up yet. Enter the details by hand; the state and PAN are "
        "filled in from the GSTIN."
    )
    default_code = "gst_lookup_not_set_up"


class LookupFailed(APIException):
    """The provider could not give the details; `detail` says why in plain words."""

    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.status_code = status_code


class GstinLookupView(APIView):
    """GET /gstin-lookup/?gstin=27ABCPE1234F1ZB"""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        gstin = request.query_params.get("gstin", "").strip().upper()
        try:
            india.validate_gstin(gstin)
        except DjangoValidationError as exc:
            raise ValidationError({"gstin": exc.messages}) from exc
        provider = getattr(settings, "GSTIN_LOOKUP_PROVIDER", "")
        if not provider:
            raise NotSetUp()
        found = import_string(provider)(gstin) or {}
        if not found:
            raise ValidationError({"gstin": ["The GST portal has no registration for this GSTIN."]})
        pincode = (found.get("pincode") or "").strip()
        listed = PinCode.objects.filter(pin=pincode, is_active=True).first() if pincode else None
        return Response(
            {
                "gstin": gstin,
                "state_code": gstin[:2],
                "pan": gstin[2:12],
                "legal_name": found.get("legal_name", ""),
                "trade_name": found.get("trade_name", ""),
                "status": found.get("status", ""),
                "gst_type": found.get("gst_type", "regular"),
                "address": found.get("address", ""),
                "pincode": pincode,
                "city": (listed.city if listed and listed.city else found.get("city", "")),
            }
        )
