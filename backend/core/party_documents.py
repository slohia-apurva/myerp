"""Documents kept for a customer or supplier (GST certificate, FSSAI licence,
agreement, cancelled cheque), each with a renewal date and attached files.

Files live in the tenant's own database. A document is never deleted: use
`is_active` to hide it; a renewal is a new document.
"""

import datetime
import os

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import EDIT, VIEW, Signed
from core.models import Party, PartyDocument, PartyDocumentFile
from tenancy.context import tenant_atomic

ALLOWED = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"}
INLINE = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
SOON_DAYS = 90


def _check(request, code: str) -> None:
    if not request.user.can(code):
        raise PermissionDenied("Your role does not allow this.")


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartyDocumentFile
        fields = ["id", "filename", "size", "uploaded_at"]


class DocumentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    files = FileSerializer(many=True, read_only=True)

    class Meta:
        model = PartyDocument
        fields = [
            "id",
            "kind",
            "kind_label",
            "name",
            "number",
            "issued_by",
            "address_label",
            "valid_from",
            "valid_until",
            "notes",
            "is_active",
            "files",
        ]


FIELDS = [f for f in DocumentSerializer.Meta.fields if f not in ("id", "kind_label", "files")]


def _party(pk: int) -> Party:
    party = Party.objects.filter(pk=pk).first()
    if party is None:
        raise NotFound("No such customer or supplier.")
    return party


def _save(document: PartyDocument, data: dict) -> PartyDocument:
    for field in FIELDS:
        if field in data:
            setattr(document, field, data[field])
    try:
        document.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    document.save()
    return document


class DocumentListView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        docs = _party(pk).documents.prefetch_related("files")
        return Response(DocumentSerializer(docs, many=True).data)

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        party = _party(pk)
        serializer = DocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = _save(PartyDocument(party=party), dict(serializer.validated_data))
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


def _document(pk: int) -> PartyDocument:
    document = PartyDocument.objects.select_for_update().filter(pk=pk).first()
    if document is None:
        raise NotFound("No such document.")
    return document


class DocumentDetailView(APIView):
    """Change or disable only: documents are never deleted."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        document = _document(pk)
        serializer = DocumentSerializer(document, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save(document, dict(serializer.validated_data))
        return Response(DocumentSerializer(document).data)


class FileUploadView(APIView):
    """Attach one file (the screen sends each file in turn)."""

    permission_classes = [Signed]
    parser_classes = [MultiPartParser]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        document = _document(pk)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["Choose a file."]})
        name = os.path.basename(upload.name)[:200]
        if os.path.splitext(name)[1].lower() not in ALLOWED:
            raise ValidationError({"file": ["Attach a PDF, image (JPG, PNG), Word or Excel file."]})
        if upload.size > PartyDocumentFile.MAX_SIZE:
            raise ValidationError({"file": [f"{name} is over 10 MB."]})
        made = PartyDocumentFile.objects.create(
            document=document,
            filename=name,
            content_type=upload.content_type or "",
            size=upload.size,
            data=upload.read(),
            uploaded_by=request.user,
        )
        return Response(FileSerializer(made).data, status=status.HTTP_201_CREATED)


class FileView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        file = PartyDocumentFile.objects.filter(pk=pk).first()
        if file is None:
            raise NotFound("No such file.")
        ext = os.path.splitext(file.filename)[1].lower()
        inline = ext in INLINE
        response = HttpResponse(
            bytes(file.data),
            content_type=INLINE.get(ext, "application/octet-stream"),
        )
        safe = file.filename.replace('"', "").replace("\r", "").replace("\n", "")
        kind = "inline" if inline else "attachment"
        response["Content-Disposition"] = f'{kind}; filename="{safe}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @tenant_atomic()
    def delete(self, request, pk: int):
        """Take a wrong file off a document (the document itself stays)."""
        _check(request, EDIT)
        file = PartyDocumentFile.objects.filter(pk=pk).first()
        if file is None:
            raise NotFound("No such file.")
        file.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RenewalsView(APIView):
    """Documents of customers and suppliers that have lapsed or lapse within
    90 days, for the Dashboard. Only the latest of each (party, kind, name)
    counts, so a renewed document hides the old one."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        today = datetime.date.today()
        latest: dict[tuple, PartyDocument] = {}
        docs = PartyDocument.objects.filter(is_active=True, valid_until__isnull=False)
        for d in docs.select_related("party").order_by("valid_until"):
            latest[(d.party_id, d.kind, d.name.lower(), d.address_label.lower())] = d
        soon = today + datetime.timedelta(days=SOON_DAYS)
        rows = [
            {
                "id": d.pk,
                "party_id": d.party_id,
                "party": d.party.name,
                "kind_label": d.get_kind_display(),
                "name": d.name,
                "valid_until": d.valid_until,
            }
            for d in latest.values()
            if d.valid_until <= soon
        ]
        rows.sort(key=lambda r: r["valid_until"])
        return Response(rows)
