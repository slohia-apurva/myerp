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
    # Transit insurance (Sidharth, 2026-11-18, preview 93b): who insures the goods
    # on the way, and, when we do, under which of our marine policies and for how
    # much (the order total, plus 10% where the policy says so). The goods
    # receipts and purchase invoices of the order show it.
    US, SUPPLIER, NOT_INSURED = "us", "supplier", "none"
    INSURED_BY = [(US, "Us"), (SUPPLIER, "Supplier"), (NOT_INSURED, "Not insured")]
    insured_by = models.CharField(max_length=10, choices=INSURED_BY, default=NOT_INSURED)
    insurance_policy = models.ForeignKey(
        "insurance.InsurancePolicy",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    insured_value = models.DecimalField(**MONEY, default=Decimal("0"))
    # A buying agent: a firm from the company's suppliers (a broker, say), or one of
    # the Purchasers (Masters > Salesmen and Purchasers), which starts as the
    # supplier's own Purchaser in this company. At most one of the two.
    agent = models.ForeignKey(
        Ledger, null=True, blank=True, on_delete=models.PROTECT, related_name="agent_orders"
    )
    purchaser = models.ForeignKey(
        "core.SalesPerson",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    # Who the order is mailed to: ids of the supplier's and the agent firm's contacts,
    # and whether the purchaser gets it too.
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
    # Masters > People ticked "Stores" (Sidharth, 2026-11-17, preview 88).
    received_by = models.ForeignKey(
        "core.SalesPerson", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Orders in a foreign currency: rupees per unit of it, for the stock value.
    currency = models.CharField(max_length=3, default="INR")
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=9, null=True, blank=True)
    # Quality check (optional add-on; for items marked "QC required").
    qc_cartons = models.CharField(max_length=8, choices=CARTONS, blank=True)
    qc_batch_print = models.CharField(max_length=8, choices=PRINTS, blank=True)
    # Masters > People ticked "Stores" (Sidharth, 2026-11-17, preview 88).
    qc_by = models.ForeignKey(
        "core.SalesPerson", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
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
    # What purchase invoices have billed of it so far, and the receipt value
    # they took out of "Goods Received but Bills not Received".
    billed_qty = models.DecimalField(**QTY, default=Decimal("0"))
    billed_value = models.DecimalField(**MONEY, default=Decimal("0"))
    # Sent back to the supplier by purchase returns, and settled by debit notes,
    # with the receipt value each moved in or out of that ledger.
    returned_qty = models.DecimalField(**QTY, default=Decimal("0"))
    returned_value = models.DecimalField(**MONEY, default=Decimal("0"))
    debited_qty = models.DecimalField(**QTY, default=Decimal("0"))
    debited_value = models.DecimalField(**MONEY, default=Decimal("0"))

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


class PurchaseInvoice(models.Model):
    """The supplier's bill, entered against goods receipts (Sidharth,
    2026-11-15, preview 67). Submit posts: the receipts' value out of "Goods
    Received but Bills not Received", input GST, a rate difference into the
    stock still on hand (else "Purchase Price Difference"), and the supplier
    credited with its due dates. Saved as a draft first; never edited once
    submitted (cancel and make a new one)."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]

    REGULAR, SUPPLEMENTARY, DIRECT = "regular", "supplementary", "direct"
    KINDS = [
        (REGULAR, "Purchase invoice"),
        (SUPPLEMENTARY, "Supplementary bill"),
        (DIRECT, "Without goods receipt"),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="purchase_invoices")
    # A supplementary bill (Sidharth, 2026-11-16, preview 79): the supplier
    # charges more for goods already billed on `original`; it has rate lines only.
    kind = models.CharField(max_length=15, choices=KINDS, default=REGULAR)
    original = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="supplementaries"
    )
    supplier = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="purchase_invoices")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="purchase_invoices")
    receipts = models.ManyToManyField(GoodsReceipt, related_name="invoices", blank=True)
    number = models.CharField(max_length=30, blank=True)
    bill_no = models.CharField(max_length=40, blank=True)  # the supplier's invoice number
    bill_date = models.DateField(null=True, blank=True)
    posting_date = models.DateField(null=True, blank=True)  # starts as the bill date
    credit_term = models.ForeignKey(
        CreditTerm, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # The grand total printed on the supplier's bill; Submit needs ours to match.
    bill_total = models.DecimalField(**MONEY, null=True, blank=True)
    interstate = models.BooleanField(default=False)
    taxable_total = models.DecimalField(**MONEY, default=Decimal("0"))
    cgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    igst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    round_off = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    # TDS deducted on the bill (buying/tds.py); the supplier is owed total less this.
    tds_total = models.DecimalField(**MONEY, default=Decimal("0"))
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
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
        ordering = ["-posting_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="pinv_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft purchase invoice {self.pk}"


class PurchaseInvoiceLine(models.Model):
    """One billed line: a quantity of a goods receipt line at the bill's rate."""

    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    receipt_line = models.ForeignKey(
        GoodsReceiptLine, on_delete=models.PROTECT, related_name="invoice_lines"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    taxable = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY)
    # Set on Submit: the receipt value cleared, and the rate difference split
    # between the stock still on hand and "Purchase Price Difference".
    receipt_value = models.DecimalField(**MONEY, default=Decimal("0"))
    stock_difference = models.DecimalField(**MONEY, default=Decimal("0"))
    price_difference = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item_id}: {self.qty} @ {self.rate}"


class PurchaseInvoiceRateLine(models.Model):
    """A supplementary bill's line: more per unit on a quantity of a line of
    the original bill. No quantity moves; the extra goes onto the stock still
    on hand, the rest to "Purchase Price Difference"."""

    invoice = models.ForeignKey(
        PurchaseInvoice, on_delete=models.CASCADE, related_name="rate_lines"
    )
    position = models.PositiveSmallIntegerField()
    original_line = models.ForeignKey(
        PurchaseInvoiceLine, on_delete=models.PROTECT, related_name="supplementary_lines"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    rate = models.DecimalField(**QTY)  # the original bill's rate
    new_rate = models.DecimalField(**QTY)  # the revised, higher rate
    taxable = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY)
    stock_difference = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Submit
    price_difference = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item_id}: {self.qty} @ +{self.new_rate - self.rate}"


class PurchaseInvoiceExpenseLine(models.Model):
    """A line of a bill without goods receipt (Sidharth, 2026-11-16, preview
    82): a service or goods not kept in stock (an item, booked to the item's
    Expense Account), or an expense ledger booked to itself. No stock moves."""

    invoice = models.ForeignKey(
        PurchaseInvoice, on_delete=models.CASCADE, related_name="expense_lines"
    )
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(
        Item, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    ledger = models.ForeignKey(
        Ledger, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    description = models.CharField(max_length=200, blank=True)
    hsn = models.CharField(max_length=8, blank=True)  # HSN or SAC
    unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    taxable = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY)
    # The ledger debited: the picked ledger, or the item's Expense Account,
    # worked out on save and fixed on Submit.
    booked_to = models.ForeignKey(
        Ledger, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(item__isnull=False, ledger__isnull=True)
                | models.Q(item__isnull=True, ledger__isnull=False),
                name="expense_line_item_or_ledger",
            )
        ]

    def __str__(self) -> str:
        return f"{self.item_id or self.ledger_id}: {self.taxable}"


class PurchaseInvoiceCharge(models.Model):
    """A charge on the bill (freight, loading): a service item with its GST.
    "In stock cost" charges were already added to the goods by the receipt,
    so they only settle against it; the others go to the item's expense."""

    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name="charges")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(0)])
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    in_stock_cost = models.BooleanField(default=True)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item_id}: {self.amount}"


