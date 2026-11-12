import re
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from core import india, modules


class Currency(models.Model):
    """A currency the tenant deals in, e.g. USD. INR is the base currency of
    every company; others are used only when a company turns on multiple
    currencies."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=60)
    symbol = models.CharField(max_length=5, blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "currencies"

    def __str__(self) -> str:
        return self.code


class Company(models.Model):
    """A legal entity inside a tenant, e.g. Apurvam Organics LLP.

    Each company keeps its own books, numbering and GST registration. Create
    companies with `core.companies.create_company`, which also adds the head
    office branch and the standard ledger groups.
    """

    PROPRIETORSHIP, PARTNERSHIP, LLP = "proprietorship", "partnership", "llp"
    PRIVATE, PUBLIC, OPC = "private_limited", "public_limited", "opc"
    ENTITY_TYPES = [
        (PROPRIETORSHIP, "Proprietorship"),
        (PARTNERSHIP, "Partnership firm"),
        (LLP, "LLP"),
        (PRIVATE, "Private limited company"),
        (PUBLIC, "Public limited company"),
        (OPC, "One person company"),
    ]
    REGISTERED_WITH_MCA = (LLP, PRIVATE, PUBLIC, OPC)

    name = models.CharField(max_length=200)
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPES, blank=True)
    # CIN for companies, LLPIN for LLPs (both from the MCA).
    cin = models.CharField(max_length=21, blank=True)
    incorporation_date = models.DateField(null=True, blank=True)
    tan = models.CharField(max_length=10, blank=True, validators=[india.validate_tan])
    # Short code used in document numbers, e.g. AOL/PO/2026-27/0001.
    abbr = models.CharField(max_length=10, unique=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[india.validate_gstin])
    pan = models.CharField(max_length=10, blank=True, validators=[india.validate_pan])
    state_code = models.CharField(max_length=2, validators=[india.validate_state_code])
    address = models.TextField(blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    city = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[india.validate_phone])
    email = models.EmailField(blank=True)
    contact_person = models.CharField(max_length=100, blank=True)
    # Indian companies close their books on 31 March, so the year starts in April.
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        default=4, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    base_currency = models.CharField(max_length=3, default="INR", editable=False)
    # Exports, imports, EEFC accounts: ledgers and bills in other currencies.
    multi_currency = models.BooleanField(default=False)
    # Module codes this company uses (core.modules); Accounts is always on.
    modules = models.JSONField(default=modules.all_modules)
    # "Books beginning from": opening balances are as at the start of this day.
    books_start = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"
        # No duplicates (core/duplicates.py): names ignore capitals; GSTIN
        # and PAN, when given, belong to one company only.
        constraints = [
            models.UniqueConstraint(Lower("name"), name="company_name_unique"),
            models.UniqueConstraint(
                "gstin", condition=~models.Q(gstin=""), name="company_gstin_unique"
            ),
            models.UniqueConstraint("pan", condition=~models.Q(pan=""), name="company_pan_unique"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.abbr:
            self.abbr = _free_abbr(self.name, exclude=self.pk)
        if self.books_start is None:
            self.books_start = fiscal_year_start(date.today(), self.fiscal_year_start_month)
        super().save(*args, **kwargs)

    def clean(self):
        self.gstin = self.gstin.strip().upper()
        self.pan = self.pan.strip().upper()
        self.abbr = self.abbr.strip().upper()
        for field in ("cin", "tan"):
            setattr(self, field, getattr(self, field).strip().upper())
        if self.cin:
            if self.entity_type == self.LLP:
                check = india.validate_llpin
            elif self.entity_type in self.REGISTERED_WITH_MCA:
                check = india.validate_cin
            else:
                raise ValidationError(
                    {"cin": "Only companies and LLPs have a CIN or LLPIN; pick the type first."}
                )
            try:
                check(self.cin)
            except ValidationError as exc:
                raise ValidationError({"cin": exc.messages}) from exc
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


class FiscalYear(models.Model):
    """A company's financial year, in whole months, split into monthly periods
    that can be locked (spec 01, "Fiscal year / period"). Years of one company
    never overlap. Never deleted, only made inactive."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="fiscal_years")
    name = models.CharField(max_length=20)  # e.g. 2026-27
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["company", "start_date"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "company", name="fiscal_year_name_unique"),
            models.UniqueConstraint(fields=["company", "start_date"], name="fiscal_year_start"),
        ]

    def __str__(self) -> str:
        return self.name


