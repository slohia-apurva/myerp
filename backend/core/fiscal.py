"""Fiscal years and their monthly periods (spec 01, "Fiscal year / period").

A company's years are whole months (start on the 1st, end on a month's last
day), never overlap, and are split into monthly periods that can be locked:
while a period is locked nothing posts into it. Vouchers call `assert_open`
before posting; locking needs "Edit" on masters, unlocking an Owner, and both
are written to the year's Activity.
"""

import calendar
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import exchange
from core.api import EDIT, VIEW, Signed, _check, _company
from core.companies import visible_companies
from core.locks import refuse_key_changes
from core.models import Company, FiscalPeriod, FiscalYear, fiscal_year_start
from tenancy.context import tenant_atomic

MAX_MONTHS = 18  # a first year can be longer than twelve months


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def year_name(start: date, end: date) -> str:
    """2026-27 for April to March, 2026 for January to December."""
    if start.year == end.year:
        return str(start.year)
    return f"{start.year}-{str(end.year)[2:]}"


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def check_range(company: Company, start: date, end: date, exclude_pk=None) -> None:
    if start.day != 1:
        raise ValidationError({"start_date": ["A year starts on the 1st of a month."]})
    if end != month_end(end):
        raise ValidationError({"end_date": ["A year ends on the last day of a month."]})
    if end <= start:
        raise ValidationError({"end_date": ["The year must end after it starts."]})
    if months_between(start, end) > MAX_MONTHS:
        raise ValidationError({"end_date": [f"A year is at most {MAX_MONTHS} months long."]})
    clash = FiscalYear.objects.filter(
        company=company, start_date__lte=end, end_date__gte=start
    ).exclude(pk=exclude_pk)
    other = clash.first()
    if other:
        raise ValidationError(
            {"start_date": [f"These dates overlap the year {other.name} of this company."]}
        )


def _make_periods(year: FiscalYear) -> None:
    day = year.start_date
    while day <= year.end_date:
        FiscalPeriod.objects.create(year=year, start_date=day, end_date=month_end(day))
        day = add_months(day, 1)


def create_year(company: Company, start: date, end: date, name: str = "") -> FiscalYear:
    check_range(company, start, end)
    name = name.strip() or year_name(start, end)
    if FiscalYear.objects.filter(company=company, name__iexact=name).exists():
        raise ValidationError({"name": ["This company already has a year with this name."]})
    year = FiscalYear(company=company, name=name, start_date=start, end_date=end)
    try:
        year.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    year.save()
    _make_periods(year)
    recorder.touch(year)
    return year


def ensure_years(company: Company, today: date | None = None) -> None:
    """Give a company the years from the one its books begin in up to the one
    that holds today, where they are missing."""
    today = today or date.today()
    month = company.fiscal_year_start_month
    start = fiscal_year_start(company.books_start, month)
    last = fiscal_year_start(today, month)
    while start <= last:
        end = month_end(add_months(start, 11))
        overlaps = FiscalYear.objects.filter(
            company=company, start_date__lte=end, end_date__gte=start
        ).exists()
        if not overlaps:
            year = FiscalYear.objects.create(
                company=company, name=year_name(start, end), start_date=start, end_date=end
            )
            _make_periods(year)
        start = add_months(start, 12)


def assert_open(company: Company, day: date) -> FiscalPeriod:
    """The period an entry dated `day` posts into; raises if there is no year
    for it or its month is locked. Every voucher calls this before posting."""
    period = (
        FiscalPeriod.objects.select_related("year")
        .filter(
            year__company=company,
            year__is_active=True,
            start_date__lte=day,
            end_date__gte=day,
        )
        .first()
    )
    if period is None:
        raise ValidationError({"date": [f"No fiscal year is set up for {day:%d-%m-%Y}."]})
    if period.is_locked:
        raise ValidationError(
            {"date": [f"{period.start_date:%B %Y} is locked; ask an Owner to unlock it."]}
        )
    return period


class PeriodSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = FiscalPeriod
        fields = ["id", "label", "start_date", "end_date", "is_locked"]

    def get_label(self, period) -> str:
        return f"{period.start_date:%B %Y}"


class FiscalYearSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=20, required=False, allow_blank=True)
    periods = PeriodSerializer(many=True, read_only=True)

    class Meta:
        model = FiscalYear
        fields = ["id", "name", "start_date", "end_date", "is_active", "periods"]


def save_year(company: Company, year: FiscalYear | None, data: dict) -> FiscalYear:
    if year is None:
        if "start_date" not in data or "end_date" not in data:
            raise ValidationError({"start_date": ["Give the start and end dates of the year."]})
        return create_year(company, data["start_date"], data["end_date"], data.get("name", ""))
    start = data.get("start_date", year.start_date)
    end = data.get("end_date", year.end_date)
    dates_changed = (start, end) != (year.start_date, year.end_date)
    if dates_changed:
        refuse_key_changes("fiscal_year", year, data)
        check_range(year.company, start, end, exclude_pk=year.pk)
        if year.periods.filter(is_locked=True).exists():
            raise ValidationError(
                {"start_date": ["Unlock the months of this year before changing its dates."]}
            )
    if "name" in data:
        name = data["name"].strip() or year_name(start, end)
        clash = FiscalYear.objects.filter(company=year.company, name__iexact=name)
        if clash.exclude(pk=year.pk).exists():
            raise ValidationError({"name": ["This company already has a year with this name."]})
        year.name = name
    if "is_active" in data:
        year.is_active = data["is_active"]
    year.start_date, year.end_date = start, end
    try:
        year.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    year.save()
    if dates_changed:
        year.periods.all().delete()
        _make_periods(year)
        recorder.touch(year)
    return year


def _years(company):
    return company.fiscal_years.prefetch_related("periods").order_by("-start_date")


exchange.register(
    exchange.Master(
        key="fiscal-years",
        label="Fiscal years",
        noun="fiscal year",
        serializer=FiscalYearSerializer,
        queryset=lambda ctx: _years(ctx.company),
        save=lambda ctx, year, data: save_year(ctx.company, year, data),
        per_company=True,
    )
)


class FiscalYearListView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        return Response(FiscalYearSerializer(_years(company), many=True).data)

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = FiscalYearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year = save_year(company, None, dict(serializer.validated_data))
        return Response(FiscalYearSerializer(year).data, status=status.HTTP_201_CREATED)


class FiscalYearDetailView(APIView):
    """Edit only: years are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        year = FiscalYear.objects.select_for_update().filter(pk=pk).first()
        if year is None or not visible_companies(request.user).filter(pk=year.company_id):
            raise NotFound("No such fiscal year.")
        serializer = FiscalYearSerializer(year, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        save_year(year.company, year, dict(serializer.validated_data))
        return Response(FiscalYearSerializer(year).data)


class PeriodDetailView(APIView):
    """PATCH {is_locked}: lock or unlock one month. Locking needs "Edit" on
    masters; unlocking an Owner, since it reopens closed books."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        period = FiscalPeriod.objects.select_related("year").filter(pk=pk).first()
        if period is None or not visible_companies(request.user).filter(pk=period.year.company_id):
            raise NotFound("No such period.")
        locked = request.data.get("is_locked")
        if not isinstance(locked, bool):
            raise ValidationError({"is_locked": ["Say whether the month is locked."]})
        if period.is_locked and not locked and not request.user.is_owner:
            raise PermissionDenied("Only an Owner can unlock a month.")
        year = FiscalYear.objects.select_for_update().get(pk=period.year_id)
        year.save()  # opens the year's Activity entry before the change
        period.is_locked = locked
        period.save()
        recorder.touch(year)
        return Response(FiscalYearSerializer(year).data)
