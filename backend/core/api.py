"""Companies, branches, ledger groups and ledgers screens.

Who may do what:
- Anyone with `masters.view` sees the companies they may work in, with
  their branches and ledger groups. `users.manage` also lists companies, to
  limit users to some of them.
- Only an Owner can add a company. `masters.edit` changes company details,
  branches, ledgers and the groups people add.
- Standard ledger groups come with MyERP and cannot be changed, because
  posting rules rely on them.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.db.models.functions import Lower
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from core import india
from core import modules as company_modules
from core.companies import create_company, visible_companies
from core.models import (
    BILL_WISE_GROUP_CODES,
    CR,
    DR,
    Branch,
    Certificate,
    Company,
    Currency,
    Ledger,
    LedgerGroup,
    LedgerOpeningBill,
)
from tenancy.context import tenant_atomic

VIEW, EDIT = "masters.view", "masters.edit"


def _check(request, code: str) -> None:
    if not request.user.can(code):
        raise PermissionDenied("Your role does not allow this.")


def _company(request, pk: int, lock: bool = False) -> Company:
    companies = visible_companies(request.user)
    if lock:
        companies = companies.select_for_update()
    company = companies.filter(pk=pk).first()
    if company is None:
        raise NotFound("No such company.")
    return company


def _django_errors(exc) -> ValidationError:
    return ValidationError(getattr(exc, "message_dict", None) or {"detail": exc.messages})


class Signed(BasePermission):
    """Signed in; each method checks its own permission code."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


def _upper(value: str) -> str:
    return value.strip().upper()


CONTACT_FIELDS = ["address", "pincode", "phone", "email", "contact_person"]
REGISTRATION_FIELDS = [
    "entity_type",
    "cin",
    "incorporation_date",
    "tan",
]
DEFAULT_FLAGS = ["default_billing", "default_ship_to", "default_ship_from"]


class CompanySerializer(serializers.ModelSerializer):
    state = serializers.SerializerMethodField()
    # Checked by the model after being upper-cased here.
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    pan = serializers.CharField(max_length=10, allow_blank=True, required=False)
    cin = serializers.CharField(max_length=21, allow_blank=True, required=False)
    tan = serializers.CharField(max_length=10, allow_blank=True, required=False)
    validate_gstin = validate_pan = validate_cin = validate_tan = staticmethod(_upper)
    modules = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_modules(self, value):
        try:
            return company_modules.check(value)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "abbr",
            "gstin",
            "pan",
            *REGISTRATION_FIELDS,
            "state_code",
            "state",
            "address",
            "pincode",
            "phone",
            "email",
            "contact_person",
            "fiscal_year_start_month",
            "books_start",
            "multi_currency",
            "modules",
            "base_currency",
        ]
        read_only_fields = ["base_currency"]
        # Uniqueness is checked case-insensitively in the views.
        extra_kwargs = {
            "name": {"validators": []},
            "abbr": {"required": False, "validators": []},
            "books_start": {"required": False},
        }

    def get_state(self, company) -> str:
        return india.STATES.get(company.state_code, "")


class BranchSerializer(serializers.ModelSerializer):
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    validate_gstin = staticmethod(_upper)

    class Meta:
        model = Branch
        fields = [
            "id",
            "name",
            "state_code",
            "gstin",
            *CONTACT_FIELDS,
            "is_head_office",
            "is_active",
            *DEFAULT_FLAGS,
        ]
        read_only_fields = ["is_head_office"]


class CertificateSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default="")

    class Meta:
        model = Certificate
        fields = [
            "id",
            "kind",
            "kind_label",
            "name",
            "number",
            "issued_by",
            "branch",
            "branch_name",
            "valid_from",
            "valid_until",
            "notes",
        ]


class LedgerGroupSerializer(serializers.ModelSerializer):
    ledger_count = serializers.IntegerField(read_only=True, default=0)
    is_bank = serializers.SerializerMethodField()
    bill_wise_default = serializers.SerializerMethodField()

    class Meta:
        model = LedgerGroup
        fields = [
            "id",
            "name",
            "parent",
            "nature",
            "affects_gross_profit",
            "code",
            "is_standard",
            "ledger_count",
            "is_bank",
            "bill_wise_default",
        ]
        read_only_fields = ["nature", "affects_gross_profit", "code", "is_standard"]

    def get_is_bank(self, group) -> bool:
        return group.is_bank_group()

    def get_bill_wise_default(self, group) -> bool:
        return group.is_under(BILL_WISE_GROUP_CODES)


