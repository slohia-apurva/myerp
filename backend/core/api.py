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
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from audit import recorder
from core import duplicates, india, print_mark
from core import modules as company_modules
from core.companies import create_company, visible_companies
from core.locks import lock_status, refuse_key_changes
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
    Party,
)
from core.parties import PartySerializer, save_party
from core.stores import sync_default_store
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


CONTACT_FIELDS = ["address", "pincode", "city", "phone", "email", "contact_person"]
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
    # The image under Printing: the company's own upload, else the standard one.
    print_image = serializers.SerializerMethodField()
    print_image_own = serializers.SerializerMethodField()

    def get_print_image(self, company) -> str:
        return print_mark.data_url(*print_mark.image_of(company))

    def get_print_image_own(self, company) -> bool:
        return bool(company.print_image)

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
            "city",
            "phone",
            "email",
            "contact_person",
            "fiscal_year_start_month",
            "books_start",
            "multi_currency",
            "modules",
            "print_ganesha",
            "print_image",
            "print_image_own",
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
            "no_stock",
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
            "schedule_iii",
            "ledger_count",
            "is_bank",
            "bill_wise_default",
            "is_active",
        ]
        read_only_fields = ["nature", "affects_gross_profit", "code", "is_standard", "schedule_iii"]

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
    party = PartySerializer(required=False, allow_null=True)
    lock = serializers.SerializerMethodField()

    def get_lock(self, ledger) -> dict:
        return lock_status("ledger", ledger)

    # Link a new ledger to a party another company has (decision 0020) and
    # add the party's ledger to more companies.
    party_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    also_in = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True
    )

    def to_representation(self, ledger):
        data = super().to_representation(ledger)
        if data.get("party") is not None:
            data["party"]["credit_limit"] = str(ledger.credit_limit)
            # Each company's own salesman or purchaser.
            data["party"]["salesman"] = ledger.salesman_id
            data["party"]["salesman_name"] = (
                ledger.salesman.display_name if ledger.salesman_id else ""
            )
            data["party"]["preferred_transporter"] = ledger.preferred_transporter_id
            data["party"]["preferred_transporter_name"] = (
                ledger.preferred_transporter.name if ledger.preferred_transporter_id else ""
            )
        return data

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
            "party",
            "party_id",
            "also_in",
            "lock",
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
        recorder.touch(ledger)
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
        recorder.touch(ledger)
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
        data["name"] = duplicates.tidy(data["name"])
        _unique_company(data)
        try:
            company = create_company(**data)
        except DjangoValidationError as exc:
            raise _django_errors(exc) from exc
        return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)


def _unique_company(data: dict, exclude: int | None = None) -> None:
    """No two companies with the same name, short code, GSTIN or PAN."""
    if "name" in data:
        duplicates.check_name(
            Company.objects.all(),
            data["name"],
            exclude=exclude,
            kind="company",
            message='There is already a company named "{name}".',
        )
    others = Company.objects.exclude(pk=exclude)
    for field, label in (("abbr", "short code"), ("gstin", "GSTIN"), ("pan", "PAN")):
        value = (data.get(field) or "").strip().upper()
        clash = others.filter(**{f"{field}__iexact": value}).first() if value else None
        if clash is not None:
            duplicates.refuse(
                field,
                f'The company "{clash.name}" already has this {label}.',
                clash,
                "company",
                company=clash.pk,
            )


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
                    company.ledger_groups.select_related("parent__parent__parent")
                    .annotate(ledger_count=Count("ledgers"))
                    # Meta.ordering is dropped from GROUP BY queries.
                    .order_by("sequence", "name"),
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
        if "name" in data:
            data["name"] = duplicates.tidy(data["name"])
        _unique_company(data, exclude=pk)
        old_pan = company.pan
        # Fiscal year start can change only until vouchers exist (a later piece
        # will refuse it then).
        fields = ["name", "gstin", "pan", *REGISTRATION_FIELDS, "state_code", *CONTACT_FIELDS]
        if "modules" in data and data["modules"] != company.modules and not request.user.is_owner:
            raise PermissionDenied("Only an Owner can change a company's modules.")
        extra = [
            "fiscal_year_start_month",
            "books_start",
            "multi_currency",
            "modules",
            "print_ganesha",
        ]
        refuse_key_changes("company", company, data)
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
        branch = save_branch(Branch(company=company), dict(serializer.validated_data))
        return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)


