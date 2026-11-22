"""Bills of materials (Sidharth, 2026-11-22, preview 14 in mockups/planning).

A BOM says what one batch of an item needs: its materials, with a loss allowed
on each, and the by-products and scrap it gives. An item can have several
versions; exactly one active version is its Default, which planning and new
Manufacturing Orders start from. A BOM posts nothing.

BOMs are kept for the whole group of companies, like items."""

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from core.models import Branch, Company, Item, Party, SalesPerson, Unit, WarehouseLocation

QTY = {"max_digits": 18, "decimal_places": 6}
MONEY = {"max_digits": 18, "decimal_places": 2}


class Bom(models.Model):
    OWN, JOB_WORK = "own", "job_work"
    KINDS = [(OWN, "Own production"), (JOB_WORK, "Job work for a customer")]
    DRAFT, ACTIVE = "draft", "active"
    STATUSES = [(DRAFT, "Draft"), (ACTIVE, "Active")]

    number = models.CharField(max_length=20, unique=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="boms")
    version = models.PositiveIntegerField()
    name = models.CharField(max_length=80)
    is_default = models.BooleanField(default=False)
    kind = models.CharField(max_length=10, choices=KINDS, default=OWN)
    # Job work: whose goods it is made from (optional: a version may serve any customer).
    customer = models.ForeignKey(
        Party, null=True, blank=True, on_delete=models.PROTECT, related_name="boms"
    )
    makes_qty = models.DecimalField(**QTY)
    makes_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    valid_from = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    # How to pack it (Sidharth, 2026-11-23): copied onto each Manufacturing Order.
    packing_notes = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=STATUSES, default=ACTIVE)
    is_active = models.BooleanField(default=True)  # cleared by the "Disabled" tick
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["item__name", "version"]
        verbose_name = "BOM"
        constraints = [
            models.UniqueConstraint(fields=["item", "version"], name="bom_version_once"),
            models.UniqueConstraint("item", Lower("name"), name="bom_name_once_per_item"),
            models.UniqueConstraint(
                fields=["item"], condition=models.Q(is_default=True), name="bom_one_default"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} {self.item} v{self.version}"


class BomLine(models.Model):
    """One material for `makes_qty` of the item. `loss_pct` is added on top when
    a Manufacturing Order works out what to issue."""

    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField(default=0)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="bom_uses")
    qty = models.DecimalField(**QTY)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    loss_pct = models.DecimalField(max_digits=7, decimal_places=3, default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} {self.qty}"


class BomByproduct(models.Model):
    """A by-product or scrap a batch gives. One with a value lowers the cost of
    the main item; the production entry receives it into stock later."""

    SCRAP, BY_PRODUCT = "scrap", "by_product"
    KINDS = [(SCRAP, "Scrap"), (BY_PRODUCT, "By-product")]

    bom = models.ForeignKey(Bom, on_delete=models.CASCADE, related_name="byproducts")
    position = models.PositiveIntegerField(default=0)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="bom_byproducts")
    qty = models.DecimalField(**QTY)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=KINDS, default=SCRAP)
    rate = models.DecimalField(**QTY, default=0)  # value of one unit; 0 for worthless scrap

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} {self.qty}"


class ManufacturingOrder(models.Model):
    """What to make, how much, by when and with which BOM version (Sidharth,
    2026-11-23, preview 15d). It posts nothing: the Material Issue and the
    Production Entry that follow move the stock.

    Materials: the lines from the BOM version are fixed (worked out from it for
    the order's quantity); lines added on the order ("Added") may be changed or
    removed, on a draft and after Submit until the order is done. Pack Details
    start from the item (MRP, USP, Batch No, Best Before) and the BOM (Packing
    Notes) and may be changed on the order."""

    DRAFT, NOT_STARTED, IN_PROCESS = "draft", "not_started", "in_process"
    COMPLETED, CLOSED, CANCELLED = "completed", "closed", "cancelled"
    STATUSES = [
        (DRAFT, "Draft"),
        (NOT_STARTED, "Not Started"),
        (IN_PROCESS, "In Process"),
        (COMPLETED, "Completed"),
        (CLOSED, "Closed"),
        (CANCELLED, "Cancelled"),
    ]
    OPEN = (NOT_STARTED, IN_PROCESS)
    DAYS, MONTHS = Item.DAYS, Item.MONTHS

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=30, blank=True)  # given on Submit
    order_date = models.DateField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="manufacturing_orders")
    qty = models.DecimalField(**QTY)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    bom = models.ForeignKey(Bom, on_delete=models.PROTECT, related_name="orders")
    # Job work: whose goods it is made from.
    customer = models.ForeignKey(
        Party, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    start_date = models.DateField()
    due_date = models.DateField()
    sales_order = models.ForeignKey(
        "selling.SalesOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    materials_from = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    goods_to = models.ForeignKey(
        WarehouseLocation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    supervisor = models.ForeignKey(
        SalesPerson, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.TextField(blank=True)
    # Pack Details.
    mrp = models.DecimalField(**MONEY, null=True, blank=True)
    usp = models.DecimalField(**MONEY, null=True, blank=True)
    usp_per = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    batch_no = models.CharField(max_length=60, blank=True)
    pkd_date = models.DateField(null=True, blank=True)
    best_before_value = models.PositiveIntegerField(null=True, blank=True)
    best_before_unit = models.CharField(max_length=6, choices=Item.PERIODS, default=DAYS)
    expiry_date = models.DateField(null=True, blank=True)
    packing_notes = models.TextField(blank=True)
    made_qty = models.DecimalField(**QTY, default=0)  # in the order's unit, by Production Entries
    status = models.CharField(max_length=12, choices=STATUSES, default=DRAFT)
    cancel_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-order_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                "company", "number", condition=~models.Q(number=""), name="mo_number_unique"
            )
        ]

    def __str__(self) -> str:
        return self.number or f"Draft manufacturing order {self.pk}"


class ManufacturingOrderLine(models.Model):
    """One material for the whole order. `per_unit` is for one of the order's
    unit; `required` = per_unit x qty, plus the loss. A line from the BOM is
    fixed; an added one is not."""

    order = models.ForeignKey(ManufacturingOrder, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="+")
    per_unit = models.DecimalField(**QTY)
    loss_pct = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    required = models.DecimalField(**QTY)
    issued = models.DecimalField(**QTY, default=0)  # by Material Issues
    from_bom = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.item} x {self.required}"
