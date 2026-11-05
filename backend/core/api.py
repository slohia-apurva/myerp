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

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.db.models.functions import Lower
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from core import india
from core.companies import create_company, visible_companies
from core.models import Branch, Company, Ledger, LedgerGroup
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


class CompanySerializer(serializers.ModelSerializer):
    state = serializers.SerializerMethodField()
    # Checked by the model after being upper-cased here.
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    pan = serializers.CharField(max_length=10, allow_blank=True, required=False)
    validate_gstin = validate_pan = staticmethod(_upper)

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "abbr",
            "gstin",
            "pan",
            "state_code",
            "state",
            "address",
            "pincode",
            "fiscal_year_start_month",
            "base_currency",
        ]
        read_only_fields = ["base_currency"]
        # Uniqueness is checked case-insensitively in the views.
        extra_kwargs = {"name": {"validators": []}, "abbr": {"required": False, "validators": []}}

    def get_state(self, company) -> str:
        return india.STATES.get(company.state_code, "")


class BranchSerializer(serializers.ModelSerializer):
    gstin = serializers.CharField(max_length=15, allow_blank=True, required=False)
    validate_gstin = staticmethod(_upper)

    class Meta:
        model = Branch
        fields = ["id", "name", "state_code", "gstin", "address", "is_head_office", "is_active"]
        read_only_fields = ["is_head_office"]


class LedgerGroupSerializer(serializers.ModelSerializer):
    ledger_count = serializers.IntegerField(read_only=True, default=0)
    is_bank = serializers.SerializerMethodField()

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
        ]
        read_only_fields = ["nature", "affects_gross_profit", "code", "is_standard"]

    def get_is_bank(self, group) -> bool:
        return group.is_bank_group()


BANK_FIELDS = ["bank_name", "account_number", "ifsc", "bank_branch"]


class LedgerSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    nature = serializers.CharField(source="group.nature", read_only=True)
    ifsc = serializers.CharField(max_length=11, allow_blank=True, required=False)
    validate_ifsc = staticmethod(_upper)

    class Meta:
        model = Ledger
        fields = ["id", "name", "group", "group_name", "nature", "is_active", "notes", *BANK_FIELDS]


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


class StatesView(APIView):
    permission_classes = [Signed]

    def get(self, request):
        return Response([{"code": c, "name": n} for c, n in india.STATE_CHOICES])


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
        fields = ["name", "gstin", "pan", "state_code", "address", "pincode"]
        _save(company, data, [*fields, "fiscal_year_start_month"])
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
        _save(branch, {**serializer.validated_data, "name": name}, BranchSerializer.Meta.fields)
        return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)


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
        _save(branch, data, ["name", "state_code", "gstin", "address", "is_active"])
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
    return data


class LedgerListView(APIView):
    """GET ?q=text&group=id (group includes the groups under it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        ledgers = company.ledgers.select_related("group")
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
        _unique_ledger_name(company, data["name"])
        _save(ledger, data, ["name", "group", "is_active", "notes", *BANK_FIELDS])
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
        if "name" in data:
            _unique_ledger_name(ledger.company, data["name"], exclude=ledger.pk)
        _save(ledger, data, ["name", "group", "is_active", "notes", *BANK_FIELDS])
        return Response(LedgerSerializer(ledger).data)
