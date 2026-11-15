"""Terms and conditions (Sidharth, 2026-11-14): named sets of the terms
printed on orders, for purchase or for sales.

A company has a default set of each kind (`Company.purchase_terms`,
`Company.sales_terms`), ticked from the set's own form ("Default For"). A
supplier or customer may carry its own set (`Party.purchase_terms`,
`Party.sales_terms`), which wins over the company's. A document copies the
text when it is made and may change it for that one document. A line ending
in ":" prints as a heading.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import lock_status, refuse_key_changes
from core.models import Company, Party, TermsSet
from tenancy.context import tenant_atomic

# The Company and Party field holding the set of each kind.
FIELD = {TermsSet.PURCHASE: "purchase_terms", TermsSet.SALES: "sales_terms"}


def terms_for(company: Company, party: Party | None, kind: str) -> TermsSet | None:
    """The set a new document starts with: the party's own active set of this
    kind, else the company's default."""
    field = FIELD[kind]
    own = getattr(party, field) if party is not None else None
    if own is not None and own.is_active:
        return own
    default = getattr(company, field)
    return default if default is not None and default.is_active else None


class TermsSetSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    # The companies whose default set of this kind this is.
    default_for = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True
    )
    default_companies = serializers.SerializerMethodField()
    party_count = serializers.IntegerField(read_only=True, default=0)
    lock = serializers.SerializerMethodField()

    class Meta:
        model = TermsSet
        fields = [
            "id", "name", "kind", "kind_label", "text", "is_active", "notes",
            "default_for", "default_companies", "party_count", "lock",
        ]  # fmt: skip

    def get_default_companies(self, terms) -> list[dict]:
        if not terms.pk:
            return []
        rows = Company.objects.filter(**{FIELD[terms.kind]: terms})
        return sorted(
            ({"id": c.pk, "name": c.name} for c in rows), key=lambda r: r["name"].casefold()
        )

    def get_lock(self, terms) -> dict:
        return lock_status("terms", terms)


def _save_terms(terms: TermsSet, data: dict) -> TermsSet:
    default_for = data.pop("default_for", None)
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            TermsSet.objects.all(),
            data["name"],
            exclude=terms.pk,
            kind="terms",
            message='There are already terms and conditions named "{name}".',
        )
    if "text" in data:
        data["text"] = "\n".join(line.rstrip() for line in data["text"].strip().splitlines())
        if not data["text"]:
            raise ValidationError({"text": ["Write the terms."]})
    if terms.pk:
        refuse_key_changes("terms", terms, data)
    for field in ("name", "kind", "text", "is_active", "notes"):
        if field in data:
            setattr(terms, field, data[field])
    if default_for is not None:
        ids = set(default_for)
        if len(Company.objects.filter(pk__in=ids)) != len(ids):
            raise ValidationError({"default_for": ["Pick companies of this group."]})
        if ids and not terms.is_active:
            raise ValidationError({"default_for": ["A disabled set cannot be a default."]})
    try:
        terms.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    terms.save()
    field = FIELD[terms.kind]
    if default_for is not None:
        # Ticked companies take this set (replacing their old default); companies
        # unticked here lose it.
        Company.objects.filter(**{field: terms}).exclude(pk__in=default_for).update(**{field: None})
        Company.objects.filter(pk__in=default_for).update(**{field: terms})
        recorder.touch(terms)
    elif not terms.is_active:
        Company.objects.filter(**{field: terms}).update(**{field: None})
    return terms


def _with_counts():
    return TermsSet.objects.annotate(
        party_count=Count("suppliers", distinct=True) + Count("customers", distinct=True)
    )


exchange.register(
    exchange.Master(
        key="terms",
        label="Terms and conditions",
        noun="terms and conditions",
        serializer=TermsSetSerializer,
        queryset=lambda ctx: TermsSet.objects.order_by("name"),
        save=lambda ctx, terms, data: _save_terms(terms or TermsSet(), data),
        exclude=("kind_label", "default_for", "default_companies", "party_count", "lock"),
        labels={"kind": "Type", "text": "Terms"},
        hints={"text": 'One term per line; a line ending in ":" prints as a heading'},
    )
)


class TermsListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(TermsSetSerializer(_with_counts().order_by("name"), many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = TermsSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        terms = TermsSet()
        _save_terms(terms, dict(serializer.validated_data))
        return Response(TermsSetSerializer(terms).data, status=status.HTTP_201_CREATED)


class TermsDetailView(APIView):
    """Edit only: sets are never deleted, only disabled."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        terms = TermsSet.objects.select_for_update().filter(pk=pk).first()
        if terms is None:
            raise NotFound("No such terms and conditions.")
        serializer = TermsSetSerializer(terms, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_terms(terms, dict(serializer.validated_data))
        return Response(TermsSetSerializer(terms).data)
