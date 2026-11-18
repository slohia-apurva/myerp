"""Insurance policies (Sidharth, 2026-11-18, previews 93a-93d).

A company's policies: marine policies for goods moving inland or exported,
and fire and stock policies. A marine policy is an open policy: each transit
is declared to the insurer, who issues a certificate for it, and the sum
insured is used up by what is declared and topped up by endorsements
(`InsurancePolicyTopUp`). A purchase order names the policy its goods travel
under; its goods receipts and purchase invoices show it from the order.
Sales orders and invoices will do the same when Sales is built.
Never deleted, only disabled."""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from core.models import Company, Ledger

MONEY = {"max_digits": 18, "decimal_places": 2}


class InsurancePolicy(models.Model):
    MARINE_INLAND, MARINE_EXPORT, FIRE, STOCK = "marine_inland", "marine_export", "fire", "stock"
    KINDS = [
        (MARINE_INLAND, "Marine (inland transit)"),
        (MARINE_EXPORT, "Marine (export)"),
        (FIRE, "Fire"),
        (STOCK, "Stock"),
    ]
    # Policies that cover goods in transit, offered on orders.
    TRANSIT = (MARINE_INLAND, MARINE_EXPORT)

    PURCHASE, SALES, BOTH = "purchase", "sales", "both"
    COVERS = [(PURCHASE, "Purchases"), (SALES, "Sales"), (BOTH, "Purchases and Sales")]
    DEFAULTS = [("", "None"), *COVERS]

    INVOICE, INVOICE_10 = "invoice", "invoice_10"
    BASES = [(INVOICE, "Invoice value"), (INVOICE_10, "Invoice value + 10%")]

    WARN, STOP = "warn", "stop"
    WHEN_OUT = [(WARN, "Warn, keep insuring"), (STOP, "Stop until topped up")]

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="insurance_policies"
    )
    number = models.CharField(max_length=60)
    # The insurance company: one of the company's suppliers.
    insurer = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="insurance_policies")
    kind = models.CharField(max_length=15, choices=KINDS)
    covers = models.CharField(max_length=10, choices=COVERS, default=BOTH)
    valid_from = models.DateField()
    valid_to = models.DateField()
    # The cover when the policy was issued, and its premium; top-ups add to it.
    sum_insured = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    premium = models.DecimalField(**MONEY, default=Decimal("0"), validators=[MinValueValidator(0)])
    # The most one transit may carry; an order above it is flagged.
    transit_limit = models.DecimalField(
        **MONEY, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    insured_basis = models.CharField(max_length=12, choices=BASES, default=INVOICE_10)
    # New orders of this side start with this policy.
    default_for = models.CharField(max_length=10, choices=DEFAULTS, blank=True, default="")
    # Owners and accountants are told when the balance falls below this.
    alert_below = models.DecimalField(
        **MONEY, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    when_out = models.CharField(max_length=6, choices=WHEN_OUT, default=WARN)
    # Where the daily declaration goes: the insurer or the broker (comma-separated).
    declare_to = models.CharField(max_length=300, blank=True)
    copy_to = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-valid_to", "number"]
        constraints = [
            models.UniqueConstraint(
                "company", Lower("number"), name="insurance_policy_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def is_transit(self) -> bool:
        return self.kind in self.TRANSIT

    def covers_side(self, side: str) -> bool:
        return self.covers in (side, self.BOTH)


class InsurancePolicyTopUp(models.Model):
    """Cover added to a policy by an endorsement, when the sum insured runs low."""

    policy = models.ForeignKey(InsurancePolicy, on_delete=models.CASCADE, related_name="top_ups")
    date = models.DateField()
    endorsement_no = models.CharField(max_length=60, blank=True)
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    premium = models.DecimalField(**MONEY, default=Decimal("0"), validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["date", "id"]

    def __str__(self) -> str:
        return f"{self.endorsement_no or 'Top-up'} of {self.date:%d-%m-%Y}"
