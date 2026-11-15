"""Attachments on entries: files kept with a purchase order, a goods receipt
and every entry screen to come (Sidharth, 2026-11-15).

Each entry type registers once with `register(record_type, find)`, where
`find(request, record_id)` returns the entry (raising NotFound if the person
may not see it) together with whether this person may add or remove files.
Adding and removing files is written to the entry's Activity.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass

from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from core.api import Signed
from core.data_reset import register_entries
from core.models import Attachment
from tenancy.context import tenant_atomic

ALLOWED = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".doc", ".docx", ".xls", ".xlsx"}
INLINE = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
KINDS = dict(Attachment.KINDS)


@dataclass
class Found:
    record: object  # has .company_id and str()
    can_change: bool


_TYPES: dict[str, Callable] = {}
# Entry types a company may tick under "Attachment Needed to Submit", in menu order.
LABELS: dict[str, str] = {}


def register(record_type: str, find: Callable, label: str) -> None:
    _TYPES[record_type] = find
    LABELS[record_type] = label


def check_required(value: list) -> list:
    """The company's "Attachment Needed to Submit" ticks: known entry types only."""
    unknown = [v for v in value if v not in LABELS]
    if unknown:
        raise ValueError(f"Unknown entry type: {', '.join(unknown)}.")
    return [code for code in LABELS if code in value]


def missing_file(record, record_type: str) -> dict | None:
    """The refusal when the company needs a file on this entry type before Submit
    (Sidharth, 2026-11-15) and none is attached yet; None when Submit may go on.
    Saving a draft never needs a file. "id" lets a new form pick up its draft."""
    company = record.company
    if record_type not in (company.attachments_required or []):
        return None
    if record.pk and files_of(record_type, record.pk).exists():
        return None
    label = LABELS.get(record_type, "entry").lower()
    return {
        "attachments": [
            f"Add at least one attachment before Submit: {company.name} needs a file "
            f"on every {label}. Your draft is saved."
        ],
        "id": record.pk,
    }


def require_file(record, record_type: str) -> None:
    refusal = missing_file(record, record_type)
    if refusal:
        raise ValidationError({"attachments": refusal["attachments"]})


def refuse_submit(record, record_type: str) -> Response | None:
    """For a view that saves then submits: answer 400 WITHOUT raising, so the draft
    it just saved is kept."""
    refusal = missing_file(record, record_type)
    return Response(refusal, status=status.HTTP_400_BAD_REQUEST) if refusal else None


def _find(request, record_type: str, record_id) -> Found:
    find = _TYPES.get(record_type)
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        raise NotFound("No such entry.") from None
    if find is None:
        raise NotFound("No such entry.")
    return find(request, record_id)


def _out(a: Attachment) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "kind_label": a.get_kind_display(),
        "filename": a.filename,
        "size": a.size,
        "added_by_name": a.added_by.display_name if a.added_by_id else "",
        "added_at": a.added_at,
    }


def _log(request, found: Found, record_type: str, record_id: int, text: str) -> None:
    user = request.user
    AuditEntry.objects.create(
        user=user,
        user_name=user.display_name[:150],
        company_id=found.record.company_id,
        record_type=record_type,
        record_id=record_id,
        record_name=str(found.record)[:200],
        action=AuditEntry.UPDATE,
        changes=[{"field": "attachments", "label": "Attachments", "old": None, "new": text}],
    )


def files_of(record_type: str, record_id: int):
    return Attachment.objects.filter(record_type=record_type, record_id=record_id)


class AttachmentListView(APIView):
    """GET ?type=goods_receipt&id=5: the entry's files. POST (multipart) type, id,
    file and optionally kind: attach one file (the screen sends each in turn)."""

    permission_classes = [Signed]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        record_type = request.query_params.get("type", "")
        record_id = request.query_params.get("id")
        found = _find(request, record_type, record_id)
        rows = files_of(record_type, int(record_id)).select_related("added_by")
        rows = [_out(a) for a in rows]
        return Response({"can_change": found.can_change, "kinds": Attachment.KINDS, "rows": rows})

    @tenant_atomic()
    def post(self, request):
        record_type = request.data.get("type", "")
        record_id = request.data.get("id")
        found = _find(request, record_type, record_id)
        if not found.can_change:
            raise PermissionDenied("Your role may not add files to this entry.")
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["Choose a file."]})
        name = os.path.basename(upload.name)[:200]
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED:
            raise ValidationError({"file": [f"{name}: attach a PDF, image, Word or Excel file."]})
        if upload.size > Attachment.MAX_SIZE:
            raise ValidationError({"file": [f"{name} is over 10 MB."]})
        kind = request.data.get("kind") or ("photo" if ext in IMAGES else "other")
        if kind not in KINDS:
            raise ValidationError({"kind": ["Pick a type from the list."]})
        made = Attachment.objects.create(
            company_id=found.record.company_id,
            record_type=record_type,
            record_id=int(record_id),
            kind=kind,
            filename=name,
            content_type=upload.content_type or "",
            size=upload.size,
            data=upload.read(),
            added_by=request.user,
        )
        _log(request, found, record_type, int(record_id), f"Added {name} ({KINDS[kind]})")
        return Response(_out(made), status=status.HTTP_201_CREATED)


class AttachmentDetailView(APIView):
    """GET the file itself (PDFs and pictures open in the browser); PATCH {kind};
    DELETE takes a wrong file off (written to the entry's Activity)."""

    permission_classes = [Signed]
    parser_classes = [JSONParser]

    def _attachment(self, request, pk: int) -> tuple[Attachment, Found]:
        a = Attachment.objects.filter(pk=pk).first()
        if a is None:
            raise NotFound("No such file.")
        return a, _find(request, a.record_type, a.record_id)

    def get(self, request, pk: int):
        a, _ = self._attachment(request, pk)
        ext = os.path.splitext(a.filename)[1].lower()
        kind = INLINE.get(ext, "application/octet-stream")
        response = HttpResponse(bytes(a.data), content_type=kind)
        safe = a.filename.replace('"', "").replace("\r", "").replace("\n", "")
        how = "inline" if ext in INLINE else "attachment"
        response["Content-Disposition"] = f'{how}; filename="{safe}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @tenant_atomic()
    def patch(self, request, pk: int):
        a, found = self._attachment(request, pk)
        if not found.can_change:
            raise PermissionDenied("Your role may not change files on this entry.")
        kind = request.data.get("kind")
        if kind not in KINDS:
            raise ValidationError({"kind": ["Pick a type from the list."]})
        if kind != a.kind:
            _log(request, found, a.record_type, a.record_id, f"{a.filename} is now {KINDS[kind]}")
            a.kind = kind
            a.save(update_fields=["kind"])
        return Response(_out(a))

    @tenant_atomic()
    def delete(self, request, pk: int):
        a, found = self._attachment(request, pk)
        if not found.can_change:
            raise PermissionDenied("Your role may not remove files from this entry.")
        _log(request, found, a.record_type, a.record_id, f"Removed {a.filename}")
        a.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _company_files(company):
    rows = Attachment.objects.all()
    return rows.filter(company=company) if company else rows


# Files belong to entries, so the Owner's "Reset data" clears them with the entries.
register_entries(
    "Attachments on entries",
    lambda c: _company_files(c).count(),
    lambda c: _company_files(c).delete(),
)