class FiscalPeriod(models.Model):
    """One month of a fiscal year. While locked, nothing posts into it."""

    year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name="periods")
    start_date = models.DateField()
    end_date = models.DateField()
    is_locked = models.BooleanField(default=False)

    class Meta:
        ordering = ["start_date"]
        constraints = [models.UniqueConstraint(fields=["year", "start_date"], name="period_start")]

    def __str__(self) -> str:
        return f"{self.start_date:%b %Y}"


def fiscal_year_start(day: date, start_month: int) -> date:
    """First day of the financial year that `day` falls in."""
    year = day.year if day.month >= start_month else day.year - 1
    return date(year, start_month, 1)


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
    pincode = models.CharField(max_length=6, blank=True)
    city = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[india.validate_phone])
    email = models.EmailField(blank=True)
    contact_person = models.CharField(max_length=100, blank=True)
    is_head_office = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # The address picked first on documents; each can be changed per document.
    default_billing = models.BooleanField(default=False)
    default_ship_to = models.BooleanField(default=False)
    default_ship_from = models.BooleanField(default=False)
    # A branch that is a physical warehouse: it holds racks, bins and areas.
    is_warehouse = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_head_office", "name"]
        verbose_name_plural = "branches"
        constraints = [
            *(
                models.UniqueConstraint(
                    fields=["company"],
                    condition=models.Q(**{flag: True}),
                    name=f"one_{flag}_per_company",
                )
                for flag in ("default_billing", "default_ship_to", "default_ship_from")
            ),
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
        if self.pincode and not re.fullmatch(r"[1-9][0-9]{5}", self.pincode):
            raise ValidationError({"pincode": "A PIN code is 6 digits."})
        if self.is_head_office and not self.is_active:
            raise ValidationError({"is_active": "The head office cannot be deactivated."})
        if not self.is_active and (
            self.default_billing or self.default_ship_to or self.default_ship_from
        ):
            raise ValidationError(
                {"is_active": "Move this branch's default addresses before closing it."}
            )


class WarehouseLocation(models.Model):
    """A place inside a warehouse branch. A rack stands in the warehouse and
    holds bins; a bin is a physical storage location on a rack; an area is a
    named zone of the warehouse (production, receiving, despatch...) that
    stock can also sit in. Stock entries will point at a bin or an area."""

    RACK, BIN, AREA = "rack", "bin", "area"
    KINDS = [(RACK, "Rack"), (BIN, "Bin"), (AREA, "Area")]
    PURPOSES = [
        ("receiving", "Receiving"),
        ("storage", "Storage"),
        ("production", "Production"),
        ("quality", "Quality check"),
        ("quarantine", "Quarantine"),
        ("packing", "Packing"),
        ("despatch", "Despatch"),
        ("other", "Other"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="locations")
    kind = models.CharField(max_length=4, choices=KINDS)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )  # a bin's rack
    name = models.CharField(max_length=60)
    purpose = models.CharField(max_length=12, choices=PURPOSES, blank=True)  # areas only
    notes = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["branch_id", "kind", "name"]
        constraints = [
            models.UniqueConstraint(
                "branch",
                "kind",
                Lower("name"),
                condition=models.Q(parent__isnull=True),
                name="location_name_unique_in_branch",
            ),
            models.UniqueConstraint(
                "parent",
                Lower("name"),
                condition=models.Q(parent__isnull=False),
                name="bin_name_unique_in_rack",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.parent.name} / {self.name}" if self.parent_id else self.name


class Certificate(models.Model):
    """A licence, registration or certificate the company must keep valid:
    FSSAI licence, organic (NPOP) scope certificate, ISO / FSSC 22000, LUT,
    factory licence, pollution consent. Kept on its own list so renewals can
    be reminded. Never deleted: a renewed certificate is a new row and the
    old one stays as history."""

    FSSAI, UDYAM, IEC, ORGANIC, ISO, FSSC, LUT, FACTORY, POLLUTION, TRADE, OTHER = (
        "fssai",
        "udyam",
        "iec",
        "organic",
        "iso",
        "fssc",
        "lut",
        "factory",
        "pollution",
        "trade",
        "other",
    )
    KINDS = [
        (FSSAI, "FSSAI licence / registration"),
        (UDYAM, "Udyam (MSME) registration"),
        (IEC, "IEC (importer-exporter code)"),
        (ORGANIC, "Organic certificate (NPOP / NOP / EU)"),
        (ISO, "ISO certificate"),
        (FSSC, "FSSC 22000"),
        (LUT, "LUT for exports"),
        (FACTORY, "Factory licence"),
        (POLLUTION, "Pollution control consent"),
        (TRADE, "Shop / trade licence"),
        (OTHER, "Other"),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="certificates")
    # Premises-wise licences (FSSAI, factory) belong to a branch; blank = whole company.
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="certificates"
    )
    kind = models.CharField(max_length=20, choices=KINDS)
    name = models.CharField(max_length=100, blank=True)  # e.g. "ISO 9001:2015"
    number = models.CharField(max_length=60)
    issued_by = models.CharField(max_length=100, blank=True)
    valid_from = models.DateField(null=True, blank=True)
    # Renewal (expiry) date; blank for certificates that do not lapse.
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["kind", "-valid_until"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.number}"

    def clean(self):
        self.number = self.number.strip()
        check = {
            self.FSSAI: india.validate_fssai,
            self.UDYAM: india.validate_udyam,
            self.IEC: india.validate_iec,
        }
        if self.kind in (self.UDYAM, self.IEC):
            self.number = self.number.upper()
        if self.kind in check:
            try:
                check[self.kind](self.number)
            except ValidationError as exc:
                raise ValidationError({"number": exc.messages}) from exc
        if self.kind == self.OTHER and not self.name.strip():
            raise ValidationError({"name": "Say what this certificate is."})
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({"valid_until": "The renewal date is before the start date."})
        if self.branch_id and self.branch.company_id != self.company_id:
            raise ValidationError({"branch": "That branch belongs to another company."})


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
    # Where a standard group is reported under Schedule III of the Companies
    # Act (decision 0015); groups people add are reported with their parent.
    schedule_iii = models.CharField(max_length=150, blank=True)

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

    def is_under(self, codes) -> bool:
        """This group or one above it has one of these standard codes."""
        group = self
        while group is not None:
            if group.code in codes:
                return True
            group = group.parent
        return False

    def is_bank_group(self) -> bool:
        return self.is_under(BANK_GROUP_CODES)

    def descendant_ids(self) -> set[int]:
        found, frontier = set(), {self.pk}
        while frontier:
            frontier = set(
                LedgerGroup.objects.filter(parent_id__in=frontier).values_list("pk", flat=True)
            )
            found |= frontier
        return found


BANK_GROUP_CODES = ("bank_accounts", "bank_od")
# Ledgers under these keep balances bill by bill unless told otherwise.
BILL_WISE_GROUP_CODES = ("sundry_debtors", "sundry_creditors")
DR, CR = "dr", "cr"
SIDES = [(DR, "Dr"), (CR, "Cr")]


class Ledger(models.Model):
    """An account that takes postings, e.g. HDFC Current A/c or Freight
    Inward. Every ledger sits under a group and takes its nature from it.

    Ledgers are never deleted (Sidharth, 5 Nov 2026), only deactivated, so
    history always resolves.

    The opening balance is entered on the ledger, as in Tally, as at the
    company's books_start. A bill-wise ledger (customers, suppliers) also
    lists the open bills that make up that balance. See decision 0013.
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
    opening_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(0)]
    )
    opening_side = models.CharField(max_length=2, choices=SIDES, default=DR)
    bill_wise = models.BooleanField(default=False)
    # Blank means the base currency (INR). For a foreign currency ledger the
    # opening balance is also kept in that currency, at the rate given;
    # opening_amount stays the INR value the books carry.
    currency = models.ForeignKey(
        Currency, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    opening_fc_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(0)]
    )
    opening_rate = models.DecimalField(max_digits=18, decimal_places=9, null=True, blank=True)
    # A customer or supplier ledger belongs to a party shared by the whole
    # group (decision 0020); balances, bills and the credit limit stay here.
    party = models.ForeignKey(
        "Party", null=True, blank=True, on_delete=models.PROTECT, related_name="ledgers"
    )
    # Which side of the party this ledger is: a firm that is both customer and
    # supplier may have one ledger under Sundry Debtors and one under Sundry
    # Creditors in the same company (Sidharth, 2026-11-11). Set from the group.
    party_side = models.CharField(
        max_length=8,
        blank=True,
        choices=[("customer", "Customer"), ("supplier", "Supplier")],
    )
    credit_limit = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(0)]
    )  # 0 = no limit
    # Each company has its own salesman (customers) or purchaser (suppliers).
    salesman = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "company", Lower("name"), name="ledger_name_unique_per_company"
            ),
            models.UniqueConstraint(
                fields=["company", "party", "party_side"],
                condition=models.Q(party__isnull=False),
                name="one_ledger_per_party_side_per_company",
            ),
            models.UniqueConstraint(
                "company",
                Lower("account_number"),
                condition=~models.Q(account_number=""),
                name="bank_account_unique_per_company",
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

    @property
    def opening_signed(self) -> Decimal:
        """Debit positive, credit negative."""
        return self.opening_amount if self.opening_side == DR else -self.opening_amount


class LedgerOpeningBill(models.Model):
    """A bill still open on the day the books begin, e.g. an unpaid sales
    invoice from the old system. Together they make up a bill-wise ledger's
    opening balance; receipts and payments will later be set against them."""

    ledger = models.ForeignKey(Ledger, on_delete=models.CASCADE, related_name="opening_bills")
    ref = models.CharField(max_length=50)
    bill_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(
        max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    side = models.CharField(max_length=2, choices=SIDES)
    # Foreign currency ledgers: the bill in its own currency and the rate
    # that gives `amount` in INR.
    fc_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    rate = models.DecimalField(max_digits=18, decimal_places=9, null=True, blank=True)

    class Meta:
        ordering = ["bill_date", "id"]
        constraints = [
            models.UniqueConstraint("ledger", Lower("ref"), name="opening_bill_ref_unique"),
        ]

    def __str__(self) -> str:
        return self.ref

    @property
    def signed(self) -> Decimal:
        return self.amount if self.side == DR else -self.amount


class CreditTerm(models.Model):
    """How a customer pays or a supplier is paid: "30 days", "50% advance,
    50% on delivery". A term is split into parts, each a share of the bill
    falling due at an event (order, dispatch, delivery, bill date) plus some
    days. The parts add up to 100%. Never deleted, only made inactive, so
    old parties and documents keep their terms. One list for the whole
    group of companies. See decisions 0019 and 0020."""

    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="credit_term_name_unique")]

    def __str__(self) -> str:
        return self.name


class Unit(models.Model):
    """A unit of measure (Packet, Carton, Kg ...): one list for the whole
    group of companies, picked by items. Never deleted, only made inactive,
    so items and documents that use a unit keep it."""

    name = models.CharField(max_length=40)
    short_name = models.CharField(max_length=10)
    # The unit quantity code (UQC) GST returns and e-invoices expect.
    gst_code = models.CharField(max_length=3, blank=True)
    whole_numbers = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="unit_name_unique"),
            models.UniqueConstraint(Lower("short_name"), name="unit_short_name_unique"),
        ]

    def __str__(self) -> str:
        return self.name


class ItemGroup(models.Model):
    """A node in the group's tree of item groups (Raw material > Spices >
    Whole spices...), shared by every company like the item catalogue. Groups
    nest to any depth; an item sits in one group. Never deleted, only made
    inactive."""

    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    notes = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="item_group_name_unique")]

    def __str__(self) -> str:
        return self.name


class Brand(models.Model):
    """A brand name items are sold under, picked on the item's General tab.
    One list shared by every company in the group. Never deleted, only made
    inactive."""

    name = models.CharField(max_length=100)
    notes = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="brand_name_unique")]

    def __str__(self) -> str:
        return self.name


class Item(models.Model):
    """A product, material or service, in one catalogue shared by every
    company in the group. Stock is held in the item's stock unit; each item
    also has a chain of other units (packet, inner box, carton, pallet) with
    size, weight and barcode (see ItemUnit and spec 00, "Item units of
    measure"). Never deleted, only made inactive."""

    GOODS, SERVICE = "goods", "service"
    TYPES = [(GOODS, "Goods (stocked)"), (SERVICE, "Service")]

    item_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    item_type = models.CharField(max_length=10, choices=TYPES, default=GOODS)
    stock_unit = models.ForeignKey("Unit", on_delete=models.PROTECT, related_name="stock_items")
    hsn = models.CharField(max_length=8, blank=True)
    # Blank sales/purchase names mean "same as the item name".
    sales_name = models.CharField(max_length=120, blank=True)
    sales_description = models.CharField(max_length=500, blank=True)
    sales_unit = models.ForeignKey(
        "Unit", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    purchase_name = models.CharField(max_length=120, blank=True)
    purchase_description = models.CharField(max_length=500, blank=True)
    purchase_unit = models.ForeignKey(
        "Unit", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    item_group = models.ForeignKey(
        "ItemGroup", null=True, blank=True, on_delete=models.PROTECT, related_name="items"
    )
    brand = models.ForeignKey(
        "Brand", null=True, blank=True, on_delete=models.PROTECT, related_name="items"
    )
    shelf_life_days = models.PositiveIntegerField(null=True, blank=True)
    batch_tracked = models.BooleanField(default=False)
    qc_required = models.BooleanField(default=False)
    notes = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="item_name_unique")]

    def __str__(self) -> str:
        return self.name


USED_FOR = [
    ("purchase", "Purchase"),
    ("sales", "Sales"),
    ("stock", "Stock"),
    ("production", "Production"),
]


def validate_used_for(value):
    allowed = {code for code, _ in USED_FOR}
    if (
        not isinstance(value, list)
        or any(v not in allowed for v in value)
        or len(set(value)) != len(value)
    ):
        raise ValidationError("Pick from purchase, sales, stock and production, each once.")


class ItemUnit(models.Model):
    """One unit of an item. The stock unit's row holds 1; every other row
    says how many of another row's unit it contains, and `factor` (how many
    stock units it is) is worked out from that chain, never typed."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="units")
    unit = models.ForeignKey("Unit", on_delete=models.PROTECT, related_name="+")
    contains_qty = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    contains_unit = models.ForeignKey(
        "Unit", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    factor = models.DecimalField(max_digits=18, decimal_places=6)
    length_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    breadth_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    net_kg = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    gross_kg = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    barcode = models.CharField(max_length=30, blank=True)
    whole_numbers = models.BooleanField(default=True)
    used_for = models.JSONField(default=list, blank=True, validators=[validate_used_for])

    class Meta:
        ordering = ["factor", "id"]
        constraints = [
            models.UniqueConstraint(fields=["item", "unit"], name="item_unit_once"),
            models.UniqueConstraint(
                "barcode",
                condition=~models.Q(barcode=""),
                name="item_unit_barcode_unique",
            ),
        ]

    def __str__(self) -> str:
        return str(self.unit)


class ItemGstRate(models.Model):
    """An item's GST rate from a date. Rates change with the law, so a new
    rate is a new row with its own "from" date; old rows stay, and a bill
    takes the rate whose date is the latest on or before the bill date."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="gst_rates")
    valid_from = models.DateField()
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
    )

    class Meta:
        ordering = ["valid_from"]
        constraints = [
            models.UniqueConstraint(fields=["item", "valid_from"], name="item_gst_rate_date_once")
        ]

    def __str__(self) -> str:
        return f"{self.rate.normalize():f}% from {self.valid_from:%d-%m-%Y}"