BRANCH_FIELDS = [
    "name",
    "state_code",
    "gstin",
    *CONTACT_FIELDS,
    "is_active",
    *DEFAULT_FLAGS,
    "no_stock",
]


def save_branch(branch: Branch, data: dict) -> Branch:
    """Add (branch not yet saved, its company set) or change a branch: the
    screen and imports both save here."""
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
        _unique_branch_name(branch.company, data["name"], exclude=branch.pk)
    if branch.pk:
        refuse_key_changes("branch", branch, data)
    if branch.pk and data.get("no_stock") and branch.locations.exclude(is_default=True).exists():
        raise ValidationError(
            {"no_stock": ["This branch has racks, bins or areas; disable them instead."]}
        )
    _move_defaults(branch, data)
    _save(branch, data, BRANCH_FIELDS)
    sync_default_store(branch)
    return branch


def _unique_branch_name(company, name: str, exclude: int | None = None) -> None:
    duplicates.check_name(
        company.branches.all(),
        name,
        exclude=exclude,
        kind="branch",
        message='This company already has a branch named "{name}".',
    )


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
        certificate = save_certificate(
            Certificate(company=company), dict(serializer.validated_data)
        )
        return Response(CertificateSerializer(certificate).data, status=status.HTTP_201_CREATED)


def save_certificate(certificate: Certificate, data: dict) -> Certificate:
    """Add or change a licence or certificate (screen and imports)."""
    branch = data.get("branch")
    if branch is not None and branch.company_id != certificate.company_id:
        raise ValidationError({"branch": ["Pick a branch of this company."]})
    _save(certificate, data, CERTIFICATE_FIELDS)
    return certificate


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
        save_certificate(certificate, dict(serializer.validated_data))
        return Response(CertificateSerializer(certificate).data)


def _move_defaults(branch: Branch, data: dict) -> None:
    """Ticking a default on this branch takes it off the company's other
    branch. Unticking is refused: every company keeps one of each default."""
    for flag in DEFAULT_FLAGS:
        if flag not in data:
            continue
        if data[flag]:
            others = Branch.objects.filter(company_id=branch.company_id, **{flag: True})
            # One by one, not .update(), so the audit log sees each change.
            for other in others.exclude(pk=branch.pk):
                setattr(other, flag, False)
                other.save(update_fields=[flag])
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
        save_branch(branch, dict(serializer.validated_data))
        return Response(BranchSerializer(branch).data)


class LedgerGroupListView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, EDIT)
        company = _company(request, pk)
        serializer = LedgerGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = save_ledger_group(company, None, dict(serializer.validated_data))
        return Response(LedgerGroupSerializer(group).data, status=status.HTTP_201_CREATED)


