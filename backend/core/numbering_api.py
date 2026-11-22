"""The Numbering tab of a company: the group's master numbers (customer,
vendor, item) and the company's document series, one counter per fiscal year.

Master numbers are shared by every company. A document series has a prefix
(with `{YY}` for the short fiscal year, 2627, or `{FY}` for 2026-27) and a
width; a branch can have its own series for a kind of document. Once a series
has handed out a number its prefix and width are fixed; the last number can
only go up (to carry on from numbers used before MyERP).
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import data_reset, duplicates, exchange, numbering
from core.api import EDIT, VIEW, Signed, _check, _company
from core.companies import visible_companies
from core.locks import refuse_key_changes
from core.locks import register as register_in_use
from core.models import Branch, NumberCounter, NumberFormat, NumberSeries
from tenancy.context import tenant_atomic

MASTER_LABELS = {
    "customer": "Customer numbers",
    "vendor": "Supplier numbers",
    "item": "Item numbers",
    "bom": "BOM numbers",
}
EXAMPLE_YEAR = "2026-27"

register_in_use(
    "number_format",
    lambda fmt: "numbers already issued" if fmt.counters.filter(last__gt=0).exists() else "",
)


def _say(exc: ValueError, field: str = "prefix"):
    return ValidationError({field: [str(exc)]})


# --- Master numbers -------------------------------------------------------------


def _masters() -> list[dict]:
    out = []
    for key, label in MASTER_LABELS.items():
        series, _ = NumberSeries.objects.get_or_create(
            key=key, defaults={"prefix": numbering.DEFAULTS.get(key, "")}
        )
        out.append(
            {
                "key": key,
                "label": label,
                "prefix": series.prefix,
                "width": series.width,
                "last": series.last,
                "next": numbering.format_number(series, series.last + 1),
            }
        )
    return out


class MasterSeriesSerializer(serializers.Serializer):
    prefix = serializers.CharField(max_length=10, allow_blank=True, required=False)
    width = serializers.IntegerField(min_value=3, max_value=8, required=False)
    last = serializers.IntegerField(min_value=0, required=False)


class MasterSeriesView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, key: str):
        _check(request, EDIT)
        if key not in MASTER_LABELS:
            raise NotFound("No such number series.")
        series = NumberSeries.objects.select_for_update().filter(key=key).first()
        if series is None:
            series = NumberSeries.objects.create(key=key, prefix=numbering.DEFAULTS.get(key, ""))
        serializer = MasterSeriesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "last" in data and data["last"] < series.last:
            raise ValidationError(
                {"last": [f"Numbers up to {series.last} are already used; it can only go up."]}
            )
        for field in ("prefix", "width", "last"):
            if field in data:
                setattr(series, field, data[field])
        series.save()
        return Response(_masters())


# --- Document series ---------------------------------------------------------------


class FormatSerializer(serializers.ModelSerializer):
    doc_type = serializers.ChoiceField(choices=numbering.DOC_CHOICES)
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), allow_null=True, required=False
    )
    prefix = serializers.CharField(max_length=20)
    example = serializers.SerializerMethodField()

    class Meta:
        model = NumberFormat
        fields = ["id", "doc_type", "branch", "prefix", "width", "example"]

    def get_example(self, fmt) -> str:
        return numbering.render(fmt.prefix, EXAMPLE_YEAR, fmt.width, 1)


def save_format(company, fmt: NumberFormat | None, data: dict) -> NumberFormat:
    """Add a branch's own series or change a series' prefix and width (the
    screen and imports both save here)."""
    new = fmt is None or fmt.pk is None
    fmt = fmt or NumberFormat(company=company)
    branch = data.get("branch", fmt.branch if not new else None)
    if branch is not None and branch.company_id != company.pk:
        raise ValidationError({"branch": ["Pick a branch of this company."]})
    doc_type = data.get("doc_type", fmt.doc_type)
    prefix = duplicates.tidy(data.get("prefix", fmt.prefix)).replace(" ", "")
    width = data.get("width", fmt.width)
    if new:
        existing = NumberFormat.objects.filter(company=company, doc_type=doc_type, branch=branch)
        if existing.exists():
            # A file may list the company's own series: change that one.
            fmt = existing.first()
            new = False
    elif (doc_type, branch) != (fmt.doc_type, fmt.branch):
        raise ValidationError({"doc_type": ["The kind of document and branch cannot change."]})
    try:
        numbering.check_format(doc_type, prefix, width)
    except ValueError as exc:
        raise _say(exc) from exc
    clash = (
        NumberFormat.objects.filter(company=company, prefix__iexact=prefix)
        .exclude(pk=fmt.pk)
        .first()
    )
    if clash:
        raise ValidationError(
            {"prefix": [f"{clash.prefix} is already the series of {_name(clash)}; use another."]}
        )
    if not new:
        refuse_key_changes("number_format", fmt, {"prefix": prefix, "width": width})
    fmt.doc_type, fmt.branch, fmt.prefix, fmt.width = doc_type, branch, prefix, width
    try:
        fmt.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    fmt.save()
    return fmt


def _name(fmt: NumberFormat) -> str:
    label = numbering.DOC_TYPES[fmt.doc_type][0]
    return f"{label} of {fmt.branch.name}" if fmt.branch_id else label


def _formats(company):
    numbering.ensure_formats(company)
    return (
        NumberFormat.objects.filter(company=company)
        .select_related("branch")
        .prefetch_related("counters")
        .order_by("doc_type", "branch__name")
    )


def _years(company):
    return list(company.fiscal_years.order_by("-start_date"))


def format_row(fmt: NumberFormat, years) -> dict:
    last = {c.year_id: c.last for c in fmt.counters.all()}
    label = numbering.DOC_TYPES[fmt.doc_type][0]
    return {
        **FormatSerializer(fmt).data,
        "doc_label": label,
        "branch_name": fmt.branch.name if fmt.branch_id else "",
        "in_use": any(v for v in last.values()),
        "years": [{"year": y.pk, "name": y.name, "last": last.get(y.pk, 0)} for y in years],
    }


def overview(company) -> dict:
    years = _years(company)
    return {
        "masters": _masters(),
        "formats": [format_row(f, years) for f in _formats(company)],
        "doc_types": [{"value": c, "label": label} for c, label in numbering.DOC_CHOICES],
    }


exchange.register(
    exchange.Master(
        key="number-formats",
        label="Document series",
        noun="document series",
        serializer=FormatSerializer,
        queryset=lambda ctx: _formats(ctx.company),
        save=lambda ctx, fmt, data: save_format(ctx.company, fmt, data),
        per_company=True,
        exclude=("example",),
        labels={"doc_type": "Document", "branch": "Branch", "width": "Digits"},
        hints={
            "prefix": "Letters, digits, / . _ - and {YY} for the fiscal year (2627) or {FY} "
            "(2026-27), for example AO/SI/{YY}/",
            "branch": "Leave empty for the company's series; fill it to give that branch its own",
        },
    )
)


class NumberingView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(overview(_company(request, pk)))


class FormatListView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = FormatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("branch") is None:
            raise ValidationError({"branch": ["Pick the branch this series is for."]})
        fmt = save_format(company, None, dict(serializer.validated_data))
        recorder.touch(fmt)
        return Response(format_row(fmt, _years(company)), status=status.HTTP_201_CREATED)


def _own(request, pk: int) -> NumberFormat:
    fmt = (
        NumberFormat.objects.select_for_update(of=("self",))
        .select_related("company", "branch")
        .filter(pk=pk)
        .first()
    )
    if fmt is None or not visible_companies(request.user).filter(pk=fmt.company_id):
        raise NotFound("No such document series.")
    return fmt


class FormatDetailView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        fmt = _own(request, pk)
        serializer = FormatSerializer(fmt, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        save_format(fmt.company, fmt, dict(serializer.validated_data))
        return Response(format_row(fmt, _years(fmt.company)))


class CounterView(APIView):
    """PATCH {last}: set the last number used in one fiscal year, to carry on
    from numbers used before MyERP. It can only go up."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int, year: int):
        _check(request, EDIT)
        fmt = _own(request, pk)
        fiscal_year = fmt.company.fiscal_years.filter(pk=year).first()
        if fiscal_year is None:
            raise NotFound("No such fiscal year.")
        last = request.data.get("last")
        if not isinstance(last, int) or isinstance(last, bool) or last < 0:
            raise ValidationError({"last": ["Give the last number used, as a whole number."]})
        NumberCounter.objects.get_or_create(format=fmt, year=fiscal_year)
        counter = NumberCounter.objects.select_for_update().get(format=fmt, year=fiscal_year)
        if last < counter.last:
            raise ValidationError(
                {"last": [f"Numbers up to {counter.last} are already used; it can only go up."]}
            )
        fmt.save()  # opens the series' Activity entry before the change
        counter.last = last
        counter.save()
        recorder.touch(fmt)
        return Response(format_row(fmt, _years(fmt.company)))


def _counters(scope):
    qs = NumberCounter.objects.filter(last__gt=0)
    return qs.filter(format__company=scope) if scope else qs


# "Entries only" in the data reset starts every series again from 0001.
data_reset.register_entries(
    "Document numbers used",
    lambda scope: _counters(scope).count(),
    lambda scope: _counters(scope).update(last=0),
)
