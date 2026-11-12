"""The central admin screen: the tables MyERP keeps once for every customer in
the platform database (HSN codes today; states, countries and PIN codes next),
and the list of customers (tenants). For platform admins only: the people whose
sign-in emails are in MYERP_PLATFORM_ADMINS. A customer's Owner is not one."""

import re

from django.conf import settings
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import duplicates
from core.api import Signed
from tenancy.models import Carrier, HsnCode, Tenant

# key, label, what it is for, model, screen to open (a hash route) or "".
CENTRAL_TABLES = [
    ("hsn", "HSN codes", "HSN and SAC codes searched on the item form.", HsnCode, "#/hsn"),
    (
        "carriers",
        "Couriers",
        "Couriers, aggregators and transporters every customer can pick when adding a transporter.",
        Carrier,
        "",
    ),
    (
        "tenants",
        "Customers (tenants)",
        "Each group of companies, with its own database.",
        Tenant,
        "",
    ),
]


def is_platform_admin(user) -> bool:
    emails = {e.strip().lower() for e in settings.MYERP_PLATFORM_ADMINS.split(",") if e.strip()}
    return bool(user and user.is_authenticated and user.email.lower() in emails)


class CentralView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        if not is_platform_admin(request.user):
            raise PermissionDenied("Only MyERP platform admins can open this.")
        return Response(
            {
                "tables": [
                    {
                        "key": k,
                        "label": label,
                        "about": about,
                        "count": model.objects.count(),
                        "open": link,
                    }
                    for k, label, about, model, link in CENTRAL_TABLES
                ],
                "tenants": [
                    {
                        "slug": t.slug,
                        "name": t.name,
                        "status": t.get_status_display(),
                        "created": t.created_at.date().isoformat(),
                    }
                    for t in Tenant.objects.all()
                ],
            }
        )


def _platform_admin(request) -> None:
    if not is_platform_admin(request.user):
        raise PermissionDenied("Only MyERP platform admins can open this.")


class CarrierAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carrier
        fields = ["id", "name", "kind", "awb_pattern", "awb_hint", "tracking_url", "is_active"]

    def validate_name(self, value):
        return duplicates.tidy(value)

    def validate_awb_pattern(self, value):
        try:
            re.compile(value)
        except re.error as exc:
            raise serializers.ValidationError(f"This is not a valid pattern: {exc}") from exc
        return value

    def validate_tracking_url(self, value):
        if value and (not value.startswith("https://") or "{awb}" not in value):
            raise serializers.ValidationError(
                "Give the courier's tracking page starting with https:// and with {awb} "
                "where the tracking number goes."
            )
        return value


def _refuse_same_name(name: str, exclude=None) -> None:
    clash = Carrier.objects.filter(name__iexact=name).exclude(pk=exclude).first()
    if clash:
        raise ValidationError({"name": [f'There is already a courier named "{clash.name}".']})


class CarrierAdminListView(APIView):
    """The central list of couriers, aggregators and transporters. Every
    customer picks from it; only platform admins add to it, because each one
    is a carrier MyERP can look up (tracking page, AWB check, PIN coverage and,
    later, its API). Never deleted, only disabled."""

    permission_classes = [Signed]

    def get(self, request):
        _platform_admin(request)
        return Response(CarrierAdminSerializer(Carrier.objects.all(), many=True).data)

    def post(self, request):
        _platform_admin(request)
        serializer = CarrierAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _refuse_same_name(serializer.validated_data["name"])
        with transaction.atomic():
            carrier = serializer.save()
        return Response(CarrierAdminSerializer(carrier).data, status=status.HTTP_201_CREATED)


class CarrierAdminDetailView(APIView):
    permission_classes = [Signed]

    def patch(self, request, pk: int):
        _platform_admin(request)
        carrier = Carrier.objects.filter(pk=pk).first()
        if carrier is None:
            raise NotFound("No such courier.")
        serializer = CarrierAdminSerializer(carrier, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "name" in serializer.validated_data:
            _refuse_same_name(serializer.validated_data["name"], exclude=carrier.pk)
        with transaction.atomic():
            serializer.save()
        return Response(CarrierAdminSerializer(carrier).data)