class PurchaseInvoiceDue(models.Model):
    """When the bill is to be paid: one row per part of the credit term."""

    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name="dues")
    position = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.due_date}: {self.amount}"


class PurchaseInvoiceTds(models.Model):
    """TDS on one line of a purchase bill (buying/tds.py), worked out again on
    every save of a draft and on Submit. `section` is the line's own (from its
    item or ledger, else the supplier's default) unless `by_hand`, when the
    person chose it, or chose none, on the bill."""

    LINE, CHARGE, RATE, EXPENSE = "line", "charge", "rate", "expense"
    KINDS = [(LINE, "Goods"), (CHARGE, "Charge"), (RATE, "Rate change"), (EXPENSE, "Line")]

    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name="tds_rows")
    position = models.PositiveSmallIntegerField()
    line_kind = models.CharField(max_length=8, choices=KINDS)
    line_position = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=200, blank=True)
    section = models.CharField(max_length=12, blank=True)
    by_hand = models.BooleanField(default=False)
    taxable = models.DecimalField(**MONEY, default=Decimal("0"))  # the line, before GST
    base = models.DecimalField(**MONEY, default=Decimal("0"))  # what TDS is worked out on
    rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))
    amount = models.DecimalField(**MONEY, default=Decimal("0"))
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.section or '-'}: {self.amount}"


