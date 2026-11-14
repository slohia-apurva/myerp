"""Purchase documents (spec 00, module 3b). This first slice is the purchase
order: what we asked a supplier for. It posts nothing to either ledger; the
goods receipt and the purchase invoice, built next, do.

A purchase order is saved as a draft (changeable), then submitted: it gets
its number and is fixed. A submitted order is never edited; it is cancelled
and a new one made (Duplicate), as for every entry (rule 1).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import Branch, Company, CreditTerm, Item, Ledger, Unit
from shipping.models import CourierAccount

MONEY = {"max_digits": 18, "decimal_places": 2}
QTY = {"max_digits": 18, "decimal_places": 6}


class PurchaseOrder(models.Model):
    DRAFT, ORDERED, PART_RECEIVED, RECEIVED, CLOSED, CANCELLED = (
        "draft",
        "ordered",
        "part_received",
        "received",
        "closed",
        "cancelled",
    )
    STATUSES = [
        (DRAFT, "Draft"),
        (ORDERED, "Ordered"),
        (PART_RECEIVED, "Part received"),
        (RECEIVED, "Received"),
        (CLOSED, "Closed"),
        (CANCELLED, "Cancelled"),
    ]
    OPEN = (ORDERED, PART_RECEIVED)

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="purchase_orders")
    # The supplier's ledger in this company (under Sundry Creditors).
    supplier = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="purchase_orders")
    # Where the goods are to come: a branch of the company. Its state decides
    # CGST + SGST (same state as the supplier) or IGST.
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="purchase_orders")
    # Given on Submit, from the company's (or branch's) Purchase order series.
    number = models.CharField(max_length=30, blank=True)
    order_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    credit_term = models.ForeignKey(
        CreditTerm, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # The company's billing address on the order (a branch; the default billing one
    # unless changed). The goods go to `branch`, which is the Ship To.
    bill_to = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # The supplier's address picked for the order, copied as it was (label, address,
    # city, pincode, state_code, country, gstin): its addresses are re-saved whole.
    supplier_address = models.JSONField(default=dict, blank=True)
    # Who brings the goods: one of our transporters, or none for "By Supplier"
    # (the supplier sends them). Comes from the supplier's preferred transporter.
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # A buying agent: a firm from the company's suppliers (a broker, say), or one of
    # our own employees (a user). At most one of the two.
    agent = models.ForeignKey(
        Ledger, null=True, blank=True, on_delete=models.PROTECT, related_name="agent_orders"
    )
    agent_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="agent_orders",
    )
    # Who the order is mailed to: ids of the supplier's and the agent firm's contacts,
    # and whether the employee agent gets it too.
    mail_to = models.JSONField(default=list, blank=True)
    mail_agent_user = models.BooleanField(default=False)
    supplier_ref = models.CharField(max_length=80, blank=True)
    terms = models.TextField(blank=True)  # printed for the supplier
    notes = models.TextField(blank=True)  # internal, not printed
    status = models.CharField(max_length=14, choices=STATUSES, default=DRAFT)
    # GST is charged only by a regular registered supplier; the split follows
    # the supplier's state against the branch's.
    interstate = models.BooleanField(default=False)
    taxable_total = models.DecimalField(**MONEY, default=Decimal("0"))
    cgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    igst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    round_off = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    cancel_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-order_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="po_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft purchase order {self.pk}"


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    # Printed under the item name: the item's purchase description unless changed here.
    description = models.TextField(blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    discount_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    taxable = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY)
    # Filled by goods receipts, when they are built.
    received_qty = models.DecimalField(**QTY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"
