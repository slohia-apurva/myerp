"""Stock entries (Entry > Stock). First the Stock Transfer between two branches
of one company (Sidharth, 2026-11-22, preview 9a in mockups/planning)."""

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import Batch, Branch, Company, Item, Package, Unit, WarehouseLocation
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