def save_ledger_group(company, group: LedgerGroup | None, data: dict) -> LedgerGroup:
    """Add a group under another (group None) or change one the company added
    (screen and imports). Standard groups cannot change; saving one as it is
    does nothing."""
    if group is None:
        name = duplicates.tidy(data.get("name") or "")
        parent = data.get("parent")
        if parent is None or parent.company_id != company.pk:
            raise ValidationError({"parent": ["Choose the group this one sits under."]})
        if not parent.is_active:
            raise ValidationError({"parent": [f"{parent.name} is disabled."]})
        _unique_group_name(company, name)
        return LedgerGroup.objects.create(
            company=company,
            name=name,
            parent=parent,
            nature=parent.nature,
            affects_gross_profit=parent.affects_gross_profit,
        )
    if group.is_standard:
        if data.get("is_active") is False:
            raise ValidationError({"detail": "Standard groups cannot be disabled."})
        renamed = "name" in data and duplicates.tidy(data["name"]) != group.name
        moved = "parent" in data and data["parent"] != group.parent
        if renamed or moved:
            raise ValidationError(
                {"detail": "Standard groups come with MyERP and cannot be changed."}
            )
        return group
    if "name" in data:
        group.name = duplicates.tidy(data["name"])
        _unique_group_name(group.company, group.name, exclude=group.pk)
    if "parent" in data and data["parent"] != group.parent:
        refuse_key_changes("ledger_group", group, {"parent": data["parent"]})
        parent = data["parent"]
        if parent is None or parent.company_id != group.company_id:
            raise ValidationError({"parent": ["Choose the group this one sits under."]})
        if not parent.is_active:
            raise ValidationError({"parent": [f"{parent.name} is disabled."]})
        if parent.pk == group.pk or parent.pk in group.descendant_ids():
            raise ValidationError({"parent": ["A group cannot sit under itself."]})
        group.parent = parent
        # Moving under another primary group changes the nature of the
        # whole branch of the tree. Refused above once the group's ledgers
        # have postings (core/locks.py).
        group.nature = parent.nature
        group.affects_gross_profit = parent.affects_gross_profit
        LedgerGroup.objects.filter(pk__in=group.descendant_ids()).update(
            nature=parent.nature, affects_gross_profit=parent.affects_gross_profit
        )
    if "is_active" in data and data["is_active"] != group.is_active:
        if not data["is_active"]:
            if group.children.filter(is_active=True).exists():
                raise ValidationError({"is_active": ["Disable the groups under this one first."]})
            if group.ledgers.filter(is_active=True).exists():
                raise ValidationError(
                    {"is_active": ["Disable or move the ledgers in this group first."]}
                )
        elif group.parent is not None and not group.parent.is_active:
            raise ValidationError({"is_active": [f"Enable {group.parent.name} first."]})
        group.is_active = data["is_active"]
    group.save()
    return group


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
        save_ledger_group(group.company, group, dict(serializer.validated_data))
        return Response(LedgerGroupSerializer(group).data)


def _unique_group_name(company, name: str, exclude: int | None = None) -> None:
    duplicates.check_name(
        company.ledger_groups.all(),
        name,
        exclude=exclude,
        kind="ledger_group",
        message='This company already has a group named "{name}".',
    )
    duplicates.check_name(
        company.ledgers.all(),
        name,
        kind="ledger",
        message='This company already has a ledger named "{name}".',
    )


def _unique_ledger_name(company, name: str, exclude: int | None = None) -> None:
    """Ledgers and groups share one list of names in a company."""
    duplicates.check_name(
        company.ledgers.all(),
        name,
        exclude=exclude,
        kind="ledger",
        message='This company already has a ledger named "{name}".',
    )
    duplicates.check_name(
        company.ledger_groups.all(),
        name,
        kind="ledger_group",
        message='This company already has a group named "{name}".',
    )


def _unique_account_number(ledger: Ledger, number: str) -> None:
    """One bank ledger per bank account in a company."""
    number = number.strip()
    if not number:
        return
    clash = (
        Ledger.objects.filter(company_id=ledger.company_id, account_number__iexact=number)
        .exclude(pk=ledger.pk)
        .first()
    )
    if clash is not None:
        duplicates.refuse(
            "account_number",
            f'The ledger "{clash.name}" already has this bank account number.',
            clash,
            "ledger",
        )


def _ledger_data(ledger: Ledger, data: dict) -> dict:
    """Bank details only belong on bank ledgers."""
    group = data.get("group", getattr(ledger, "group", None))
    if group is not None and group.company_id != ledger.company_id:
        raise ValidationError({"group": ["Choose a group of this company."]})
    if group is not None and not group.is_active and group != getattr(ledger, "group", None):
        raise ValidationError({"group": [f"{group.name} is disabled."]})
    if group is not None and not group.is_bank_group():
        data = {**data, **dict.fromkeys(BANK_FIELDS, "")}
    if "name" in data:
        data["name"] = duplicates.tidy(data["name"])
    if data.get("account_number"):
        _unique_account_number(ledger, data["account_number"])
    if data.get("currency") is not None:
        if data["currency"].code == ledger.company.base_currency:
            data["currency"] = None
        elif not ledger.company.multi_currency:
            raise ValidationError(
                {"currency": ["Turn on multiple currencies for this company first."]}
            )
    return data


