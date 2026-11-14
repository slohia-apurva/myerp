"""Couriers, transporters and shipments (spec 06, build step 1).

Who may do what:
- Transporters (the company's courier accounts) are masters: `masters.view` sees them,
  `masters.edit` adds and changes them.
- Shipments belong to despatch: `sales.view` or `stock.view` sees them,
  `sales.create` or `stock.create` enters them and types their status.
- All of it needs the company's Sales module (decision 0014).
"""

import datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import duplicates, exchange
from core.api import CONTACT_FIELDS, EDIT, VIEW, Signed, _check
from core.api import _company as _visible_company
from core.companies import visible_companies
from core.locks import lock_status, refuse_key_changes
from shipping.models import (
    CLOSED,
    CourierAccount,
    Shipment,
    Status,
    TrackingEvent,
    check_awb,
    clean_awb,
)
from tenancy.context import require_tenant, tenant_atomic
from tenancy.models import Carrier, CarrierRequest

SEE = ("sales.view", "stock.view")
ENTER = ("sales.create", "stock.create")


def _check_any(request, codes) -> None:
    if not any(request.user.can(c) for c in codes):
        raise PermissionDenied("Your role does not allow this.")


def _company(request, pk: int):
    company = _visible_company(request, pk)
    if "sales" not in company.modules:
        raise NotFound("This company does not use the Sales module.")
    return company


def _carriers() -> dict[int, Carrier]:
    return {c.pk: c for c in Carrier.objects.all()}


def _carrier_out(c: Carrier) -> dict:
    return {
        "id": c.pk,
        "name": c.name,
        "kind": c.kind,
        "kind_label": c.get_kind_display(),
        "awb_hint": c.awb_hint,
        "tracking_url": c.tracking_url,
        "is_active": c.is_active,
    }


class CarrierListView(APIView):
    """GET: the central list of couriers and aggregators."""

    permission_classes = [Signed]

    def get(self, request):
        if not (request.user.can(VIEW) or any(request.user.can(c) for c in SEE)):
            raise PermissionDenied("Your role does not allow this.")
        return Response([_carrier_out(c) for c in Carrier.objects.all()])


# Transporters ----------------------------------------------------------


class CourierAccountSerializer(serializers.ModelSerializer):
    carrier_id = serializers.IntegerField(allow_null=True, required=False)
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    # For a transporter that is not in the courier list: a word for the MyERP team.
    note_for_central = serializers.CharField(write_only=True, allow_blank=True, required=False)
    lock = serializers.SerializerMethodField()

    def get_lock(self, account) -> dict:
        return lock_status("courier_account", account)

    class Meta:
        model = CourierAccount
        fields = [
            "id",
            "carrier_id",
            "name",
            "gstin",
            "state_code",
            *CONTACT_FIELDS,
            "service",
            "account_code",
            "notes",
            "note_for_central",
            "is_active",
            "lock",
        ]
        read_only_fields = ["state_code"]


def _account_out(a: CourierAccount, carriers: dict[int, Carrier]) -> dict:
    data = CourierAccountSerializer(a).data
    carrier = carriers.get(a.carrier_id)
    data["carrier_name"] = carrier.name if carrier else ""
    data["service_label"] = a.get_service_display()
    data["company"] = a.company_id
    data["preferred_by"] = a.preferred_by.count()
    return data


def _ask_central(account: CourierAccount, note: str, user) -> None:
    """A transporter without a listed courier leaves (or updates) an open
    request for the MyERP team to add it to the central list."""
    tenant = require_tenant()
    req = (
        CarrierRequest.objects.filter(tenant=tenant, status=CarrierRequest.OPEN)
        .filter(name__iexact=account.name)
        .first()
    )
    if req is None:
        req = CarrierRequest(tenant=tenant, name=account.name)
    req.gstin = account.gstin
    if note:
        req.note = note
    req.requested_by = user.email
    req.save()


