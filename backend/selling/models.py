"""Sales documents (spec 00, module 3c). This first slice is the sales order:
what a customer asked us for. It posts nothing to either ledger; the delivery
note and the sales invoice, built later, do.

A sales order is saved as a draft (changeable), then submitted: it gets its
number and is fixed. A submitted order is never edited; it is cancelled and a
new one made (Duplicate), as for every entry (rule 1).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import (
    Batch,
    Branch,
    Company,
    CreditTerm,
    Item,
    Ledger,
    Package,
    SalesPerson,
    TermsSet,
    Unit,
    WarehouseLocation,
)
from shipping.models import CourierAccount

MONEY = {"max_digits": 18, "decimal_places": 2}
QTY = {"max_digits": 18, "decimal_places": 6}


class SalesOrder(models.Model):
    DRAFT, ORDERED, PART_DELIVERED, DELIVERED, CLOSED, CANCELLED = (
        "draft",
        "ordered",
        "part_delivered",
        "delivered",
        "closed",
        "cancelled",
    )
    STATUSES = [
        (DRAFT, "Draft"),
        (ORDERED, "Ordered"),
        (PART_DELIVERED, "Part delivered"),
        (DELIVERED, "Delivered"),
        (CLOSED, "Closed"),
        (CANCELLED, "Cancelled"),
    ]
    OPEN = (ORDERED, PART_DELIVERED)

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="sales_orders")
    # The customer's ledger in this company (under Sundry Debtors).
    customer = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="sales_orders")
    # Where the goods go out from (Sidharth, 2026-11-19): a branch of the company,
    # or one area of it ("area"): stock is then looked for only in that area and
    # the racks and bins under it, else anywhere in the branch.
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="sales_orders")
    area = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Given on Submit, from the company's (or branch's) Sales order series.
    number = models.CharField(max_length=30, blank=True)
    order_date = models.DateField()
    delivery_date = models.DateField(null=True, blank=True)
    credit_term = models.ForeignKey(
        CreditTerm, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Our branch whose GST registration bills the goods ("Bill From").
    bill_from = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # The customer's addresses as they were on the order: billing (it decides the
    # place of supply) and shipping.
    bill_address = models.JSONField(default=dict, blank=True)
    ship_address = models.JSONField(default=dict, blank=True)
    # None: "By Customer" (the customer collects).
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    salesman = models.ForeignKey(
        SalesPerson, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # The customer's contacts (ids) who get the order confirmation by mail.
    mail_to = models.JSONField(default=list, blank=True)
    customer_po_no = models.CharField(max_length=60, blank=True)
    customer_po_date = models.DateField(null=True, blank=True)
    terms_set = models.ForeignKey(
        TermsSet, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    terms = models.TextField(blank=True)  # printed for the customer
    notes = models.TextField(blank=True)  # internal, not printed
    status = models.CharField(max_length=14, choices=STATUSES, default=DRAFT)
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
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # What Submit found short at the branch and what it did, one entry per item:
    # {item, item_name, expected, short, unit_name, action: ok|po|make|transfer|
    # no_supplier|failed, order, message} (buying/planning.py).
    shortages = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-order_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="so_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft sales order {self.pk}"


class SalesOrderLine(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    # Printed under the item name: the item's sales description unless changed here.
    description = models.TextField(blank=True)
    # One of the item's own units (Sidharth, 2026-11-19): starts at its Sales Unit.
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    # Where the rate came from when it was filled in: "own" (the customer's own
    # price), a price list's name, "mrp", or "" (typed).
    rate_source = models.CharField(max_length=80, blank=True)
    taxable = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY)
    # Filled by delivery notes, when they are built.
    delivered_qty = models.DecimalField(**QTY, default=Decimal("0"))
    # "Close Line": the rest will not be sent. A closed line has nothing pending.
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    close_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class SalesOrderCharge(models.Model):
    """An extra we bill on the order, such as freight or packing: a service item
    marked "Use as Sales Charge". Its amount is fixed, a share of the items'
    taxable value, or a rate on their total quantity."""

    FIXED, PERCENT, PER_UNIT = "fixed", "percent", "per_unit"
    BASES = [(FIXED, "Fixed"), (PERCENT, "% of items"), (PER_UNIT, "Per unit")]

    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="charges")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    basis = models.CharField(max_length=10, choices=BASES, default=FIXED)
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    amount = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item} {self.amount}"


class PickList(models.Model):
    """Where the stores take an order's goods from: bin and batch per item
    (Sidharth, 2026-11-19, preview 6). Made by itself when a sales order is
    submitted; an open list can be changed, and once submitted ("Picked") it is
    final. Stock on an open or picked list is kept aside, so the next order
    does not pick the same bags. It posts nothing: the delivery note moves the
    stock, and the list is then "Delivered"."""

    OPEN, PICKED, DELIVERED, CANCELLED = "open", "picked", "delivered", "cancelled"
    STATUSES = [
        (OPEN, "Open"),
        (PICKED, "Picked"),
        (DELIVERED, "Delivered"),
        (CANCELLED, "Cancelled"),
    ]
    HOLDING = (OPEN, PICKED)

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="pick_lists")
    # The order's Despatch From, as it was when the list was made.
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    area = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    number = models.CharField(max_length=30)
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN)
    notes = models.TextField(blank=True)
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
        ordering = ["-id"]
        constraints = [models.UniqueConstraint("company", "number", name="pick_list_number_unique")]

    def __str__(self) -> str:
        return self.number


class PickListLine(models.Model):
    """One bin and batch to take an order line's goods from. Quantities are in
    the item's stock unit. An order line with nothing found has no rows; what is
    short is the line's quantity less what its rows pick."""

    pick_list = models.ForeignKey(PickList, on_delete=models.CASCADE, related_name="lines")
    order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name="+")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(WarehouseLocation, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # The bag or box taken from (Sidharth, 2026-11-20, previews 12a/12b); none for
    # stock that has no package numbers (opening stock, goods before packages).
    package = models.ForeignKey(
        Package, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    qty = models.DecimalField(**QTY, validators=[MinValueValidator(Decimal("0.000001"))])

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} {self.qty} from {self.location}"


class DeliveryNote(models.Model):
    """The goods going out to the customer (Sidharth, 2026-11-20, previews 7-9 in
    mockups/sales): made from a picked pick list, with its bins and batches.
    Submit takes the stock out at FIFO cost into "Goods Delivered but Bills not
    Made" (decided 2026-11-19); the sales invoice later moves that cost to Cost
    of Goods Sold and books the sale. The transport details are kept for the
    e-way bill, which comes with the invoice."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]
    ROAD, RAIL, AIR, SHIP = "road", "rail", "air", "ship"
    MODES = [(ROAD, "Road"), (RAIL, "Rail"), (AIR, "Air"), (SHIP, "Ship")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="delivery_notes")
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="delivery_notes")
    pick_list = models.ForeignKey(PickList, on_delete=models.PROTECT, related_name="delivery_notes")
    # The pick list's Despatch From.
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    area = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Given on Submit, from the "Delivery challan" series.
    number = models.CharField(max_length=30, blank=True)
    note_date = models.DateField()
    bill_from = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    ship_address = models.JSONField(default=dict, blank=True)
    # None: "By Customer" (the customer collects).
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    mode = models.CharField(max_length=5, choices=MODES, default=ROAD)
    vehicle_no = models.CharField(max_length=20, blank=True)
    distance_km = models.PositiveIntegerField(null=True, blank=True)
    lr_no = models.CharField(max_length=40, blank=True)
    lr_date = models.DateField(null=True, blank=True)
    packages = models.PositiveIntegerField(null=True, blank=True)
    gross_weight = models.DecimalField(**QTY, null=True, blank=True)  # kg
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    interstate = models.BooleanField(default=False)
    # At the order's rates, for the challan and the e-way bill.
    taxable_total = models.DecimalField(**MONEY, default=Decimal("0"))
    cgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    igst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    # Set on Submit: the FIFO cost of the goods sent.
    cost_total = models.DecimalField(**MONEY, default=Decimal("0"))
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
                "company",
                "number",
                condition=~models.Q(number=""),
                name="delivery_note_number_unique",
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft delivery note {self.pk}"


class DeliveryNoteLine(models.Model):
    """One order line going out; its quantity (in the line's unit) is what its
    bins send."""

    note = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY, default=Decimal("0"))
    rate = models.DecimalField(**QTY, default=Decimal("0"))
    taxable = models.DecimalField(**MONEY, default=Decimal("0"))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY, default=Decimal("0"))
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Submit

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class DeliveryNoteBin(models.Model):
    """A bin and batch a line's goods leave from. Quantities in the item's
    stock unit; `picked` is what the pick list had there."""

    line = models.ForeignKey(DeliveryNoteLine, on_delete=models.CASCADE, related_name="bins")
    location = models.ForeignKey(WarehouseLocation, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    package = models.ForeignKey(
        Package, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    picked = models.DecimalField(**QTY, default=Decimal("0"))
    qty = models.DecimalField(**QTY, default=Decimal("0"))
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Submit

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.line.item} {self.qty} from {self.location}"


class SalesInvoice(models.Model):
    """The tax invoice for one or more submitted delivery notes of one customer
    (Sidharth, 2026-11-20, previews 14a/14b in mockups/sales; several notes on one
    invoice, so one e-invoice, asked the same day). Quantities are what the notes
    sent; rates and the credit term are the order's and cannot change; an order's
    charges go on its first invoice. Submit books the sale: Dr the customer, Cr
    each item group's Sales Ledger and Output GST, and moves the notes' cost from
    "Goods Delivered but Bills not Made" to Cost of Goods Sold.

    The e-invoice (IRN) and e-way bill numbers are typed in from the portal for
    now (a JSON download feeds the portal); a provider's API comes later. The
    transport details stay open after Submit ("Update Transport"): they touch
    no ledger."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="sales_invoices")
    # The notes billed: same customer, Despatch From, Bill From, addresses and
    # credit term (selling.invoices.match_key).
    delivery_notes = models.ManyToManyField(DeliveryNote, related_name="invoices")
    # The notes' Despatch From branch: the voucher's branch.
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    bill_from = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Given on Submit, from the "Sales invoice" series of the Bill From branch.
    number = models.CharField(max_length=30, blank=True)
    invoice_date = models.DateField()
    bill_address = models.JSONField(default=dict, blank=True)
    ship_address = models.JSONField(default=dict, blank=True)
    place_of_supply = models.CharField(max_length=2, blank=True)  # state code
    credit_term = models.ForeignKey(
        CreditTerm, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Transport, for the e-way bill: from the note, changeable even after Submit.
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    mode = models.CharField(max_length=5, choices=DeliveryNote.MODES, default=DeliveryNote.ROAD)
    vehicle_no = models.CharField(max_length=20, blank=True)
    distance_km = models.PositiveIntegerField(null=True, blank=True)
    lr_no = models.CharField(max_length=40, blank=True)
    lr_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    interstate = models.BooleanField(default=False)
    taxable_total = models.DecimalField(**MONEY, default=Decimal("0"))
    cgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    igst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    round_off = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    # The note's FIFO cost, moved to Cost of Goods Sold on Submit.
    cost_total = models.DecimalField(**MONEY, default=Decimal("0"))
    # From the government portal, typed in after Submit.
    irn = models.CharField(max_length=64, blank=True)
    ack_no = models.CharField(max_length=20, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)
    signed_qr = models.TextField(blank=True)
    eway_bill_no = models.CharField(max_length=12, blank=True)
    eway_bill_date = models.DateTimeField(null=True, blank=True)
    eway_valid_until = models.DateTimeField(null=True, blank=True)
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
        ordering = ["-invoice_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company",
                "number",
                condition=~models.Q(number=""),
                name="sales_invoice_number_unique",
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft sales invoice {self.pk}"


class SalesInvoiceLine(models.Model):
    """One delivery note line billed: its quantity as sent, at the invoice's rate."""

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    note_line = models.ForeignKey(DeliveryNoteLine, on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY)
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    taxable = models.DecimalField(**MONEY, default=Decimal("0"))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY, default=Decimal("0"))
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # the note line's cost

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class SalesInvoiceCharge(models.Model):
    """An extra billed, such as freight: from the order, or added on the invoice."""

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="charges")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    basis = models.CharField(
        max_length=10, choices=SalesOrderCharge.BASES, default=SalesOrderCharge.FIXED
    )
    rate = models.DecimalField(**QTY, validators=[MinValueValidator(0)])
    amount = models.DecimalField(**MONEY)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.item} {self.amount}"


class SalesInvoiceDue(models.Model):
    """When the customer is to pay: one row per part of the credit term."""

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="dues")
    position = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.due_date}: {self.amount}"