BANK_FIELDS = ["bank_name", "account_number", "ifsc", "bank_branch"]


class OpeningBillSerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerOpeningBill
        fields = ["ref", "bill_date", "due_date", "amount", "side", "fc_amount", "rate"]
        extra_kwargs = {"amount": {"required": False}}


class LedgerSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    nature = serializers.CharField(source="group.nature", read_only=True)
    ifsc = serializers.CharField(max_length=11, allow_blank=True, required=False)
    validate_ifsc = staticmethod(_upper)
    opening_bills = OpeningBillSerializer(many=True, required=False)
    currency = serializers.SlugRelatedField(
        slug_field="code", queryset=Currency.objects.all(), allow_null=True, required=False
    )
    bill_wise = serializers.BooleanField(required=False)

    class Meta:
        model = Ledger
        fields = [
            "id",
            "name",
            "group",
            "group_name",
            "nature",
            "is_active",
            "notes",
            *BANK_FIELDS,
            "opening_amount",
            "opening_side",
            "bill_wise",
            "opening_bills",
            "currency",
            "opening_fc_amount",
            "opening_rate",
        ]


LEDGER_FIELDS = [
    "name",
    "group",
    "is_active",
    "notes",
    *BANK_FIELDS,
    "opening_amount",
    "opening_side",
    "bill_wise",
    "currency",
    "opening_fc_amount",
    "opening_rate",
]

CENT = Decimal("0.01")


def _in_inr(fc_amount, rate) -> Decimal:
    return (fc_amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)


def _set_foreign_opening(ledger: Ledger) -> None:
    """A foreign currency ledger's INR opening balance is its foreign amount
    at the rate given. A base-currency ledger keeps no foreign figures."""
    if ledger.currency is None:
        ledger.opening_fc_amount, ledger.opening_rate = Decimal("0"), None
    elif not ledger.bill_wise:
        if ledger.opening_fc_amount and not (ledger.opening_rate and ledger.opening_rate > 0):
            raise ValidationError({"opening_rate": ["Give the exchange rate in INR."]})
        rate = ledger.opening_rate or Decimal("0")
        ledger.opening_amount = _in_inr(ledger.opening_fc_amount, rate)
    ledger.save()


def _save_opening_bills(ledger: Ledger, bills: list[dict] | None) -> None:
    """Replace the ledger's opening bills (when given) and check that they
    add up to its opening balance. Runs inside tenant_atomic, so raising
    undoes the whole save."""
    if not ledger.bill_wise:
        ledger.opening_bills.all().delete()
        return
    if bills is not None:
        refs = [b["ref"].strip().lower() for b in bills]
        if any(not r for r in refs):
            raise ValidationError({"opening_bills": ["Every bill needs a reference."]})
        if len(set(refs)) != len(refs):
            raise ValidationError({"opening_bills": ["Each bill reference may appear only once."]})
        start = ledger.company.books_start
        for b in bills:
            if b["bill_date"] >= start:
                raise ValidationError(
                    {
                        "opening_bills": [
                            f"Bill {b['ref']} must be dated before {start:%d %b %Y}, "
                            "when the books begin."
                        ]
                    }
                )
            if b.get("due_date") and b["due_date"] < b["bill_date"]:
                raise ValidationError(
                    {"opening_bills": [f"Bill {b['ref']} is due before its own date."]}
                )
            if ledger.currency is not None:
                fc, rate = b.get("fc_amount"), b.get("rate")
                if not fc or fc <= 0 or not rate or rate <= 0:
                    raise ValidationError(
                        {
                            "opening_bills": [
                                f"Bill {b['ref']} needs its {ledger.currency.code} amount "
                                "and the exchange rate."
                            ]
                        }
                    )
                b["amount"] = _in_inr(fc, rate)
            else:
                b["fc_amount"] = b["rate"] = None
                if not b.get("amount") or b["amount"] <= 0:
                    raise ValidationError({"opening_bills": [f"Bill {b['ref']} needs an amount."]})
        ledger.opening_bills.all().delete()
        LedgerOpeningBill.objects.bulk_create(
            LedgerOpeningBill(ledger=ledger, **{**b, "ref": b["ref"].strip()}) for b in bills
        )
    total = sum((b.signed for b in ledger.opening_bills.all()), Decimal("0"))
    if ledger.currency is not None:
        # Each bill has its own rate, so the INR balance is the bills' total.
        fc_total = sum(
            (b.fc_amount if b.side == DR else -b.fc_amount for b in ledger.opening_bills.all()),
            Decimal("0"),
        )
        ledger.opening_amount, ledger.opening_side = abs(total), DR if total >= 0 else CR
        ledger.opening_fc_amount, ledger.opening_rate = abs(fc_total), None
        ledger.save()
        return
    if total != ledger.opening_signed:
        raise ValidationError(
            {
                "opening_bills": [
                    f"The bills add up to {_dr_cr(total)} but the opening balance is "
                    f"{_dr_cr(ledger.opening_signed)}."
                ]
            }
        )


