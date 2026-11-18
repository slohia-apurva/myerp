"""Masters > Insurance Policies (Sidharth, 2026-11-18, previews 93a and 93d).

Policies belong to one company, like its transporters: `masters.view` sees
them, `masters.edit` adds and changes them. Never deleted, only disabled.

The cover of a policy is its starting sum insured plus every top-up. What
the company has insured under it so far is the insured value of the
submitted (not cancelled) orders that name it; the balance is the cover less
that. When an order takes the balance below the policy's "Alert When Balance
Falls Below", Owners and Accountants get a bell notice.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import duplicates, exchange
from core.api import EDIT, VIEW, Signed, _check
from core.api import _company as _visible_company
from core.companies import visible_companies
from core.locks import lock_status, refuse_key_changes
from core.models import Ledger
from insurance.models import InsurancePolicy, InsurancePolicyTopUp
from tenancy.context import tenant_atomic

ZERO = Decimal("0")


# Cover, use and balance -------------------------------------------------------


def _orders_under(policy: InsurancePolicy):
    from buying.models import PurchaseOrder

    return PurchaseOrder.objects.filter(insurance_policy=policy).exclude(
        status__in=(PurchaseOrder.DRAFT, PurchaseOrder.CANCELLED)
    )


def cover(policy: InsurancePolicy) -> Decimal:
    added = policy.top_ups.aggregate(s=Sum("amount"))["s"] or ZERO
    return policy.sum_insured + added


def used(policy: InsurancePolicy) -> Decimal:
    return _orders_under(policy).aggregate(s=Sum("insured_value"))["s"] or ZERO


def figures(policy: InsurancePolicy) -> dict:
    total, spent = cover(policy), used(policy)
    balance = total - spent
    return {
        "cover": str(total),
        "used": str(spent),
        "balance": str(balance),
        "low": policy.alert_below is not None and balance < policy.alert_below,
        "orders": _orders_under(policy).count(),
    }


def insured_value(policy: InsurancePolicy, amount: Decimal) -> Decimal:
    """What a transit worth `amount` is insured for under this policy."""
    if policy.insured_basis == InsurancePolicy.INVOICE_10:
        amount = amount * Decimal("1.1")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def check_pick(policy: InsurancePolicy, company_id: int, side: str, day, old_id=None) -> str:
    """Why this policy cannot go on an order of `side` dated `day`, or ""."""
    if policy.company_id != company_id:
        return "Pick a policy of this company."
    if not policy.is_transit:
        kind = policy.get_kind_display().lower()
        return f"Policy {policy.number} is a {kind} policy, not a transit one."
    if not policy.covers_side(side):
        return f"Policy {policy.number} does not cover {side}s."
    if policy.pk == old_id:
        return ""
    if not policy.is_active:
        return f"Policy {policy.number} is disabled."
    if not policy.valid_from <= day <= policy.valid_to:
        return (
            f"Policy {policy.number} runs from {policy.valid_from:%d-%m-%Y} to "
            f"{policy.valid_to:%d-%m-%Y}; the order is dated {day:%d-%m-%Y}."
        )
    return ""


def on_submit(order) -> None:
    """Called when an order naming a policy is submitted, inside its
    transaction: refuse it if the policy has run out and says "Stop until
    topped up"; tell Owners and Accountants when the balance falls below the
    alert."""
    policy = order.insurance_policy
    if policy is None:
        return
    before = cover(policy) - used(policy)
    after = before - order.insured_value
    if after < 0 and policy.when_out == InsurancePolicy.STOP:
        raise ValidationError(
            {
                "insurance_policy": [
                    f"Policy {policy.number} has ₹{before:,.2f} of cover left, less than this "
                    f"order's insured value of ₹{order.insured_value:,.2f}. Add the insurer's "
                    "top-up on the policy first."
                ]
            }
        )
    limit = policy.alert_below
    if limit is not None and after < limit <= before:
        from core.notifications import notify, people_with_roles

        notify(
            people_with_roles(order.company, "owner", "accountant"),
            order.company,
            f"Insurance policy {policy.number}: only ₹{after:,.2f} of cover left",
            f"Below ₹{limit:,.2f} after purchase order {order.number}. "
            f"Ask {policy.insurer.name} for a top-up.",
            f"#/companies/{policy.company_id}/insurance?open={policy.pk}",
        )


def picker_rows(company, side: str) -> list[dict]:
    """The company's transit policies covering `side`, for an order's picker."""
    rows = []
    for p in (
        InsurancePolicy.objects.filter(company=company, kind__in=InsurancePolicy.TRANSIT)
        .select_related("insurer")
        .prefetch_related("top_ups")
    ):
        if not p.covers_side(side):
            continue
        rows.append(
            {
                "id": p.pk,
                "number": p.number,
                "insurer_name": p.insurer.name,
                "kind_label": p.get_kind_display(),
                "valid_from": p.valid_from,
                "valid_to": p.valid_to,
                "is_active": p.is_active,
                "is_default": p.default_for in (side, InsurancePolicy.BOTH),
                "plus_ten": p.insured_basis == InsurancePolicy.INVOICE_10,
                "transit_limit": str(p.transit_limit) if p.transit_limit is not None else None,
                "balance": str(cover(p) - used(p)),
            }
        )
    return rows


# The master ----------------------------------------------------------------------


class TopUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsurancePolicyTopUp
        fields = ["date", "endorsement_no", "amount", "premium"]


class PolicySerializer(serializers.ModelSerializer):
    insurer = serializers.PrimaryKeyRelatedField(queryset=Ledger.objects.all())
    top_ups = TopUpSerializer(many=True, required=False)
    lock = serializers.SerializerMethodField()

    def get_lock(self, policy) -> dict:
        return lock_status("insurance_policy", policy)

    class Meta:
        model = InsurancePolicy
        fields = [
            "id", "number", "insurer", "kind", "covers", "valid_from", "valid_to",
            "sum_insured", "premium", "transit_limit", "insured_basis", "default_for",
            "alert_below", "when_out", "declare_to", "copy_to", "notes", "is_active",
            "top_ups", "lock",
        ]  # fmt: skip


def _emails(text: str, field: str) -> str:
    from django.core.validators import validate_email

    parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    for p in parts:
        try:
            validate_email(p)
        except DjangoValidationError:
            raise ValidationError({field: [f"{p} is not an email address."]}) from None
    return ", ".join(parts)


def _save_policy(policy: InsurancePolicy, data: dict) -> InsurancePolicy:
    top_ups = data.pop("top_ups", None)
    if "number" in data:
        data["number"] = duplicates.tidy(data["number"])
        duplicates.check_name(
            InsurancePolicy.objects.filter(company=policy.company),
            data["number"],
            field="number",
            exclude=policy.pk,
            kind="insurance_policy",
            message='This company already has policy number "{name}".',
        )
    insurer = data.get("insurer")
    if insurer is not None and insurer.pk != policy.insurer_id:
        if (
            insurer.company_id != policy.company_id
            or insurer.party_side != "supplier"
            or insurer.party_id is None
        ):
            raise ValidationError({"insurer": ["Pick the insurer from this company's suppliers."]})
        if not insurer.is_active:
            raise ValidationError({"insurer": [f"{insurer.name} is disabled."]})
    for field in ("declare_to", "copy_to"):
        if field in data:
            data[field] = _emails(data[field], field)
    refuse_key_changes("insurance_policy", policy, data)
    for field, value in data.items():
        setattr(policy, field, value)
    if policy.valid_from and policy.valid_to and policy.valid_to < policy.valid_from:
        raise ValidationError({"valid_to": ["The policy ends before it starts."]})
    if policy.default_for and not policy.is_transit:
        raise ValidationError(
            {"default_for": ["Only a marine (transit) policy can be filled in on orders."]}
        )
    if policy.default_for and policy.default_for != policy.covers and policy.covers != "both":
        raise ValidationError(
            {"default_for": [f"The policy covers {policy.get_covers_display().lower()} only."]}
        )
    try:
        policy.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    if top_ups is not None:
        for n, row in enumerate(top_ups, start=1):
            if row["amount"] <= 0:
                raise ValidationError({"top_ups": [f"Top-up {n}: the cover added is more than 0."]})
            if not policy.valid_from <= row["date"] <= policy.valid_to:
                raise ValidationError(
                    {"top_ups": [f"Top-up {n}: the date is outside the policy's period."]}
                )
    policy.save()
    if policy.default_for:
        # One default policy per side: another policy defaulting to the same
        # side gives it up (a "both" one keeps the other side).
        for other in InsurancePolicy.objects.filter(company=policy.company).exclude(pk=policy.pk):
            sides = {"purchase", "sales"} if other.default_for == "both" else {other.default_for}
            mine = {"purchase", "sales"} if policy.default_for == "both" else {policy.default_for}
            left = sides - mine - {""}
            new = "both" if len(left) == 2 else (left.pop() if left else "")
            if new != other.default_for:
                other.default_for = new
                other.save(update_fields=["default_for"])
    if top_ups is not None:
        policy.top_ups.all().delete()
        InsurancePolicyTopUp.objects.bulk_create(
            [
                InsurancePolicyTopUp(
                    policy=policy,
                    date=r["date"],
                    endorsement_no=duplicates.tidy(r.get("endorsement_no", "")),
                    amount=r["amount"],
                    premium=r.get("premium") or ZERO,
                )
                for r in top_ups
            ]
        )
        recorder.touch(policy)
    return policy


def _policy_out(p: InsurancePolicy) -> dict:
    data = PolicySerializer(p).data
    data["company"] = p.company_id
    data["insurer_name"] = p.insurer.name
    data["kind_label"] = p.get_kind_display()
    data["covers_label"] = p.get_covers_display()
    data["insured_basis_label"] = p.get_insured_basis_display()
    data["default_for_label"] = p.get_default_for_display()
    data["when_out_label"] = p.get_when_out_display()
    data["is_transit"] = p.is_transit
    today = timezone.localdate()
    data["days_left"] = (p.valid_to - today).days if p.valid_to >= today else 0
    data.update(figures(p))
    return data


def _policies(company):
    return (
        InsurancePolicy.objects.filter(company=company)
        .select_related("insurer")
        .prefetch_related("top_ups")
    )


def _import_policy(ctx, policy, data):
    policy = policy or InsurancePolicy(company=ctx.company)
    return _save_policy(policy, data)


exchange.register(
    exchange.Master(
        key="insurance-policies",
        label="Insurance policies",
        noun="insurance policy",
        serializer=PolicySerializer,
        queryset=lambda ctx: _policies(ctx.company).order_by("number"),
        save=_import_policy,
        per_company=True,
        link="number",
        exclude=("lock",),
        labels={
            "number": "Policy number",
            "kind": "Type of insurance",
            "sum_insured": "Starting sum insured",
            "premium": "Premium",
            "transit_limit": "Limit per transit",
            "insured_basis": "Insured value",
            "default_for": "Default for",
            "alert_below": "Alert when balance falls below",
            "when_out": "When cover runs out",
            "declare_to": "Send declaration to",
            "copy_to": "Copy to",
            "top_ups": "Top-ups",
            "top_ups.date": "Date",
            "top_ups.endorsement_no": "Endorsement no",
            "top_ups.amount": "Cover added",
            "top_ups.premium": "Premium",
        },
        hints={"insurer": "A supplier of this company", "declare_to": "Emails, comma-separated"},
    )
)


def _company(request, pk: int):
    return _visible_company(request, pk)


class PolicyListView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        return Response([_policy_out(p) for p in _policies(company)])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = PolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = InsurancePolicy(company=company)
        _save_policy(policy, dict(serializer.validated_data))
        return Response(_policy_out(policy), status=status.HTTP_201_CREATED)


class PolicySetupView(APIView):
    """GET: the company's suppliers, for the Insurer picker, and where "Create …"
    adds a new one."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        from core.models import LedgerGroup

        return Response(
            {
                "insurers": [
                    {"id": s.pk, "name": s.name, "is_active": s.is_active}
                    for s in Ledger.objects.filter(
                        company=company, party_side="supplier", party__isnull=False
                    ).order_by("name")
                ],
                "supplier_group": LedgerGroup.objects.filter(
                    company=company, code="sundry_creditors"
                )
                .values_list("pk", flat=True)
                .first(),
            }
        )


class PolicyDetailView(APIView):
    """Edit only: policies are never deleted, only disabled."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        policy = (
            InsurancePolicy.objects.select_for_update()
            .filter(pk=pk, company__in=visible_companies(request.user))
            .first()
        )
        if policy is None:
            raise NotFound("No such insurance policy.")
        serializer = PolicySerializer(policy, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save_policy(policy, dict(serializer.validated_data))
        return Response(_policy_out(policy))


# The policy's own files: the policy schedule and its endorsements.


def _policy_files(request, pk: int):
    from core import attachments

    if not request.user.can(VIEW):
        raise attachments.NotFound("No such insurance policy.")
    policy = InsurancePolicy.objects.filter(
        pk=pk, company__in=visible_companies(request.user)
    ).first()
    if policy is None:
        raise attachments.NotFound("No such insurance policy.")
    return attachments.Found(policy, request.user.can(EDIT))


def _register_files() -> None:
    from core import attachments

    attachments.register("insurance_policy", _policy_files, "Insurance Policy", entry=False)


_register_files()
