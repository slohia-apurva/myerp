"""The small image at the top centre of the first page of every printout.

A company ticks "Print Lord Ganesha image" under Printing. The standard line
drawing (core/assets/ganesha.png) is used unless the company uploads its own
PNG or JPG. Purchase orders use their own company's setting; reports, which
are not always for one company, print it when any company in the group has
it ticked (the first such company's image).
"""

from __future__ import annotations

import base64
from functools import cache
from pathlib import Path

from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.context import tenant_atomic

STANDARD = Path(__file__).parent / "assets" / "ganesha.png"
MAX_SIZE = 300 * 1024
TYPES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}


@cache
def standard() -> bytes:
    return STANDARD.read_bytes()


def image_of(company) -> tuple[bytes, str]:
    """The company's chosen image, own or standard, ticked or not."""
    if company.print_image:
        return bytes(company.print_image), company.print_image_type
    return standard(), "image/png"


def data_url(data: bytes, kind: str) -> str:
    return f"data:{kind};base64,{base64.b64encode(data).decode()}"


def mark(company) -> bytes | None:
    """The image to print for this company, or None when it is not ticked."""
    return image_of(company)[0] if company and company.print_ganesha else None


def mark_url(company) -> str:
    return data_url(*image_of(company)) if company and company.print_ganesha else ""


def group_company():
    from core.models import Company

    return Company.objects.filter(print_ganesha=True).order_by("id").first()


def check_upload(data: bytes) -> str:
    if len(data) > MAX_SIZE:
        raise ValidationError({"file": ["The image is over 300 KB; save it smaller."]})
    kind = next((t for magic, t in TYPES.items() if data.startswith(magic)), "")
    if not kind:
        raise ValidationError({"file": ["Upload a PNG or JPG image."]})
    return kind


class PrintImageView(APIView):
    """Upload the company's own image (POST) or go back to the standard one
    (DELETE). Needs the right to edit companies."""

    parser_classes = [MultiPartParser]

    def _company(self, request, pk: int, lock: bool = False):
        from core.api import EDIT, _check, _company

        _check(request, EDIT)
        return _company(request, pk, lock=lock)

    @tenant_atomic()
    def post(self, request, pk: int):
        from core.api import CompanySerializer

        company = self._company(request, pk, lock=True)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["Choose an image."]})
        if upload.size > MAX_SIZE:
            raise ValidationError({"file": ["The image is over 300 KB; save it smaller."]})
        data = upload.read()
        company.print_image_type = check_upload(data)
        company.print_image = data
        company.save(update_fields=["print_image", "print_image_type"])
        return Response(CompanySerializer(company).data)

    @tenant_atomic()
    def delete(self, request, pk: int):
        from core.api import CompanySerializer

        company = self._company(request, pk, lock=True)
        company.print_image = None
        company.print_image_type = ""
        company.save(update_fields=["print_image", "print_image_type"])
        return Response(CompanySerializer(company).data)


class MarkView(APIView):
    """The image for report printouts in the browser: {"mark": data URL or ""}."""

    def get(self, request):
        return Response({"mark": mark_url(group_company())})