def _dr_cr(signed: Decimal) -> str:
    return f"{abs(signed):,.2f} {'Dr' if signed >= 0 else 'Cr'}"


def _opening_totals(company) -> dict:
    """Total opening debits and credits; they should match, as in Tally."""
    dr = cr = Decimal("0")
    for amount, side in company.ledgers.values_list("opening_amount", "opening_side"):
        if side == DR:
            dr += amount
        else:
            cr += amount
    return {"dr": str(dr), "cr": str(cr), "difference": str(dr - cr)}


def _save(instance, data: dict, fields) -> None:
    """Copy validated fields onto the model, run the model's checks, save."""
    for field in fields:
        if field in data:
            setattr(instance, field, data[field])
    try:
        instance.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise _django_errors(exc) from exc
    instance.save()


class CurrencyListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        return Response(list(Currency.objects.values("code", "name", "symbol")))


class StatesView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        return Response([{"code": c, "name": n} for c, n in india.STATE_CHOICES])


class ModulesView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        return Response(
            [
                {"code": code, "label": label, "what": what, "needs": list(needs)}
                for code, label, what, needs in company_modules.MODULES
            ]
        )


class CompanyListView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        if not (request.user.can(VIEW) or request.user.can("users.manage")):
            raise PermissionDenied("Your role does not allow this.")
        return Response(CompanySerializer(visible_companies(request.user), many=True).data)

    def post(self, request):
        if not request.user.is_owner:
            raise PermissionDenied("Only an Owner can add a company.")
        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if Company.objects.filter(name__iexact=data["name"].strip()).exists():
            raise ValidationError({"name": ["There is already a company with this name."]})
        if data.get("abbr") and Company.objects.filter(abbr__iexact=data["abbr"]).exists():
            raise ValidationError({"abbr": ["Another company uses this short code."]})
        try:
            company = create_company(**{**data, "name": data["name"].strip()})
        except DjangoValidationError as exc:
            raise _django_errors(exc) from exc
        return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)


class CompanyDetailView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        return Response(
            {
                "company": CompanySerializer(company).data,
                "branches": BranchSerializer(company.branches.all(), many=True).data,
                "certificates": CertificateSerializer(
                    company.certificates.select_related("branch"), many=True
                ).data,
                "opening": _opening_totals(company),
                "ledger_groups": LedgerGroupSerializer(
                    company.ledger_groups.select_related("parent__parent__parent").annotate(
                        ledger_count=Count("ledgers")
                    ),
                    many=True,
                ).data,
            }
        )

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk, lock=True)
        serializer = CompanySerializer(company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "abbr" in data and data["abbr"].upper() != company.abbr:
            raise ValidationError({"abbr": ["The short code cannot be changed once set."]})
        if (
            "name" in data
            and Company.objects.filter(name__iexact=data["name"].strip()).exclude(pk=pk).exists()
        ):
            raise ValidationError({"name": ["There is already a company with this name."]})
        old_pan = company.pan
        # Fiscal year start can change only until vouchers exist (a later piece
        # will refuse it then).
        fields = ["name", "gstin", "pan", *REGISTRATION_FIELDS, "state_code", *CONTACT_FIELDS]
        if "modules" in data and data["modules"] != company.modules and not request.user.is_owner:
            raise PermissionDenied("Only an Owner can change a company's modules.")
        extra = ["fiscal_year_start_month", "books_start", "multi_currency", "modules"]
        _save(company, data, [*fields, *extra])
        if not company.multi_currency and company.ledgers.exclude(currency=None).exists():
            raise ValidationError(
                {"multi_currency": ["Some ledgers are in foreign currencies; change them first."]}
            )
        if LedgerOpeningBill.objects.filter(
            ledger__company=company, bill_date__gte=company.books_start
        ).exists():
            raise ValidationError(
                {"books_start": ["Some opening bills are dated on or after this day."]}
            )
        if old_pan and company.pan != old_pan and company.branches.exclude(gstin="").exists():
            # Raising inside tenant_atomic undoes the save above.
            raise ValidationError({"pan": ["Branches have GSTINs under the old PAN."]})
        return Response(CompanySerializer(company).data)


class BranchListView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = BranchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"].strip()
        if company.branches.filter(name__iexact=name).exists():
            raise ValidationError({"name": ["This company already has a branch by that name."]})
        branch = Branch(company=company)
        _move_defaults(branch, serializer.validated_data)
        _save(branch, {**serializer.validated_data, "name": name}, BranchSerializer.Meta.fields)
        return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)