def _save_account(account: CourierAccount, data: dict, user=None) -> None:
    note = data.pop("note_for_central", "").strip()
    if data.get("carrier_id") is not None:
        carrier = Carrier.objects.filter(pk=data["carrier_id"]).first()
        if carrier is None or (not carrier.is_active and carrier.pk != account.carrier_id):
            raise ValidationError({"carrier_id": ["Pick a courier from the list."]})
    if "gstin" in data:
        data["gstin"] = data["gstin"].strip().upper()
    if not data.get("gstin", account.gstin):
        raise ValidationError(
            {
                "gstin": [
                    "Give the transporter's GSTIN: an e-way bill needs it as the Transporter ID."
                ]
            }
        )
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        duplicates.check_name(
            CourierAccount.objects.filter(company=account.company),
            data["name"],
            exclude=account.pk,
            kind="courier_account",
            message='This company already has a transporter named "{name}".',
        )
    refuse_key_changes("courier_account", account, data)
    for field, value in data.items():
        setattr(account, field, value)
    try:
        account.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    account.save()
    if user is not None and account.carrier_id is None and (note or "carrier_id" in data):
        _ask_central(account, note, user)


def _carrier_name(pk) -> str:
    if not pk:
        return ""
    carrier = Carrier.objects.filter(pk=pk).first()
    return carrier.name if carrier else str(pk)


def _carrier_from(text: str) -> int:
    carrier = Carrier.objects.filter(name__iexact=text.strip()).first()
    if carrier is None:
        names = ", ".join(Carrier.objects.filter(is_active=True).values_list("name", flat=True))
        raise ValueError(
            f"there is no courier {text.strip()!r} in MyERP's list; pick one of: {names}, "
            "or leave it empty for a transporter that is not in the list"
        )
    return carrier.pk


def _import_account(ctx, account, data):
    account = account or CourierAccount(company=ctx.company)
    _save_account(account, data)
    return account


exchange.register(
    exchange.Master(
        key="courier-accounts",
        label="Transporters",
        noun="transporter",
        serializer=CourierAccountSerializer,
        queryset=lambda ctx: ctx.company.courier_accounts.order_by("name"),
        save=_import_account,
        per_company=True,
        labels={
            "carrier_id": "Courier in MyERP's list",
            "account_code": "Account code",
            "gstin": "GSTIN",
        },
        hints={
            "gstin": "Required: it is the Transporter ID on an e-way bill",
            "carrier_id": "Leave empty for a transporter that is not in MyERP's list of couriers",
        },
        codecs={
            "carrier_id": exchange.Codec(
                _carrier_name,
                _carrier_from,
                hint="The courier's name as in MyERP's list of couriers",
                choices=lambda: list(
                    Carrier.objects.filter(is_active=True).values_list("name", flat=True)
                ),
            )
        },
    )
)


class CourierAccountListView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        if not (request.user.can(VIEW) or any(request.user.can(c) for c in SEE)):
            raise PermissionDenied("Your role does not allow this.")
        company = _company(request, pk)
        carriers = _carriers()
        return Response([_account_out(a, carriers) for a in company.courier_accounts.all()])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = CourierAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = CourierAccount(company=company)
        _save_account(account, dict(serializer.validated_data), request.user)
        return Response(_account_out(account, _carriers()), status=status.HTTP_201_CREATED)


