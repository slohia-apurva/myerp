"""Requests to add an entry to a central list (an HSN or SAC code, a GST rate),
sent by a customer from a "Request Addition" screen to the MyERP team. The team
sees them on the Central screen (core/central.py)."""

from decimal import Decimal, InvalidOperation

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import EDIT, VIEW, Signed, _check
from tenancy.context import require_tenant
from tenancy.models import CentralRequest, GstRate, HsnCode


class CentralRequestSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CentralRequest
        fields = [
            "id",
            "kind",
            "kind_label",
            "entry",
            "description",
            "note",
            "requested_by",
            "status",
            "status_label",
            "created_at",
            "seen",
        ]
        read_only_fields = ["id", "requested_by", "status", "created_at"]


def clean_entry(kind: str, entry: str) -> str:
    """The code or rate as it will be compared and shown; refuses one that is
    malformed or already in the list."""
    entry = entry.strip()
    if kind == CentralRequest.HSN:
        code = entry.replace(" ", "")
        if not code.isdigit() or not 2 <= len(code) <= 8:
            raise ValidationError({"entry": ["An HSN or SAC code is 2 to 8 digits."]})
        if HsnCode.objects.filter(hsn_code=code).exists():
            raise ValidationError({"entry": [f"{code} is already in the HSN list."]})
        return code
    try:
        rate = Decimal(entry)
    except InvalidOperation as exc:
        raise ValidationError({"entry": ["Give the GST rate as a number, such as 18."]}) from exc
    if not 0 <= rate <= 100:
        raise ValidationError({"entry": ["A GST rate is between 0 and 100."]})
    if GstRate.objects.filter(rate=rate).exists():
        raise ValidationError({"entry": [f"{rate.normalize():f}% is already in the GST rates."]})
    return f"{rate.normalize():f}"


class CentralRequestListView(APIView):
    """A customer's own requests (GET) and a new request (POST)."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        rows = CentralRequest.objects.filter(tenant=require_tenant())
        return Response(CentralRequestSerializer(rows, many=True).data)

    def post(self, request):
        _check(request, EDIT)
        serializer = CentralRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenant = require_tenant()
        entry = clean_entry(data["kind"], data["entry"])
        clash = CentralRequest.objects.filter(
            tenant=tenant, kind=data["kind"], entry__iexact=entry, status=CentralRequest.OPEN
        ).first()
        if clash:
            raise ValidationError(
                {"entry": [f"There is already an open request for {entry}; the team has it."]}
            )
        row = CentralRequest.objects.create(
            tenant=tenant,
            kind=data["kind"],
            entry=entry,
            description=data.get("description", "").strip(),
            note=data.get("note", "").strip(),
            requested_by=request.user.email,
        )
        return Response(CentralRequestSerializer(row).data, status=status.HTTP_201_CREATED)


class CentralRequestSeenView(APIView):
    """The requester dismisses the notice about a decision."""

    permission_classes = [Signed]

    def post(self, request, pk: int):
        _check(request, VIEW)
        updated = CentralRequest.objects.filter(pk=pk, tenant=require_tenant()).update(seen=True)
        if not updated:
            raise NotFound("No such request.")
        return Response({"seen": True})


def add_to_list(row: CentralRequest) -> None:
    """Put the requested entry in its central list (no-op if it is already there)."""
    if row.kind == CentralRequest.HSN:
        if not row.description.strip():
            raise ValidationError(
                {"status": ["This request has no description; add the code from Shared lists."]}
            )
        HsnCode.objects.get_or_create(
            hsn_code=row.entry, defaults={"description": row.description.strip()[:500]}
        )
    else:
        GstRate.objects.get_or_create(rate=Decimal(row.entry))