class CreditNote(models.Model):
    """A GST credit note against a submitted sales invoice (Sidharth, 2026-11-21,
    previews 18a/18b/18c in mockups/sales), of one of three types, all with GST:

    * "Sales Return – goods come back": the quantity returned, at the invoice's
      rate and GST; the goods go back into a bin, in the batch that went out, at
      the cost they left at (Dr Stock, Cr Cost of Goods Sold);
    * "Sales Return – goods not coming back": the same credit, with no stock
      (the cost stays in Cost of Goods Sold);
    * "Rate Difference": the billed quantity at a lower rate; no stock or cost.

    Every type posts Dr each item group's Sales Ledger and Output GST, Cr the
    customer. Numbers come from the one "Credit note" series. The e-invoice
    (document type CRN) is made from its JSON on the portal, as for the invoice."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]
    GOODS_BACK, GOODS_KEPT, RATE = "goods_back", "goods_kept", "rate"
    KINDS = [
        (GOODS_BACK, "Sales Return – goods come back"),
        (GOODS_KEPT, "Sales Return – goods not coming back"),
        (RATE, "Rate Difference"),
    ]
    REASONS = [
        ("damaged", "Damaged in transit"),
        ("destroyed", "Damaged, destroyed at customer"),
        ("wrong_item", "Wrong item sent"),
        ("excess", "Excess sent"),
        ("quality", "Quality complaint"),
        ("short", "Short received by customer"),
        ("rate_lower", "Rate agreed lower"),
        ("wrong_rate", "Billed at wrong rate"),
        ("other", "Other"),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="credit_notes")
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="credit_notes")
    # The invoice's Despatch From branch: the voucher's branch, where goods come back.
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    bill_from = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    kind = models.CharField(max_length=10, choices=KINDS, default=GOODS_BACK)
    reason = models.CharField(max_length=12, choices=REASONS, default="damaged")
    # Given on Submit, from the "Credit note" series of the Bill From branch.
    number = models.CharField(max_length=30, blank=True)
    note_date = models.DateField()
    customer_ref = models.CharField(max_length=60, blank=True)
    remarks = models.CharField(max_length=200, blank=True)
    place_of_supply = models.CharField(max_length=2, blank=True)
    interstate = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    taxable_total = models.DecimalField(**MONEY, default=Decimal("0"))
    cgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    igst_total = models.DecimalField(**MONEY, default=Decimal("0"))
    round_off = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    # The cost of the goods that came back (goods_back only), set on Submit.
    cost_total = models.DecimalField(**MONEY, default=Decimal("0"))
    irn = models.CharField(max_length=64, blank=True)
    ack_no = models.CharField(max_length=20, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)
    signed_qr = models.TextField(blank=True)
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
                "company",
                "number",
                condition=~models.Q(number=""),
                name="credit_note_number_unique",
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft credit note {self.pk}"


class CreditNoteLine(models.Model):
    """One invoice line credited. A return of goods that come back has one line
    per batch that went out, with the bin it comes back into. For a rate
    difference, `rate` is the reduction per unit and `new_rate` the correct rate."""

    note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    invoice_line = models.ForeignKey(SalesInvoiceLine, on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    location = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    qty = models.DecimalField(**QTY, default=Decimal("0"))
    rate = models.DecimalField(**QTY, default=Decimal("0"))
    new_rate = models.DecimalField(**QTY, null=True, blank=True)
    taxable = models.DecimalField(**MONEY, default=Decimal("0"))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(**MONEY, default=Decimal("0"))
    sgst = models.DecimalField(**MONEY, default=Decimal("0"))
    igst = models.DecimalField(**MONEY, default=Decimal("0"))
    amount = models.DecimalField(**MONEY, default=Decimal("0"))
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # goods back: set on Submit

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"