def add_ledger(request, company, data: dict) -> Ledger:
    """Save a new ledger from validated LedgerSerializer data: the Ledgers
    screen's Save, and each new row of an imported file."""
    ledger = Ledger(company=company)
    data = _ledger_data(ledger, data)
    bills = data.pop("opening_bills", None)
    party = data.pop("party", None)
    party_id = data.pop("party_id", None)
    also_in = _also_in(request, data.pop("also_in", None))
    if "bill_wise" not in data:
        data["bill_wise"] = data["group"].is_under(BILL_WISE_GROUP_CODES)
    _unique_ledger_name(company, data["name"])
    _save(ledger, data, LEDGER_FIELDS)
    _set_foreign_opening(ledger)
    _save_opening_bills(ledger, bills)
    save_party(ledger, party, party_id, also_in)
    return ledger


def change_ledger(request, ledger: Ledger, data: dict) -> Ledger:
    """Save changes to a ledger (validated, partial LedgerSerializer data)."""
    data = _ledger_data(ledger, data)
    bills = data.pop("opening_bills", None)
    party = data.pop("party", None)
    data.pop("party_id", None)  # only when adding a ledger
    also_in = _also_in(request, data.pop("also_in", None))
    if "name" in data:
        _unique_ledger_name(ledger.company, data["name"], exclude=ledger.pk)
    refuse_key_changes("ledger", ledger, data)
    if ledger.system_code and data.get("is_active") is False:
        raise ValidationError(
            {"is_active": ["MyERP posts to this ledger itself, so it cannot be disabled."]}
        )
    _save(ledger, data, LEDGER_FIELDS)
    _set_foreign_opening(ledger)
    _save_opening_bills(ledger, bills)
    save_party(ledger, party, None, also_in)
    return ledger


class LedgerListView(APIView):
    """GET ?q=text&group=id (group includes the groups under it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        ledgers = company.ledgers.select_related(
            "group", "party", "salesman", "preferred_transporter"
        ).prefetch_related(
            "opening_bills", "party__addresses", "party__contacts", "party__ledgers__company"
        )
        if q := request.query_params.get("q", "").strip():
            ledgers = ledgers.filter(
                Q(name__icontains=q)
                | Q(account_number__icontains=q)
                | Q(party__customer_number__icontains=q)
                | Q(party__vendor_number__icontains=q)
            )
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
        ledger = add_ledger(request, company, dict(serializer.validated_data))
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
        change_ledger(request, ledger, dict(serializer.validated_data))
        return Response(LedgerSerializer(ledger).data)


def _also_in(request, ids):
    """The companies, among those this person may work in, to add a
    party's ledger to."""
    if ids is None:
        return None
    companies = visible_companies(request.user).filter(pk__in=ids)
    if companies.count() != len(set(ids)):
        raise ValidationError({"also_in": ["No such company."]})
    return companies


class PartyListView(APIView):
    """GET /parties/?not_in=COMPANY[&side=customer|supplier]: the group's
    customers and suppliers, optionally only those that company has no ledger
    for yet (on that side), to pick when adding a party ledger."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        parties = Party.objects.select_related("credit_term").prefetch_related(
            "addresses", "contacts", "ledgers__company"
        )
        if "not_in" in request.query_params:
            try:
                company = int(request.query_params["not_in"])
            except ValueError:
                raise ValidationError({"not_in": ["Give a number."]}) from None
            # With ?side=customer|supplier, only those without a ledger on that
            # side: a firm can have one customer and one supplier ledger.
            side = request.query_params.get("side")
            if side:
                taken = Ledger.objects.filter(company=company, party_side=side, party__isnull=False)
                parties = parties.exclude(pk__in=taken.values("party"))
            else:
                parties = parties.exclude(ledgers__company=company)
        return Response(PartySerializer(parties.order_by("name"), many=True).data)


class PeopleView(APIView):
    """Active users, for pickers such as a customer's salesman."""

    permission_classes = [Signed]

    def get(self, request):
        _check(request, VIEW)
        from accounts.models import User

        people = User.objects.filter(is_active=True).order_by("full_name", "email")
        return Response([{"id": u.pk, "name": u.display_name} for u in people])
