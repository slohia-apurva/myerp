"""HSN / SAC codes: the group's list, searched as people type an item's HSN.
The list is loaded from the official one by an import (CSV rows of code and
description), so MyERP does not call any outside service when searching."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import EDIT, VIEW, Signed, _check
from core.models import HsnCode
from tenancy.context import tenant_atomic

SEARCH_LIMIT = 30
IMPORT_LIMIT = 30000


class HsnSerializer(serializers.ModelSerializer):
    class Meta:
        model = HsnCode
        fields = ["id", "hsn_code", "description", "is_active"]


def _clean(code: str, description: str) -> tuple[str, str]:
    return code.strip().replace(" ", ""), " ".join(description.split())


def _save(hsn: HsnCode, data: dict) -> None:
    if "hsn_code" in data:
        code, _ = _clean(data["hsn_code"], "")
        if hsn.pk and code != hsn.hsn_code:
            raise ValidationError(
                {"hsn_code": ["A code cannot be changed; add the new one instead."]}
            )
        hsn.hsn_code = code
        if HsnCode.objects.filter(hsn_code=code).exclude(pk=hsn.pk).exists():
            raise ValidationError({"hsn_code": ["This code is already in the list."]})
    if "description" in data:
        hsn.description = _clean("", data["description"])[1]
    if "is_active" in data:
        hsn.is_active = data["is_active"]
    try:
        hsn.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    hsn.save()


def search(q: str, active_only: bool, limit: int | None = None):
    rows = HsnCode.objects.all()
    if active_only:
        rows = rows.filter(is_active=True)
    q = q.strip()
    if q:
        if q.replace(" ", "").isdigit():
            rows = rows.filter(hsn_code__startswith=q.replace(" ", ""))
        else:
            for word in q.split():
                rows = rows.filter(Q(description__icontains=word) | Q(hsn_code__startswith=word))
    rows = rows.order_by("hsn_code")
    return rows[:limit] if limit else rows


class HsnListView(APIView):
    """GET ?q=text&active=1 (at most 30 rows when searching for the picker)."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        active = request.query_params.get("active") == "1"
        limit = SEARCH_LIMIT if request.query_params.get("limit") == "pick" else 500
        rows = search(request.query_params.get("q", ""), active, limit)
        return Response(
            {
                "total": HsnCode.objects.count(),
                "results": HsnSerializer(rows, many=True).data,
            }
        )

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = HsnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hsn = HsnCode()
        _save(hsn, dict(serializer.validated_data))
        return Response(HsnSerializer(hsn).data, status=status.HTTP_201_CREATED)


class HsnDetailView(APIView):
    """Edit only: codes are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        hsn = HsnCode.objects.select_for_update().filter(pk=pk).first()
        if hsn is None:
            raise NotFound("No such HSN code.")
        serializer = HsnSerializer(hsn, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save(hsn, dict(serializer.validated_data))
        return Response(HsnSerializer(hsn).data)


class HsnImportView(APIView):
    """POST {"rows": [{"hsn_code": "1701", "description": "..."}]}: adds new codes
    and refreshes the description of ones already there. A bad row stops the
    whole import, so the list is never half loaded."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        rows = request.data.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ValidationError({"rows": ["Give the rows to import."]})
        if len(rows) > IMPORT_LIMIT:
            raise ValidationError({"rows": [f"Import at most {IMPORT_LIMIT} rows at a time."]})
        wanted: dict[str, str] = {}
        for n, row in enumerate(rows, 1):
            code, description = _clean(
                str(row.get("hsn_code", "")), str(row.get("description", ""))
            )
            probe = HsnCode(hsn_code=code, description=description)
            try:
                probe.clean()
            except DjangoValidationError as exc:
                raise ValidationError(
                    {"rows": [f"Row {n} ({code or 'blank'}): {exc.messages[0]}"]}
                ) from exc
            if not description:
                raise ValidationError({"rows": [f"Row {n} ({code}): the description is blank."]})
            wanted[code] = description[:500]
        have = {h.hsn_code: h for h in HsnCode.objects.filter(hsn_code__in=wanted)}
        new, changed = [], []
        for code, description in wanted.items():
            if code in have:
                if have[code].description != description:
                    have[code].description = description
                    changed.append(have[code])
            else:
                new.append(HsnCode(hsn_code=code, description=description))
        HsnCode.objects.bulk_create(new)
        HsnCode.objects.bulk_update(changed, ["description"])
        return Response(
            {
                "added": len(new),
                "updated": len(changed),
                "unchanged": len(wanted) - len(new) - len(changed),
            }
        )
