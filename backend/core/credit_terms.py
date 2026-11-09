"""Credit terms: a company's list of how bills are paid (decision 0019).

A term such as "50% advance, 50% on delivery" is split into parts; each is
a share of the bill due at an event plus some days, and the shares add up
to 100%. Parties pick a term; sales and purchase documents will copy it and
work out due dates from it.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core.api import EDIT, VIEW, Signed, _check, _company
from core.companies import visible_companies
from core.models import CreditTerm, CreditTermPart, describe_part
from tenancy.context import tenant_atomic

# name, parts as (percent, event, days). Every new company starts with these.
STANDARD_TERMS = [
    ("Full advance", [(100, "order", 0)]),
    ("50% advance, 50% on delivery", [(50, "order", 0), (50, "delivery", 0)]),
    ("50% advance, 50% before dispatch", [(50, "order", 0), (50, "dispatch", 0)]),
    ("On delivery", [(100, "delivery", 0)]),
    ("15 days", [(100, "bill", 15)]),
    ("30 days", [(100, "bill", 30)]),
    ("45 days", [(100, "bill", 45)]),
    ("60 days", [(100, "bill", 60)]),
]


def seed_credit_terms(CreditTerm, CreditTermPart, company) -> None:
    """Add the standard terms a company lacks. Takes the models so that
    migrations can pass their historical versions."""
    have = set(CreditTerm.objects.filter(company=company).values_list("name", flat=True))
    for name, parts in STANDARD_TERMS:
        if name in have:
            continue
        term = CreditTerm.objects.create(company=company, name=name)
        for percent, event, days in parts:
            CreditTermPart.objects.create(term=term, percent=percent, event=event, days=days)


def summary(term: CreditTerm) -> str:
    return ", ".join(describe_part(p.percent, p.event, p.days) for p in term.parts.all())


class CreditTermPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditTermPart
        fields = ["percent", "event", "days"]


class CreditTermSerializer(serializers.ModelSerializer):
    parts = CreditTermPartSerializer(many=True)
    summary = serializers.SerializerMethodField()
    party_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = CreditTerm
        fields = ["id", "name", "is_active", "notes", "parts", "summary", "party_count"]

    def get_summary(self, term) -> str:
        return summary(term)


def _save_term(term: CreditTerm, data: dict) -> None:
    parts = data.pop("parts", None)
    if "name" in data:
        data["name"] = data["name"].strip()
        clash = CreditTerm.objects.filter(company=term.company, name__iexact=data["name"])
        if term.pk:
            clash = clash.exclude(pk=term.pk)
        if clash.exists():
            raise ValidationError({"name": ["There are already credit terms with this name."]})
    for field in ("name", "is_active", "notes"):
        if field in data:
            setattr(term, field, data[field])
    if parts is not None:
        if not parts:
            raise ValidationError({"parts": ["Add at least one part."]})
        total = sum((Decimal(p["percent"]) for p in parts), Decimal(0))
        if total != 100:
            raise ValidationError(
                {"parts": [f"The parts add up to {total.normalize():f}%; make them 100%."]}
            )
    try:
        term.full_clean(exclude=["company"], validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    term.save()
    if parts is not None:
        term.parts.all().delete()
        for p in parts:
            CreditTermPart.objects.create(term=term, **p)
        recorder.touch(term)


class CreditTermListView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        terms = (
            company.credit_terms.annotate(party_count=Count("parties"))
            .prefetch_related("parts")
            .order_by("name")
        )
        return Response(CreditTermSerializer(terms, many=True).data)

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = CreditTermSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        term = CreditTerm(company=company)
        _save_term(term, dict(serializer.validated_data))
        return Response(CreditTermSerializer(term).data, status=status.HTTP_201_CREATED)


class CreditTermDetailView(APIView):
    """Edit only: credit terms are never deleted, only made inactive."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        term = CreditTerm.objects.select_for_update().filter(pk=pk).first()
        if term is None or not visible_companies(request.user).filter(pk=term.company_id):
            raise NotFound("No such credit terms.")
        serializer = CreditTermSerializer(term, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_term(term, dict(serializer.validated_data))
        return Response(CreditTermSerializer(term).data)
