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
    # Contacts ticked to get the order on WhatsApp (kept now; sending comes later).
    whatsapp_to = models.JSONField(default=list, blank=True)
    mail_agent_user = models.BooleanField(default=False)
    supplier_ref = models.CharField(max_length=80, blank=True)
    # The order's currency: the supplier ledger's (INR unless it is overseas with a
    # foreign currency ledger). No exchange rate is kept on an order.
    currency = models.CharField(max_length=3, default="INR")
    # Shipment and payment terms of an import (buying.imports); empty otherwise.
    import_details = models.JSONField(default=dict, blank=True)
    # The set the terms were taken from (the supplier's, else the company's
    # default); the text below is the order's own copy and may be changed.
    terms_set = models.ForeignKey(
        "core.TermsSet", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
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
    # Who submitted (approved) it: printed under the signature.
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Where the supplier's reply stands (buying/supplier_link.py): blank until
    # the order is mailed with its link. Kept here for the orders list.
    SUPPLIER_STATUSES = [
        ("", "Not sent"),
        ("sent", "Sent"),
        ("opened", "Opened"),
        ("accepted", "Accepted"),
        ("issue", "Issue"),
    ]
    supplier_status = models.CharField(
        max_length=10, choices=SUPPLIER_STATUSES, blank=True, default=""
    )

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
    # "Close Line" (Sidharth, 2026-11-15): the rest will not come. A closed line
    # has nothing pending; "Reopen Line" clears these.
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    close_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class PurchaseOrderCharge(models.Model):
    """An extra the supplier bills on the order (Sidharth, 2026-11-14): a service
    item marked "Use as Purchase Charge". Its amount is fixed, a share of the
    items' taxable value, or a rate on their total quantity. "Add to Stock Cost"
    says how it is spread over the items when the goods are received (by
    quantity or by value), or "No" for the expense account."""

    FIXED, PERCENT, PER_UNIT = "fixed", "percent", "per_unit"
    BASES = [(FIXED, "Fixed"), (PERCENT, "% of items"), (PER_UNIT, "Per unit")]

    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="charges")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    basis = models.CharField(max_length=10, choices=BASES, default=FIXED)
    # The amount for Fixed, the percent for "% of items", the rate per unit for "Per unit".
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    amount = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    add_to_stock = models.CharField(max_length=5, choices=Item.STOCK_COST, default=Item.BY_VALUE)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item} {self.amount}"


class GoodsReceipt(models.Model):
    """A goods receipt (GRN): what arrived at one of our warehouses against one
    or more purchase orders of a supplier, and which bins and batches it was
    put into. On Submit it posts the stock (one move per bin and batch, each a
    FIFO lot) and Dr Stock / Cr Goods Received but Bills not Received at order
    rates plus the order's charges added to stock (decision 0017, rule 11)."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]
    OK, DAMAGED, MATCHES, WRONG = "ok", "damaged", "matches", "wrong"
    CARTONS = [(OK, "OK"), (DAMAGED, "Damaged")]
    PRINTS = [(MATCHES, "Matches"), (WRONG, "Wrong / Missing")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="goods_receipts")
    supplier = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="goods_receipts")
    # The receiving warehouse: our branch the goods came into.
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="goods_receipts")
    orders = models.ManyToManyField(PurchaseOrder, related_name="receipts", blank=True)
    number = models.CharField(max_length=30, blank=True)
    receipt_date = models.DateField()
    challan_no = models.CharField(max_length=40, blank=True)
    challan_date = models.DateField(null=True, blank=True)
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    lr_no = models.CharField(max_length=40, blank=True)
    vehicle_no = models.CharField(max_length=20, blank=True)
    eway_bill_no = models.CharField(max_length=20, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Orders in a foreign currency: rupees per unit of it, for the stock value.
    currency = models.CharField(max_length=3, default="INR")
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=9, null=True, blank=True)
    # Quality check (optional add-on; for items marked "QC required").
    qc_cartons = models.CharField(max_length=8, choices=CARTONS, blank=True)
    qc_batch_print = models.CharField(max_length=8, choices=PRINTS, blank=True)
    qc_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    stock_value = models.DecimalField(**MONEY, default=Decimal("0"))
    cancel_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-receipt_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="grn_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft goods receipt {self.pk}"


class GoodsReceiptLine(models.Model):
    """One item received, against one order line, in that line's unit.
    Accepted = received - rejected; only the accepted quantity goes into stock."""

    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    received_qty = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    rejected_qty = models.DecimalField(
        **QTY, default=Decimal("0"), validators=[MinValueValidator(0)]
    )
    accepted_qty = models.DecimalField(**QTY, default=Decimal("0"))
    # Set on Submit: the rupee value posted (order rate + charges to stock).
    value = models.DecimalField(**MONEY, default=Decimal("0"))
    charges_value = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item} × {self.accepted_qty}"


class GoodsReceiptPutaway(models.Model):
    """Where part of a line's accepted quantity went: a bin or an area of the
    receiving warehouse, and its batch. A new batch is typed here with its
    dates and added to the Batches master on Submit (Sidharth, 2026-11-15)."""

    line = models.ForeignKey(GoodsReceiptLine, on_delete=models.CASCADE, related_name="putaways")
    position = models.PositiveSmallIntegerField()
    location = models.ForeignKey(
        "core.WarehouseLocation", on_delete=models.PROTECT, related_name="+"
    )
    batch = models.ForeignKey(
        "core.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # A new batch, until Submit makes it.
    batch_number = models.CharField(max_length=60, blank=True)
    mfg_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    # How it came packed: 5 bags of 20 (qty is then 100). Blank for loose goods.
    packages = models.PositiveIntegerField(null=True, blank=True)
    package_type = models.CharField(max_length=10, blank=True)
    package_qty = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.location_id}: {self.qty}"


class SupplierLink(models.Model):
    """The private link mailed with a purchase order (Sidharth, 2026-11-15):
    the supplier opens it without signing in to accept the order or report an
    issue. Only a hash of the code is kept, so the code itself lives only in
    the mail. Each mailing makes a new link; each stays valid until it expires
    or the order is cancelled."""

    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="links")
    token_hash = models.CharField(max_length=64, unique=True)
    mailed_to = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    opened_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"Link for {self.order}"


class SupplierResponse(models.Model):
    """What the supplier said through a link: accepted, an issue, or a later
    comment. Never changed after it is made."""

    ACCEPTED, ISSUE, COMMENT = "accepted", "issue", "comment"
    KINDS = [(ACCEPTED, "Accepted"), (ISSUE, "Issue"), (COMMENT, "Comment")]

    link = models.ForeignKey(SupplierLink, on_delete=models.CASCADE, related_name="responses")
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="responses")
    kind = models.CharField(max_length=10, choices=KINDS)
    name = models.CharField(max_length=100)
    dispatch_date = models.DateField(null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} by {self.name}"
