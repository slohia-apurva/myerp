"""Stock entries (Entry > Stock): the Stock Transfer between two branches of
one company, and the Stock Receipt and Stock Delivery of a customer's own goods
(Sidharth, 2026-11-22, previews 9a and 9c in mockups/planning)."""

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import (
    PACKAGE_TYPES,
    Batch,
    Branch,
    Company,
    Item,
    Ledger,
    Package,
    SalesPerson,
    Unit,
    WarehouseLocation,
)
from shipping.models import CourierAccount

MONEY = {"max_digits": 18, "decimal_places": 2}
QTY = {"max_digits": 18, "decimal_places": 6}


class StockTransfer(models.Model):
    """Goods moving from one branch to another of the same company and GSTIN.

    Draft -> Dispatch (the goods leave the From branch's bins and sit in the To
    branch's "In Transit" place, at the same FIFO cost) -> Receive (at the To
    branch: what came goes into its bins; a shortfall is a transit loss)."""

    DRAFT, IN_TRANSIT, RECEIVED, CANCELLED = "draft", "in_transit", "received", "cancelled"
    STATUSES = [
        (DRAFT, "Draft"),
        (IN_TRANSIT, "In Transit"),
        (RECEIVED, "Received"),
        (CANCELLED, "Cancelled"),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    from_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    # Pick only from this area (its racks and bins); else anywhere in the branch.
    from_area = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    to_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    # Where Receive puts the goods unless another place is chosen.
    to_area = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Given on Dispatch, from the "Stock transfer" series.
    number = models.CharField(max_length=30, blank=True)
    transfer_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    vehicle_no = models.CharField(max_length=20, blank=True)
    eway_bill_no = models.CharField(max_length=20, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default=DRAFT)
    value = models.DecimalField(**MONEY, default=Decimal("0"))  # at cost, set on Dispatch
    received_date = models.DateField(null=True, blank=True)
    shortfall_reason = models.CharField(max_length=200, blank=True)
    shortfall_value = models.DecimalField(**MONEY, default=Decimal("0"))
    cancel_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Made by planning (Sidharth, 2026-11-22, preview 9b): on Submit of this sales
    # order, or by this Stock Check run (by hand or daily).
    sales_order = models.ForeignKey(
        "selling.SalesOrder",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_transfers",
    )
    stock_check_run = models.ForeignKey(
        "buying.StockCheckRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_transfers",
    )

    class Meta:
        ordering = ["-transfer_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company",
                "number",
                condition=~models.Q(number=""),
                name="stock_transfer_number_unique",
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft stock transfer {self.pk}"


class StockTransferLine(models.Model):
    """One item going across, in a unit of the item."""

    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY)
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Dispatch

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class StockTransferBin(models.Model):
    """A bin and batch (and package) a line's goods leave from, in the item's
    stock unit; on Receive, how much of it came and where it was put."""

    line = models.ForeignKey(StockTransferLine, on_delete=models.CASCADE, related_name="bins")
    location = models.ForeignKey(WarehouseLocation, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    package = models.ForeignKey(
        Package, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # True when the whole package went across (it moves with the goods).
    whole_package = models.BooleanField(default=False)
    qty = models.DecimalField(**QTY)
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Dispatch
    received_qty = models.DecimalField(**QTY, null=True, blank=True)
    put_location = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.line.item} {self.qty} from {self.location}"


class CustomerStock(models.Model):
    """A customer's own goods coming in (Stock Receipt: their tea for job work,
    their packing material, against their challan) or going back to them unused
    (Stock Delivery), Sidharth 2026-11-22, preview 9c. Only items marked
    "Customer Provided". Quantity only: nothing in the books, and the goods are
    held as that customer's stock, never mixed with ours or another customer's.

    Draft -> Submit (numbered, stock moved) -> Cancel (stock moved back)."""

    RECEIPT, DELIVERY = "receipt", "delivery"
    KINDS = [(RECEIPT, "Stock Receipt"), (DELIVERY, "Stock Delivery")]
    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=KINDS)
    customer = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    # Receipt: where lines go unless they name a place; Delivery: pick only here.
    area = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    number = models.CharField(max_length=30, blank=True)  # given on Submit
    entry_date = models.DateField()
    # Receipt: the customer's own challan that came with the goods.
    challan_no = models.CharField(max_length=40, blank=True)
    challan_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    # None: brought or taken by the customer.
    transporter = models.ForeignKey(
        CourierAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    vehicle_no = models.CharField(max_length=20, blank=True)
    eway_bill_no = models.CharField(max_length=20, blank=True)
    # Receipt: "Received By"; Delivery: "Handed Over By" (a stores person).
    stores_person = models.ForeignKey(
        SalesPerson, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
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
        ordering = ["-entry_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company",
                "kind",
                "number",
                condition=~models.Q(number=""),
                name="customer_stock_number_unique",
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft {self.get_kind_display().lower()} {self.pk}"


class CustomerStockLine(models.Model):
    """One item, in a unit of the item. A receipt line says where it is put
    (and its batch and bags); a delivery line's bins are picked (below)."""

    entry = models.ForeignKey(CustomerStock, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY)
    location = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    batch_number = models.CharField(max_length=60, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )  # set on Submit
    bags = models.PositiveIntegerField(default=0)
    package_type = models.CharField(max_length=10, choices=PACKAGE_TYPES, default="bag")

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class CustomerStockBin(models.Model):
    """A bin and batch (and package) a delivery line's goods leave from, in the
    item's stock unit, picked from that customer's stock only."""

    line = models.ForeignKey(CustomerStockLine, on_delete=models.CASCADE, related_name="bins")
    location = models.ForeignKey(WarehouseLocation, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    package = models.ForeignKey(
        Package, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    qty = models.DecimalField(**QTY)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.line.item} {self.qty} from {self.location}"


class OwnUse(models.Model):
    """Our own stock used inside the company: office, canteen, maintenance, R&D,
    damaged and thrown away (Sidharth, 2026-11-22, preview 9c). The goods leave
    their bins at FIFO cost: Dr each line's Expense Ledger (the item's own
    Expense Account to start with), Cr Stock. Draft -> Submit -> Cancel.
    A draft counts as Reserved in the Stock Check."""

    DRAFT, SUBMITTED, CANCELLED = "draft", "submitted", "cancelled"
    STATUSES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (CANCELLED, "Cancelled")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    # Pick only from this area (its racks and bins); else anywhere in the branch.
    area = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    number = models.CharField(max_length=30, blank=True)  # given on Submit
    entry_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)
    # The stores person who gave the goods out.
    stores_person = models.ForeignKey(
        SalesPerson, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    value = models.DecimalField(**MONEY, default=Decimal("0"))  # at cost, set on Submit
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
        ordering = ["-entry_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company",
                "number",
                condition=~models.Q(number=""),
                name="own_use_number_unique",
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft own use {self.pk}"


class OwnUseLine(models.Model):
    """One item used, in a unit of the item, and the ledger it is charged to."""

    entry = models.ForeignKey(OwnUse, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY)
    # Blank: the item's Expense Account for the company (else its group's).
    expense_ledger = models.ForeignKey(
        Ledger, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Submit

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} × {self.qty}"


class OwnUseBin(models.Model):
    """A bin and batch (and package) a line's goods are taken from, in the
    item's stock unit."""

    line = models.ForeignKey(OwnUseLine, on_delete=models.CASCADE, related_name="bins")
    location = models.ForeignKey(WarehouseLocation, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(
        Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    package = models.ForeignKey(
        Package, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    qty = models.DecimalField(**QTY)
    cost = models.DecimalField(**MONEY, default=Decimal("0"))  # set on Submit

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.line.item} {self.qty} from {self.location}"
