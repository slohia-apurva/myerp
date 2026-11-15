"""QR codes as SVG pictures for labels: a bin label's QR opens that bin's contents on
a phone (Sidharth, 2026-11-15). Drawn with reportlab's encoder, which MyERP already
uses for its PDFs."""

from django.http import HttpResponse
from reportlab.graphics.barcode import qrencoder
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from core.api import Signed


def svg(text: str) -> str:
    code = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    code.addData(text)
    code.make()
    n = code.getModuleCount()
    quiet = 4
    size = n + quiet * 2
    dark = "".join(
        f"M{x + quiet} {y + quiet}h1v1h-1z" for y in range(n) for x in range(n) if code.isDark(y, x)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'shape-rendering="crispEdges"><rect width="{size}" height="{size}" fill="#fff"/>'
        f'<path d="{dark}" fill="#000"/></svg>'
    )


class QrView(APIView):
    """GET ?text=...: the QR code as an SVG picture."""

    permission_classes = [Signed]

    def get(self, request):
        text = request.query_params.get("text", "")
        if not text or len(text) > 300:
            raise ValidationError({"text": ["Give the text for the QR code (up to 300 letters)."]})
        response = HttpResponse(svg(text), content_type="image/svg+xml")
        response["Cache-Control"] = "private, max-age=86400"
        return response