class CourierAccountDetailView(APIView):
    """Edit only: accounts are never deleted, only disabled."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        account = (
            CourierAccount.objects.select_for_update()
            .filter(pk=pk, company__in=visible_companies(request.user))
            .first()
        )
        if account is None:
            raise NotFound("No such transporter.")
        serializer = CourierAccountSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_account(account, dict(serializer.validated_data), request.user)
        return Response(_account_out(account, _carriers()))


# Shipments -----------------------------------------------------------------


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = [
            "id",
            "branch",
            "account",
            "awb",
            "booked_on",
            "party",
            "reference",
            "ship_to_city",
            "ship_to_pincode",
            "packages",
            "weight_kg",
            "payment",
            "cod_amount",
            "expected_on",
            "notes",
        ]
        extra_kwargs = {"party": {"required": False}, "branch": {"required": False}}


# What may still change once the courier has reported on the shipment.
FIXED_AFTER_TRACKING = {"account": "transporter", "awb": "tracking number"}


def _tracking_link(s: Shipment, carriers) -> str:
    carrier = carriers.get(s.carrier_id)
    if carrier and carrier.tracking_url and "{awb}" in carrier.tracking_url:
        return carrier.tracking_url.replace("{awb}", s.awb)
    return ""


def _event_out(e: TrackingEvent) -> dict:
    return {
        "id": e.id,
        "at": e.at.isoformat(),
        "status": e.status,
        "status_label": e.get_status_display(),
        "place": e.place,
        "carrier_text": e.carrier_text,
        "received_by": e.received_by,
        "source": e.get_source_display(),
        "by": (e.by.full_name or e.by.email) if e.by else "",
    }


def _shipment_out(s: Shipment, carriers, now=None, events=False) -> dict:
    data = ShipmentSerializer(s).data
    carrier = carriers.get(s.carrier_id)
    data.update(
        {
            "company": s.company_id,
            "carrier_name": carrier.name if carrier else "",
            "account_name": s.account.name,
            "party_name": s.party.name if s.party else "",
            "branch_name": s.branch.name if s.branch else "",
            "status": s.status,
            "status_label": s.get_status_display(),
            "is_open": s.is_open,
            "last_event_at": s.last_event_at.isoformat() if s.last_event_at else None,
            "last_place": s.last_place,
            "delivered_at": s.delivered_at.isoformat() if s.delivered_at else None,
            "received_by": s.received_by,
            "cancelled": s.cancelled,
            "cancel_reason": s.cancel_reason,
            "alerts": s.alerts(now),
            "tracking_link": _tracking_link(s, carriers),
            "days_out": (timezone.localdate(now) - s.booked_on).days,
        }
    )
    if events:
        data["events"] = [_event_out(e) for e in s.events.select_related("by")]
    return data


def _save_shipment(s: Shipment, data: dict) -> None:
    errors: dict[str, list[str]] = {}
    if "account" in data:
        account = data["account"]
        if account.company_id != s.company_id:
            errors["account"] = ["Pick a transporter of this company."]
        elif not account.is_active and account.pk != s.account_id:
            errors["account"] = ["This transporter is disabled."]
        else:
            data["carrier_id"] = account.carrier_id
    branch = data.get("branch")
    if branch is not None and branch.company_id != s.company_id:
        errors["branch"] = ["Pick a branch of this company."]
    if "awb" in data:
        data["awb"] = clean_awb(data["awb"])
    if s.pk and s.events.exclude(source=TrackingEvent.TYPED).exists():
        for field, label in FIXED_AFTER_TRACKING.items():
            if field in data and data[field] != getattr(s, field):
                errors[field] = [
                    f"The courier has reported on this shipment; the {label} is fixed."
                ]
    if errors:
        raise ValidationError(errors)

    for field, value in data.items():
        setattr(s, field, value)
    if s.payment != Shipment.COD:
        s.cod_amount = None
    elif not s.cod_amount:
        errors["cod_amount"] = ["Give the amount to collect on delivery."]
    if s.ship_to_pincode and not (s.ship_to_pincode.isdigit() and len(s.ship_to_pincode) == 6):
        errors["ship_to_pincode"] = ["A PIN code is 6 digits."]
    if s.weight_kg is not None and s.weight_kg <= 0:
        errors["weight_kg"] = ["Weight must be more than zero."]
    if s.expected_on and s.expected_on < s.booked_on:
        errors["expected_on"] = ["The expected delivery date is before the booking date."]
    if why := check_awb(s.awb, Carrier.objects.filter(pk=s.carrier_id).first()):
        errors["awb"] = [why]
    elif (
        Shipment.objects.filter(
            **({"carrier_id": s.carrier_id} if s.carrier_id else {"account": s.account}),
            awb=s.awb,
            cancelled=False,
        )
        .exclude(pk=s.pk)
        .exists()
    ):
        errors["awb"] = ["This tracking number is already entered for this courier."]
    if errors:
        raise ValidationError(errors)
    s.save()


VIEWS = {
    "action": "Needs action",
    "open": "Open",
    "delivered": "Delivered",
    "all": "All",
}


def _booked_at(day: datetime.date) -> datetime.datetime:
    """When the "Booked" event is put: the start of the booking day, so any
    status typed for that day or later comes after it."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(0, 0)))


