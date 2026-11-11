"""Brands: the group's list of brand names, shared by every company. An item
picks its brand on the General tab."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import Brand
from tenancy.context import tenant_atomic


class BrandSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Brand
        fields = ["id", "name", "notes", "is_active", "item_count"]


def _save_brand(brand: Brand, data: dict) -> Brand:
    if "name" in data:
        data["name"] = data["name"].strip()
        clash = Brand.objects.filter(name__iexact=data["name"])
        if brand.pk:
            clash = clash.exclude(pk=brand.pk)
        if clash.exists():
            raise ValidationError({"name": ["There is already a brand with this name."]})
    refuse_key_changes("brand", brand, data)
    for field in ("name", "notes", "is_active"):
        if field in data:
            setattr(brand, field, data[field])
    try:
        brand.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    brand.save()
    return brand


exchange.register(
    exchange.Master(
        key="brands",
        label="Brands",
        noun="brand",
        serializer=BrandSerializer,
        queryset=lambda ctx: Brand.objects.order_by("name"),
        save=lambda ctx, brand, data: _save_brand(brand or Brand(), data),
        exclude=("item_count",),
    )
)


def _brands():
    return Brand.objects.annotate(item_count=Count("items")).order_by("name")


class BrandListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(BrandSerializer(_brands(), many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = BrandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        brand = Brand()
        _save_brand(brand, dict(serializer.validated_data))
        return Response(
            BrandSerializer(_brands().get(pk=brand.pk)).data, status=status.HTTP_201_CREATED
        )


class BrandDetailView(APIView):
    """Edit only: brands are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        brand = Brand.objects.select_for_update().filter(pk=pk).first()
        if brand is None:
            raise NotFound("No such brand.")
        serializer = BrandSerializer(brand, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_brand(brand, dict(serializer.validated_data))
        return Response(BrandSerializer(_brands().get(pk=brand.pk)).data)