class CreditTermPart(models.Model):
    ORDER, DISPATCH, DELIVERY, BILL = "order", "dispatch", "delivery", "bill"
    EVENTS = [
        (ORDER, "With the order (advance)"),
        (DISPATCH, "Before dispatch"),
        (DELIVERY, "On delivery"),
        (BILL, "After the bill date"),
    ]

    term = models.ForeignKey(CreditTerm, on_delete=models.CASCADE, related_name="parts")
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100"))],
    )
    event = models.CharField(max_length=10, choices=EVENTS)
    days = models.PositiveSmallIntegerField(default=0)  # days after the event

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return describe_part(self.percent, self.event, self.days)


def describe_part(percent, event: str, days: int) -> str:
    share = format(Decimal(percent).normalize(), "f")
    if event == CreditTermPart.BILL:
        when = f"{days} days after the bill" if days else "on the bill date"
    else:
        label = {
            CreditTermPart.ORDER: "advance with the order",
            CreditTermPart.DISPATCH: "before dispatch",
            CreditTermPart.DELIVERY: "on delivery",
        }[event]
        when = f"{label} + {days} days" if days else label
    return f"{share}% {when}"


class Party(models.Model):
    """A customer or supplier, shared by every company in the group: GST
    registration, addresses, contacts and credit terms. Each company that
    deals with the party has its own ledger for it under Sundry Debtors or
    Sundry Creditors (Ledger.party), which holds that company's balance,
    bills, credit limit and salesman or purchaser. Decisions 0018 and 0020."""

    REGULAR, COMPOSITION, UNREGISTERED = "regular", "composition", "unregistered"
    CONSUMER, OVERSEAS, SEZ = "consumer", "overseas", "sez"
    GST_TYPES = [
        (REGULAR, "Registered (regular)"),
        (COMPOSITION, "Registered (composition)"),
        (UNREGISTERED, "Unregistered business"),
        (CONSUMER, "Consumer"),
        (SEZ, "SEZ unit or developer"),
        (OVERSEAS, "Overseas"),
    ]
    NEEDS_GSTIN = (REGULAR, COMPOSITION, SEZ)

    name = models.CharField(max_length=150, default="")
    gst_type = models.CharField(max_length=15, choices=GST_TYPES, default=UNREGISTERED)
    gstin = models.CharField(max_length=15, blank=True, validators=[india.validate_gstin])
    pan = models.CharField(max_length=10, blank=True, validators=[india.validate_pan])
    # The state of the party's main (billing) address; it decides the place of
    # supply. Blank for overseas parties.
    state_code = models.CharField(max_length=2, blank=True, validators=[india.validate_state_code])
    country = models.CharField(max_length=60, default="India")
    credit_term = models.ForeignKey(
        CreditTerm, null=True, blank=True, on_delete=models.PROTECT, related_name="parties"
    )
    # Given automatically the first time a company deals with the party as a
    # customer (Sundry Debtors) or a supplier (Sundry Creditors); one party
    # can be both. Unique across the group. Decision 0021.
    customer_number = models.CharField(max_length=20, blank=True)
    vendor_number = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name_plural = "parties"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="party_name_unique"),
            models.UniqueConstraint(
                "gstin", condition=~models.Q(gstin=""), name="party_gstin_unique"
            ),
            models.UniqueConstraint(
                "customer_number",
                condition=~models.Q(customer_number=""),
                name="party_customer_number_unique",
            ),
            models.UniqueConstraint(
                "vendor_number",
                condition=~models.Q(vendor_number=""),
                name="party_vendor_number_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        self.gstin = self.gstin.strip().upper()
        self.pan = self.pan.strip().upper()
        self.country = self.country.strip() or "India"
        if self.gst_type == self.OVERSEAS:
            if self.country.lower() == "india":
                raise ValidationError({"country": "Give the country of an overseas party."})
            if self.gstin:
                raise ValidationError({"gstin": "An overseas party has no GSTIN."})
            self.state_code = ""
            return
        if self.country.lower() != "india":
            raise ValidationError(
                {"country": "Choose Overseas as the GST type for a party abroad."}
            )
        self.country = "India"
        if self.gst_type in self.NEEDS_GSTIN:
            if not self.gstin:
                raise ValidationError({"gstin": "A registered party needs its GSTIN."})
        elif self.gstin:
            raise ValidationError(
                {"gst_type": "This party has a GSTIN; choose a registered GST type."}
            )
        if self.gstin:
            if not self.pan:
                self.pan = self.gstin[2:12]
            elif self.gstin[2:12] != self.pan:
                raise ValidationError({"pan": "The PAN must match the one inside the GSTIN."})
            if not self.state_code:
                self.state_code = self.gstin[:2]
            elif self.gstin[:2] != self.state_code:
                raise ValidationError({"gstin": "This GSTIN belongs to a different state."})
        if not self.state_code:
            raise ValidationError({"state_code": "Choose the party's state."})


class PartyAddress(models.Model):
    """One of a party's addresses: its office, a godown, a shop. Documents
    pick the default billing and shipping addresses first."""

    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=60)  # e.g. "Head office", "Bhiwandi godown"
    address = models.TextField()
    pincode = models.CharField(max_length=10, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state_code = models.CharField(max_length=2, blank=True, validators=[india.validate_state_code])
    country = models.CharField(max_length=60, default="India")
    # A party registered in several states has a GSTIN per state.
    gstin = models.CharField(max_length=15, blank=True, validators=[india.validate_gstin])
    is_billing = models.BooleanField(default=False)
    is_shipping = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.label


# What a contact is for; automated emails go to the contacts of the right type.
# "Main" is the `is_primary` tick (one per party); these are the other types.
# To add a type, add a line here and in `CONTACT_KINDS` in frontend Parties.tsx.
CONTACT_KINDS = [
    ("accounts", "Accounting"),
    ("shipping", "Shipping"),
    ("purchase", "Purchase"),
    ("sales", "Sales"),
]


def validate_contact_kinds(value):
    codes = [code for code, _ in CONTACT_KINDS]
    if (
        not isinstance(value, list)
        or any(k not in codes for k in value)
        or len(set(value)) != len(value)
    ):
        raise ValidationError(
            "Choose from: " + ", ".join(label for _, label in CONTACT_KINDS) + "."
        )


class PartyContact(models.Model):
    """A person to deal with at a customer or supplier: the owner, the
    purchase manager, accounts. One can be ticked as the main contact, and
    each can be of several types (see CONTACT_KINDS)."""

    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=60, blank=True)  # e.g. "Purchase manager"
    phone = models.CharField(max_length=20, blank=True, validators=[india.validate_phone])
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)
    kinds = models.JSONField(default=list, blank=True, validators=[validate_contact_kinds])

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class NumberSeries(models.Model):
    """A running number handed out as PREFIX + zero-padded count, e.g.
    CUST-00012. One row per kind of record (`customer`, `vendor`), shared by
    every company in the group. Use core.numbering.next_number()."""

    key = models.CharField(max_length=30, unique=True)
    prefix = models.CharField(max_length=10, blank=True)
    width = models.PositiveSmallIntegerField(default=5)
    last = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "number series"

    def __str__(self) -> str:
        return self.key