CERTIFICATE_FIELDS = [
    f for f in CertificateSerializer.Meta.fields if f not in ("id", "kind_label", "branch_name")
]


class CertificateListView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = CertificateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        certificate = Certificate(company=company)
        _save(certificate, serializer.validated_data, CERTIFICATE_FIELDS)
        return Response(CertificateSerializer(certificate).data, status=status.HTTP_201_CREATED)


class CertificateDetailView(APIView):
    """Edit only: certificates are never deleted (a renewal is a new row)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        certificate = Certificate.objects.select_for_update().filter(pk=pk).first()
        if certificate is None or not visible_companies(request.user).filter(
            pk=certificate.company_id
        ):
            raise NotFound("No such certificate.")
        serializer = CertificateSerializer(certificate, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _save(certificate, serializer.validated_data, CERTIFICATE_FIELDS)
        return Response(CertificateSerializer(certificate).data)


def _move_defaults(branch: Branch, data: dict) -> None:
    """Ticking a default on this branch takes it off the company's other
    branch. Unticking is refused: every company keeps one of each default."""
    for flag in DEFAULT_FLAGS:
        if flag not in data:
            continue
        if data[flag]:
            others = Branch.objects.filter(company_id=branch.company_id, **{flag: True})
            others.exclude(pk=branch.pk).update(**{flag: False})
        elif getattr(branch, flag):
            raise ValidationError({flag: ["Tick this default on another branch instead."]})


class BranchDetailView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, EDIT)
        branch = Branch.objects.select_for_update().filter(pk=pk).first()
        if branch is None or not visible_companies(request.user).filter(pk=branch.company_id):
            raise NotFound("No such branch.")
        serializer = BranchSerializer(branch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "name" in data:
            data["name"] = data["name"].strip()
            others = Branch.objects.filter(company_id=branch.company_id).exclude(pk=pk)
            if others.filter(name__iexact=data["name"]).exists():
                raise ValidationError({"name": ["This company already has a branch by that name."]})
        _move_defaults(branch, data)
        fields = ["name", "state_code", "gstin", *CONTACT_FIELDS, "is_active", *DEFAULT_FLAGS]
        _save(branch, data, fields)
        return Response(BranchSerializer(branch).data)


class LedgerGroupListView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = LedgerGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"].strip()
        parent = serializer.validated_data.get("parent")
        if parent is None or parent.company_id != company.pk:
            raise ValidationError({"parent": ["Choose the group this one sits under."]})
        _unique_group_name(company, name)
        group = LedgerGroup.objects.create(
            company=company,
            name=name,
            parent=parent,
            nature=parent.nature,
            affects_gross_profit=parent.affects_gross_profit,
        )
        return Response(LedgerGroupSerializer(group).data, status=status.HTTP_201_CREATED)


class LedgerGroupDetailView(APIView):
    permission_classes = [Signed]

    def _editable(self, request, pk: int) -> LedgerGroup:
        _check(request, EDIT)
        group = LedgerGroup.objects.select_for_update().filter(pk=pk).first()
        if group is None or not visible_companies(request.user).filter(pk=group.company_id):
            raise NotFound("No such group.")
        if group.is_standard:
            raise ValidationError(
                {"detail": "Standard groups come with MyERP and cannot be changed."}
            )
        return group

    @tenant_atomic()
    def patch(self, request, pk: int):
        group = self._editable(request, pk)
        serializer = LedgerGroupSerializer(group, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "name" in data:
            group.name = data["name"].strip()
            _unique_group_name(group.company, group.name, exclude=group.pk)
        if "parent" in data:
            parent = data["parent"]
            if parent is None or parent.company_id != group.company_id:
                raise ValidationError({"parent": ["Choose the group this one sits under."]})
            if parent.pk == group.pk or parent.pk in group.descendant_ids():
                raise ValidationError({"parent": ["A group cannot sit under itself."]})
            group.parent = parent
            # Moving under another primary group changes the nature of the
            # whole branch of the tree. (Once ledgers exist, this must be
            # refused for groups whose ledgers have postings.)
            group.nature = parent.nature
            group.affects_gross_profit = parent.affects_gross_profit
            LedgerGroup.objects.filter(pk__in=group.descendant_ids()).update(
                nature=parent.nature, affects_gross_profit=parent.affects_gross_profit
            )
        group.save()
        return Response(LedgerGroupSerializer(group).data)

    @tenant_atomic()
    def delete(self, request, pk: int):
        group = self._editable(request, pk)
        if group.children.exists():
            raise ValidationError({"detail": "Move or delete the groups under this one first."})
        if group.ledgers.exists():
            raise ValidationError({"detail": "Move or delete the ledgers in this group first."})
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _unique_group_name(company, name: str, exclude: int | None = None) -> None:
    clash = LedgerGroup.objects.annotate(lname=Lower("name")).filter(
        company=company, lname=name.lower()
    )
    if exclude is not None:
        clash = clash.exclude(pk=exclude)
    if clash.exists():
        raise ValidationError({"name": ["This company already has a group by that name."]})
    if Ledger.objects.filter(company=company, name__iexact=name).exists():
        raise ValidationError({"name": ["This company already has a ledger by that name."]})


def _unique_ledger_name(company, name: str, exclude: int | None = None) -> None:
    clash = Ledger.objects.filter(company=company, name__iexact=name)
    if exclude is not None:
        clash = clash.exclude(pk=exclude)
    if clash.exists():
        raise ValidationError({"name": ["This company already has a ledger by that name."]})
    if LedgerGroup.objects.filter(company=company, name__iexact=name).exists():
        raise ValidationError({"name": ["This company already has a group by that name."]})


def _ledger_data(ledger: Ledger, data: dict) -> dict:
    """Bank details only belong on bank ledgers."""
    group = data.get("group", getattr(ledger, "group", None))
    if group is not None and group.company_id != ledger.company_id:
        raise ValidationError({"group": ["Choose a group of this company."]})
    if group is not None and not group.is_bank_group():
        data = {**data, **dict.fromkeys(BANK_FIELDS, "")}
    if "name" in data:
        data["name"] = data["name"].strip()
    if data.get("currency") is not None:
        if data["currency"].code == ledger.company.base_currency:
            data["currency"] = None
        elif not ledger.company.multi_currency:
            raise ValidationError(
                {"currency": ["Turn on multiple currencies for this company first."]}
            )
    return data


class LedgerListView(APIView):
    """GET ?q=text&group=id (group includes the groups under it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        ledgers = company.ledgers.select_related("group").prefetch_related("opening_bills")
        if q := request.query_params.get("q", "").strip():
            ledgers = ledgers.filter(Q(name__icontains=q) | Q(account_number__icontains=q))
        if group_id := request.query_params.get("group"):
            group = company.ledger_groups.filter(pk=group_id).first()
            if group is None:
                raise NotFound("No such group.")
            ledgers = ledgers.filter(group_id__in={group.pk, *group.descendant_ids()})
        return Response(LedgerSerializer(ledgers, many=True).data)

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = LedgerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ledger = Ledger(company=company)
        data = _ledger_data(ledger, dict(serializer.validated_data))
        bills = data.pop("opening_bills", None)
        if "bill_wise" not in data:
            data["bill_wise"] = data["group"].is_under(BILL_WISE_GROUP_CODES)
        _unique_ledger_name(company, data["name"])
        _save(ledger, data, LEDGER_FIELDS)
        _set_foreign_opening(ledger)
        _save_opening_bills(ledger, bills)
        return Response(LedgerSerializer(ledger).data, status=status.HTTP_201_CREATED)


class LedgerDetailView(APIView):
    permission_classes = [Signed]

    def _ledger(self, request, pk: int) -> Ledger:
        _check(request, EDIT)
        ledger = Ledger.objects.select_for_update().filter(pk=pk).first()
        if ledger is None or not visible_companies(request.user).filter(pk=ledger.company_id):
            raise NotFound("No such ledger.")
        return ledger

    @tenant_atomic()
    def patch(self, request, pk: int):
        ledger = self._ledger(request, pk)
        serializer = LedgerSerializer(ledger, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = _ledger_data(ledger, dict(serializer.validated_data))
        bills = data.pop("opening_bills", None)
        if "name" in data:
            _unique_ledger_name(ledger.company, data["name"], exclude=ledger.pk)
        _save(ledger, data, LEDGER_FIELDS)
        _set_foreign_opening(ledger)
        _save_opening_bills(ledger, bills)
        return Response(LedgerSerializer(ledger).data)
