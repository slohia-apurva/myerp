"""Batches: the lots of batch-tracked items, with mfg date, expiry and quality
status (design rule 12). Items are shared by the group, so batches are too.
A goods receipt line can make a new batch as it is received (Sidharth,
2026-11-15); this module's `save_batch` is the one save path for both."""

import calendar
import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import Batch, Item
from tenancy.context import tenant_atomic


def add_months(day: datetime.date, months: int) -> datetime.date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last))


def expiry_from(item: Item, mfg: datetime.date | None) -> datetime.date | None:
    """The best-before date: the mfg date plus the item's best-before period."""
    if mfg is None or not item.best_before_value:
        return None
    if item.best_before_unit == Item.MONTHS:
        return add_months(mfg, item.best_before_value)
    return mfg + datetime.timedelta(days=item.best_before_value)


class BatchSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_number = serializers.CharField(source="item.item_number", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Batch
        fields = [
            "id",
            "item",
            "item_name",
            "item_number",
            "number",
            "supplier_batch_no",
            "mfg_date",
            "expiry_date",
            "status",
            "status_label",
            "notes",
            "is_active",
        ]


def save_batch(batch: Batch, data: dict) -> Batch:
    """Add or change a batch, with every check its screen makes."""
    item = data.get("item", batch.item if batch.item_id else None)
    if item is None:
        raise ValidationError({"item": ["Pick the item."]})
    if not item.batch_tracked:
        raise ValidationError(
            {"item": [f'{item.name} is not batch-tracked (tick "Track batches" on the item).']}
        )
    if "number" in data:
        data["number"] = duplicates.tidy(data["number"])
        if not data["number"]:
            raise ValidationError({"number": ["Give the batch number."]})
        duplicates.check_name(
            Batch.objects.filter(item=item),
            data["number"],
            field="number",
            exclude=batch.pk,
            kind="batch",
            message=f'{item.name} already has a batch "{{name}}".',
        )
    refuse_key_changes("batch", batch, data)
    for field in (
        "item",
        "number",
        "supplier_batch_no",
        "mfg_date",
        "expiry_date",
        "status",
        "notes",
        "is_active",
    ):
        if field in data:
            setattr(batch, field, data[field])
    if batch.expiry_date is None:  # blank means "work it out"
        batch.expiry_date = expiry_from(item, batch.mfg_date)
    try:
        batch.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    batch.save()
    return batch


def _batches():
    return Batch.objects.select_related("item").order_by("item__name", "number")


exchange.register(
    exchange.Master(
        key="batches",
        label="Batches",
        noun="batch",
        serializer=BatchSerializer,
        queryset=lambda ctx: _batches(),
        save=lambda ctx, batch, data: save_batch(batch or Batch(), data),
        exclude=("item_name", "item_number", "status_label"),
        hints={
            "status": "Quarantine, Released or Rejected",
            "expiry_date": "Blank: worked out from the mfg date and the item's best-before",
        },
    )
)


class BatchListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        rows = _batches()
        item = request.query_params.get("item")
        if item:
            rows = rows.filter(item_id=item)
        return Response(BatchSerializer(rows, many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = BatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = save_batch(Batch(), dict(serializer.validated_data))
        return Response(BatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class BatchDetailView(APIView):
    """Edit only: batches are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        batch = Batch.objects.select_for_update().filter(pk=pk).first()
        if batch is None:
            raise NotFound("No such batch.")
        serializer = BatchSerializer(batch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        save_batch(batch, dict(serializer.validated_data))
        return Response(BatchSerializer(_batches().get(pk=batch.pk)).data)
