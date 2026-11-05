import re

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from core import india


class Company(models.Model):
    """A legal entity inside a tenant, e.g. Apurvam Organics LLP.

    Each company keeps its own books, numbering and GST registration. Create
    companies with `core.companies.create_company`, which also adds the head
    office branch and the standard ledger groups.
    """

    name = models.CharField(max_length=200, unique=True)
    # Short code used in document numbers, e.g. AOL/PO/2026-27/0001.
    abbr = models.CharField(max_length=10, unique=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[india.validate_gstin])
    pan = models.CharField(max_length=10, blank=True, validators=[india.validate_pan])
    state_code = models.CharField(max_length=2, validators=[india.validate_state_code])
    address = models.TextField(blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    # Indian companies close their books on 31 March, so the year starts in April.
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        default=4, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    base_currency = models.CharField(max_length=3, default="INR", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.abbr:
            self.abbr = _free_abbr(self.name, exclude=self.pk)
        super().save(*args, **kwargs)

    def clean(self):
        self.gstin = self.gstin.strip().upper()
        self.pan = self.pan.strip().upper()
        self.abbr = self.abbr.strip().upper()
        if self.gstin:
            if not self.pan:
                self.pan = self.gstin[2:12]
            elif self.gstin[2:12] != self.pan:
                raise ValidationError({"pan": "The PAN must match the one inside the GSTIN."})
            if self.state_code and self.gstin[:2] != self.state_code:
                raise ValidationError({"gstin": "This GSTIN belongs to a different state."})
        if self.abbr and not re.fullmatch(r"[A-Z0-9]{2,10}", self.abbr):
            raise ValidationError({"abbr": "Use 2 to 10 letters or digits, e.g. AOL."})
        if self.pincode and not re.fullmatch(r"[1-9][0-9]{5}", self.pincode):
            raise ValidationError({"pincode": "A PIN code is 6 digits."})


def _free_abbr(name: str, exclude=None) -> str:
    """Initials of the name (Apurvam Organics LLP -> AOL), made unique."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    base = "".join(w[0] for w in words).upper()[:8] or "CO"
    if len(base) < 2:
        base = (words[0][:3] if words else "CO").upper()
    taken = set(Company.objects.exclude(pk=exclude).values_list("abbr", flat=True))
    abbr, n = base, 2
    while abbr in taken:
        abbr, n = f"{base}{n}", n + 1
    return abbr


class Branch(models.Model):
    """A place a company does business from: head office, factory, depot,
    shop. Every voucher, GL row and stock row will carry a branch (rule 19).

    A branch in another state has its own GSTIN under the company's PAN.
    """

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="branches")
    name = models.CharField(max_length=100)
    state_code = models.CharField(max_length=2, validators=[india.validate_state_code])
    gstin = models.CharField(max_length=15, blank=True, validators=[india.validate_gstin])
    address = models.TextField(blank=True)
    is_head_office = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_head_office", "name"]
        verbose_name_plural = "branches"
        constraints = [
            models.UniqueConstraint(
                "company", Lower("name"), name="branch_name_unique_per_company"
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(is_head_office=True),
                name="one_head_office_per_company",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        self.gstin = self.gstin.strip().upper()
        if self.gstin:
            if self.state_code and self.gstin[:2] != self.state_code:
                raise ValidationError({"gstin": "This GSTIN belongs to a different state."})
            if self.company.pan and self.gstin[2:12] != self.company.pan:
                raise ValidationError({"gstin": "A branch GSTIN must be under the company's PAN."})
        if self.is_head_office and not self.is_active:
            raise ValidationError({"is_active": "The head office cannot be deactivated."})


class LedgerGroup(models.Model):
    """A node in a company's chart of accounts, Tally style (decision 0005).

    Groups nest to any depth. Nature comes from the primary group at the top
    and is copied down so reports need not walk the tree. Ledgers (next
    piece) sit under groups; only ledgers take postings.
    """

    ASSET, LIABILITY, INCOME, EXPENSE = "asset", "liability", "income", "expense"
    NATURES = [
        (ASSET, "Asset"),
        (LIABILITY, "Liability"),
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="ledger_groups")
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    nature = models.CharField(max_length=10, choices=NATURES)
    # Sales, Purchase, Direct Incomes/Expenses: shown in the trading account
    # above gross profit.
    affects_gross_profit = models.BooleanField(default=False)
    # Standard groups have a fixed code that posting rules use to find them,
    # e.g. sundry_debtors; groups people add have none.
    code = models.SlugField(max_length=50, blank=True)
    is_standard = models.BooleanField(default=False)
    sequence = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["sequence", "name"]
        constraints = [
            models.UniqueConstraint(
                "company", Lower("name"), name="ledger_group_name_unique_per_company"
            ),
            models.UniqueConstraint(
                fields=["company", "code"],
                condition=~models.Q(code=""),
                name="ledger_group_code_unique_per_company",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def is_bank_group(self) -> bool:
        """Under Bank Accounts or Bank OD A/c, at any depth."""
        group = self
        while group is not None:
            if group.code in BANK_GROUP_CODES:
                return True
            group = group.parent
        return False

    def descendant_ids(self) -> set[int]:
        found, frontier = set(), {self.pk}
        while frontier:
            frontier = set(
                LedgerGroup.objects.filter(parent_id__in=frontier).values_list("pk", flat=True)
            )
            found |= frontier
        return found


BANK_GROUP_CODES = ("bank_accounts", "bank_od")


class Ledger(models.Model):
    """An account that takes postings, e.g. HDFC Current A/c or Freight
    Inward. Every ledger sits under a group and takes its nature from it.

    Opening balances and postings arrive with vouchers; a ledger with
    postings can then only be deactivated, not deleted.
    """

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="ledgers")
    group = models.ForeignKey(LedgerGroup, on_delete=models.PROTECT, related_name="ledgers")
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True)
    # For ledgers under Bank Accounts or Bank OD A/c.
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=34, blank=True)
    ifsc = models.CharField(max_length=11, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "company", Lower("name"), name="ledger_name_unique_per_company"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def nature(self) -> str:
        return self.group.nature

    def clean(self):
        self.ifsc = self.ifsc.strip().upper()
        self.account_number = self.account_number.strip()
        if self.group.company_id != self.company_id:
            raise ValidationError({"group": "Choose a group of this company."})
        if self.ifsc and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", self.ifsc):
            raise ValidationError({"ifsc": "An IFSC is 11 characters like HDFC0001234."})