class PurchaseReturn(models.Model):
    """Goods sent back to the supplier from one goods receipt (Sidharth,
    2026-11-15, preview 74): damaged, short, rejected. Submit takes them out of
    stock at the receipt's cost and back out of "Goods Received but Bills not
    Received"; the supplier's account is touched only by the Debit Note."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]
    REASONS = [
        ("damaged", "Damaged in transit"),
        ("short", "Short supplied"),
        ("quality", "Quality rejected"),
        ("wrong", "Wrong item"),
        ("other", "Other"),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="purchase_returns")
    supplier = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="purchase_returns")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="purchase_returns")
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="returns")
    number = models.CharField(max_length=30, blank=True)
    return_date = models.DateField()
    reason = models.CharField(max_length=10, choices=REASONS, default="damaged")
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    lr_no = models.CharField(max_length=40, blank=True)
    vehicle_no = models.CharField(max_length=20, blank=True)
    eway_bill_no = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    value = models.DecimalField(**MONEY, default=Decimal("0"))  # receipt value sent back
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
        ordering = ["-return_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="pret_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft return {self.pk}"


class PurchaseReturnLine(models.Model):
    """A quantity of one receipt line going back, from one bin and batch, in
    the receipt line's unit."""

    ret = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    receipt_line = models.ForeignKey(
        GoodsReceiptLine, on_delete=models.PROTECT, related_name="return_lines"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(
        "core.WarehouseLocation", on_delete=models.PROTECT, related_name="+"
    )
    batch = models.ForeignKey(
        "core.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    # Set on Submit: the receipt value out of "Goods Received but Bills not
    # Received", and the stock value taken out (they differ once a bill has
    # revalued the lot; the difference is "Purchase Price Difference").
    value = models.DecimalField(**MONEY, default=Decimal("0"))
    stock_value = models.DecimalField(**MONEY, default=Decimal("0"))
    debited_qty = models.DecimalField(**QTY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item_id} × {self.qty}"


class DebitNote(models.Model):
    """Our debit note to the supplier against one purchase invoice, for goods
    sent back on purchase returns (Sidharth, 2026-11-15, preview 75): at the
    bill's rate and GST. Submit debits the supplier against that bill, clears
    the returned goods from "Goods Received but Bills not Received" and
    reverses the input GST."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]
    REASONS = [("returned", "Goods returned"), ("rate", "Rate charged higher")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="debit_notes")
    supplier = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="debit_notes")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="debit_notes")
    invoice = models.ForeignKey(
        PurchaseInvoice, on_delete=models.PROTECT, related_name="debit_notes"
    )
    number = models.CharField(max_length=30, blank=True)
    note_date = models.DateField()
    reason = models.CharField(max_length=10, choices=REASONS, default="returned")
    supplier_note_no = models.CharField(max_length=40, blank=True)
    supplier_note_date = models.DateField(null=True, blank=True)
    interstate = models.BooleanField(default=False)
    taxable_total = models.DecimalField(**MONEY, default=Decimal("0"))
    cgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    igst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    round_off = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    # TDS taken back from the bill in proportion (buying/tds.py); the supplier's
    # balance goes down by total less this.
    tds_total = models.DecimalField(**MONEY, default=Decimal("0"))
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
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
        ordering = ["-note_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="dn_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft debit note {self.pk}"


class DebitNoteLine(models.Model):
    """A returned quantity debited at the bill line's rate and GST."""

    note = models.ForeignKey(DebitNote, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    invoice_line = models.ForeignKey(
        PurchaseInvoiceLine, on_delete=models.PROTECT, related_name="debit_lines"
    )
    # Goods returned: the return line settled. Rate charged higher (Sidharth,
    # 2026-11-16, preview 78): no return; `rate` is the bill's, `new_rate` the
    # agreed one, and the taxable is the difference on `qty`.
    return_line = models.ForeignKey(
        PurchaseReturnLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="debit_lines",
    )
    new_rate = models.DecimalField(**QTY, null=True, blank=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    rate = models.DecimalField(**QTY)
    taxable = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY)
    receipt_value = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Submit
    stock_difference = models.DecimalField(**MONEY, default=Decimal("0"))  # rate notes
    price_difference = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item_id}: {self.qty} @ {self.rate}"


class TdsReturnFiled(models.Model):
    """A quarter whose TDS return is filed (Sidharth, 2026-11-19): its bills'
    TDS can no longer be put right by a TDS Adjustment, and its bills with TDS
    cannot be cancelled. Quarters run April-June, July-September,
    October-December, January-March; `quarter_start` is the first day."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="tds_returns")
    quarter_start = models.DateField()
    filed_on = models.DateField()
    ack_no = models.CharField(max_length=30, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["quarter_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "quarter_start"], name="tds_return_once_a_quarter"
            )
        ]

    def __str__(self) -> str:
        return f"TDS return from {self.quarter_start}"


class TdsAdjustment(models.Model):
    """TDS put right after the bills were submitted (Sidharth, 2026-11-19,
    previews 95a-c), made from the TDS Check: a submitted bill is never
    changed, so TDS missed is deducted now (Dr supplier, Cr TDS Payable) and TDS
    deducted in excess is given back (the other way). One supplier, one section;
    its lines name the bills (buying/tds_check.py)."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="tds_adjustments")
    supplier = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="tds_adjustments")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="tds_adjustments")
    number = models.CharField(max_length=30, blank=True)
    adj_date = models.DateField()
    section = models.CharField(max_length=12)
    remarks = models.TextField(blank=True)
    # Signed: + TDS deducted now, - TDS given back.
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    interest = models.DecimalField(**MONEY, default=Decimal("0"))  # for information only
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
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
        ordering = ["-adj_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="tdsa_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft TDS adjustment {self.pk}"


class TdsAdjustmentLine(models.Model):
    """One bill put right: the TDS due on it (worked out again by the TDS
    Check), what the bill and earlier adjustments deducted, and the difference
    taken now (signed). Interest is on TDS deducted late only."""

    adjustment = models.ForeignKey(TdsAdjustment, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    invoice = models.ForeignKey(
        PurchaseInvoice, on_delete=models.PROTECT, related_name="tds_adjustment_lines"
    )
    base = models.DecimalField(**MONEY, default=Decimal("0"))
    rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))
    due = models.DecimalField(**MONEY, default=Decimal("0"))
    deducted = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY, default=Decimal("0"))
    months = models.PositiveSmallIntegerField(default=0)
    interest = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.invoice_id}: {self.amount}"
