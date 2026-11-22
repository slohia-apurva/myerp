"""Bills of materials (Sidharth, 2026-11-22, preview 14 in mockups/planning).

A BOM says what one batch of an item needs: its materials, with a loss allowed
on each, and the by-products and scrap it gives. An item can have several
versions; exactly one active version is its Default, which planning and new
Manufacturing Orders start from. A BOM posts nothing.

BOMs are kept for the whole group of companies, like items."""

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from core.models import Item, Party, Unit

QTY = {"max_digits": 18, "decimal_places": 6}


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
