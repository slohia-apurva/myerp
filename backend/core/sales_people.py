"""People (Sidharth, 2026-11-16, preview 83; "Stores" added 2026-11-17, preview
88): the people who sell to customers, buy from suppliers or receive goods in
the stores, with or without a MyERP sign-in.
One list for every company in the group. A customer's "Salesman" offers the
people ticked Salesman, a supplier's "Purchaser" those ticked Purchaser; each
company picks its own (kept on its ledger). A goods receipt's "Received By" and
"QC By" offer those ticked Stores."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.locks import refuse_key_changes
from core.models import SalesPerson
from tenancy.context import tenant_atomic


class SalesPersonSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), allow_null=True, required=False
    )
    user_name = serializers.SerializerMethodField()
    party_count = serializers.IntegerField(read_only=True, default=0)

    def get_user_name(self, person) -> str:
        return person.user.display_name if person.user_id else ""

    class Meta:
        model = SalesPerson
        fields = [
            "id",
            "name",
            "is_salesman",
            "is_purchaser",
            "is_stores",
            "mobile",
            "email",
            "user",
            "user_name",
            "notes",
            "is_active",
            "party_count",
        ]


def _save_person(person: SalesPerson, data: dict) -> SalesPerson:
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            SalesPerson.objects.all(),
            data["name"],
            exclude=person.pk,
            kind="sales_person",
            message='There is already a person named "{name}".',
        )
    refuse_key_changes("sales_person", person, data)
    user = data.get("user")
    if user is not None and user.pk != person.user_id:
        if not user.is_active:
            raise ValidationError({"user": [f"{user.display_name} cannot sign in any more."]})
        other = SalesPerson.objects.filter(user=user).exclude(pk=person.pk).first()
        if other is not None:
            raise ValidationError({"user": [f"{user.display_name} is already {other.name}."]})
    for field in (
        "name",
        "is_salesman",
        "is_purchaser",
        "is_stores",
        "mobile",
        "email",
        "user",
        "notes",
        "is_active",
    ):
        if field in data:
            setattr(person, field, data[field])
    if not (person.is_salesman or person.is_purchaser or person.is_stores):
        raise ValidationError(
            {"is_salesman": ['Tick at least one of "Salesman", "Purchaser" and "Stores".']}
        )
    if person.pk:
        # A person picked on customers stays a salesman, on suppliers a purchaser.
        sides = set(person.ledgers.values_list("party_side", flat=True))
        if "customer" in sides and not person.is_salesman:
            raise ValidationError(
                {"is_salesman": [f"{person.name} is the salesman of a customer."]}
            )
        if "supplier" in sides and not person.is_purchaser:
            raise ValidationError(
                {"is_purchaser": [f"{person.name} is the purchaser of a supplier."]}
            )
        # Picked on a goods receipt: stays a stores person.
        from buying.models import GoodsReceipt

        on_receipt = GoodsReceipt.objects.filter(Q(received_by=person) | Q(qc_by=person))
        if not person.is_stores and on_receipt.exists():
            raise ValidationError({"is_stores": [f"{person.name} is named on a goods receipt."]})
    try:
        person.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    person.save()
    return person


def check_pick(ledger, side: str, person: SalesPerson | None) -> None:
    """A customer's salesman must be ticked Salesman, a supplier's purchaser
    Purchaser; a disabled person is kept only if already picked."""
    if person is None:
        return
    if side == "supplier" and not person.is_purchaser:
        raise ValidationError({"salesman": [f'{person.name} is not ticked "Purchaser".']})
    if side == "customer" and not person.is_salesman:
        raise ValidationError({"salesman": [f'{person.name} is not ticked "Salesman".']})
    if not person.is_active and person.pk != ledger.salesman_id:
        raise ValidationError({"salesman": [f"{person.name} is disabled."]})


def _user_cell(pk) -> str:
    if pk is None:
        return ""
    user = User.objects.filter(pk=pk).first()
    return user.email if user else str(pk)


def _user_from(text: str) -> int:
    text = text.strip()
    user = (
        User.objects.filter(is_active=True)
        .filter(Q(email__iexact=text) | Q(full_name__iexact=text))
        .first()
    )
    if user is None:
        raise ValueError(f"there is no active user {text!r}")
    return user.pk


USER = exchange.Codec(_user_cell, _user_from, hint="The user's email or full name", kind="other")


def _person_cell(pk) -> str:
    if pk is None:
        return ""
    person = SalesPerson.objects.filter(pk=pk).first()
    return person.name if person else str(pk)


def _person_from(text: str) -> int:
    person = SalesPerson.objects.filter(name__iexact=duplicates.tidy(text)).first()
    if person is None:
        raise ValueError(f"there is no person {text.strip()!r}")
    return person.pk


PERSON = exchange.Codec(
    _person_cell,
    _person_from,
    hint="A name from People",
    kind="other",
)


exchange.register(
    exchange.Master(
        key="sales-people",
        label="People",
        noun="person",
        serializer=SalesPersonSerializer,
        queryset=lambda ctx: SalesPerson.objects.select_related("user").order_by("name"),
        save=lambda ctx, person, data: _save_person(person or SalesPerson(), data),
        exclude=("user_name", "party_count"),
        codecs={"user": USER},
        labels={
            "is_salesman": "Salesman",
            "is_purchaser": "Purchaser",
            "is_stores": "Stores",
            "user": "MyERP user",
        },
    )
)


def _people():
    return (
        SalesPerson.objects.select_related("user")
        .annotate(party_count=Count("ledgers"))
        .order_by("name")
    )


class SalesPersonListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        return Response(SalesPersonSerializer(_people(), many=True).data)

    @tenant_atomic()
    def post(self, request):
        _check(request, EDIT)
        serializer = SalesPersonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        person = SalesPerson()
        _save_person(person, dict(serializer.validated_data))
        return Response(
            SalesPersonSerializer(_people().get(pk=person.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class SalesPersonDetailView(APIView):
    """Edit only: people are never deleted, only disabled."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        person = SalesPerson.objects.select_for_update().filter(pk=pk).first()
        if person is None:
            raise NotFound("No such person.")
        serializer = SalesPersonSerializer(person, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_person(person, dict(serializer.validated_data))
        return Response(SalesPersonSerializer(_people().get(pk=person.pk)).data)