class ShipmentListView(APIView):
    """GET ?view=action|open|delivered|all&q=text. POST adds a shipment."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check_any(request, SEE)
        company = _company(request, pk)
        rows = Shipment.objects.filter(company=company).select_related("account", "party", "branch")
        view = request.query_params.get("view", "open")
        if view == "delivered":
            rows = rows.filter(cancelled=False, status=Status.DELIVERED)
        elif view in ("open", "action"):
            rows = rows.filter(cancelled=False).exclude(status__in=[*CLOSED - {Status.LOST}])
        q = request.query_params.get("q", "").strip()
        for word in q.split():
            rows = rows.filter(
                Q(awb__icontains=word)
                | Q(reference__icontains=word)
                | Q(party__name__icontains=word)
                | Q(ship_to_city__icontains=word)
                | Q(ship_to_pincode__startswith=word)
            )
        now = timezone.now()
        carriers = _carriers()
        out = [_shipment_out(s, carriers, now) for s in rows[:1000]]
        if view == "action":
            out = [s for s in out if s["alerts"]]
        elif view == "open":
            out = [s for s in out if s["is_open"]]
        return Response(out)

    @tenant_atomic()
    def post(self, request, pk: int):
        _check_any(request, ENTER)
        company = _company(request, pk)
        serializer = ShipmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        s = Shipment(company=company, created_by=request.user)
        _save_shipment(s, dict(serializer.validated_data))
        TrackingEvent.objects.create(
            shipment=s, at=_booked_at(s.booked_on), status=Status.BOOKED, by=request.user
        )
        s.refresh_status()
        return Response(_shipment_out(s, _carriers(), events=True), status=status.HTTP_201_CREATED)


def _shipment(request, pk: int, lock: bool = False) -> Shipment:
    rows = Shipment.objects.filter(
        pk=pk, company__in=visible_companies(request.user)
    ).select_related("account", "party", "branch", "company")
    if lock:
        rows = rows.select_for_update(of=("self",))
    s = rows.first()
    if s is None or "sales" not in s.company.modules:
        raise NotFound("No such shipment.")
    return s


class ShipmentDetailView(APIView):
    """GET one shipment with its events; PATCH its details."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check_any(request, SEE)
        return Response(_shipment_out(_shipment(request, pk), _carriers(), events=True))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check_any(request, ENTER)
        s = _shipment(request, pk, lock=True)
        if s.cancelled:
            raise ValidationError({"detail": "This shipment is cancelled."})
        serializer = ShipmentSerializer(s, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_shipment(s, dict(serializer.validated_data))
        return Response(_shipment_out(s, _carriers(), events=True))


class EventSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c for c in Status.choices if c[0] != Status.UNKNOWN])
    at = serializers.DateTimeField()
    place = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    carrier_text = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    received_by = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )


class ShipmentEventView(APIView):
    """POST a status typed by a person (until the courier's API is connected)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check_any(request, ENTER)
        s = _shipment(request, pk, lock=True)
        if s.cancelled:
            raise ValidationError({"detail": "This shipment is cancelled."})
        serializer = EventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["at"] > timezone.now() + datetime.timedelta(minutes=5):
            raise ValidationError({"at": ["The time is in the future."]})
        if data["at"].date() < s.booked_on - datetime.timedelta(days=1):
            raise ValidationError({"at": ["The time is before the shipment was booked."]})
        if data["status"] != Status.DELIVERED:
            data["received_by"] = ""
        if s.events.filter(at=data["at"], status=data["status"], carrier_code="").exists():
            raise ValidationError({"detail": "This status at this time is already recorded."})
        try:
            TrackingEvent.objects.create(shipment=s, by=request.user, **data)
        except IntegrityError as exc:  # pragma: no cover - raced with the check above
            raise ValidationError({"detail": "This status is already recorded."}) from exc
        s.refresh_status()
        return Response(_shipment_out(s, _carriers(), events=True), status=status.HTTP_201_CREATED)


class ShipmentCancelView(APIView):
    """POST {reason}: an AWB entered by mistake. The shipment stays, marked
    cancelled, and the number can be entered again."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check_any(request, ENTER)
        s = _shipment(request, pk, lock=True)
        if s.cancelled:
            raise ValidationError({"detail": "This shipment is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        s.cancelled = True
        s.cancel_reason = reason[:200]
        s.save()
        return Response(_shipment_out(s, _carriers(), events=True))
