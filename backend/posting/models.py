"""The two ledgers every balance comes from (design rule 1): GL entries and
stock moves. Rows are written only by `posting.service` and never changed
or deleted (rule 2); a cancel writes the exact reversal. The database
refuses updates and deletes, and refuses a voucher whose GL rows do not
balance (migration 0001)."""

from decimal import Decimal

from django.db import models
from django.db.models import Q


class VoucherRef(models.Model):
    """Which document a row came from. `voucher_type` is a short code such as
    "goods_receipt"; `voucher_id` that document's id; `voucher_no` its number
    as printed."""

    voucher_type = models.CharField(max_length=30)
    voucher_id = models.PositiveBigIntegerField()
    voucher_no = models.CharField(max_length=40)
    # A row written by cancelling the voucher: the exact reverse of an original row.
    is_reversal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        abstract = True


class GLEntry(VoucherRef):
    """One line of a voucher in the general ledger: a debit or a credit to one
    ledger, in rupees."""

    company = models.ForeignKey("core.Company", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="+")
    date = models.DateField()
    ledger = models.ForeignKey("core.Ledger", on_delete=models.PROTECT, related_name="gl_entries")
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    remarks = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["date", "id"]
        verbose_name = "GL entry"
        verbose_name_plural = "GL entries"
        indexes = [
            models.Index(fields=["company", "ledger", "date"]),
            models.Index(fields=["voucher_type", "voucher_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(Q(debit__gt=0) & Q(credit=0)) | (Q(credit__gt=0) & Q(debit=0)),
                name="gl_entry_one_side",
            ),
        ]

    def __str__(self) -> str:
        side = f"Dr {self.debit}" if self.debit else f"Cr {self.credit}"
        return f"{self.voucher_no}: {self.ledger_id} {side}"


class StockMove(VoucherRef):
    """One movement of an item into (+qty) or out of (-qty) a place in a
    warehouse (a bin or an area of a branch), with its batch. `value` is the
    signed rupee value it moved at: the given rate for a receipt, the FIFO cost
    of the lots used for an issue. A move that is not valued (goods a customer
    owns) has value 0 and touches no lot and no GL."""

    company = models.ForeignKey("core.Company", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(
        "core.WarehouseLocation", on_delete=models.PROTECT, related_name="stock_moves"
    )
    item = models.ForeignKey("core.Item", on_delete=models.PROTECT, related_name="stock_moves")
    batch = models.ForeignKey(
        "core.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="stock_moves"
    )
    date = models.DateField()
    qty = models.DecimalField(max_digits=18, decimal_places=6)
    rate = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0"))
    value = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    valued = models.BooleanField(default=True)
    # Whose goods these are when they are not ours: a customer's own goods taken
    # in by a Stock Receipt (quantity only, never valued). Kept apart per owner.
    owner = models.ForeignKey(
        "core.Party", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["date", "id"]
        indexes = [
            models.Index(fields=["company", "item", "branch", "date"]),
            models.Index(fields=["item", "location", "batch"]),
            models.Index(fields=["voucher_type", "voucher_id"]),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(qty=0), name="stock_move_not_zero"),
        ]

    def __str__(self) -> str:
        return f"{self.voucher_no}: {self.item_id} {self.qty}"


class StockLot(models.Model):
    """A FIFO lot (decision 0002): what one valued receipt brought into a
    branch, and how much of it is left. Issues use the oldest lots first. This
    is working state kept beside the ledger, so it does change."""

    company = models.ForeignKey("core.Company", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey("core.Item", on_delete=models.PROTECT, related_name="+")
    date = models.DateField()
    rate = models.DecimalField(max_digits=18, decimal_places=6)
    qty_in = models.DecimalField(max_digits=18, decimal_places=6)
    value_in = models.DecimalField(max_digits=18, decimal_places=2)
    qty_left = models.DecimalField(max_digits=18, decimal_places=6)
    value_left = models.DecimalField(max_digits=18, decimal_places=2)
    move = models.OneToOneField(StockMove, on_delete=models.PROTECT, related_name="lot")

    class Meta:
        ordering = ["date", "id"]
        indexes = [models.Index(fields=["item", "branch", "date"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(qty_left__gte=0) & Q(qty_left__lte=models.F("qty_in")),
                name="stock_lot_left_in_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_id} {self.date}: {self.qty_left} of {self.qty_in} @ {self.rate}"


class StockLotUse(models.Model):
    """How much of a lot an issue used, so a cancel can put it back."""

    move = models.ForeignKey(StockMove, on_delete=models.PROTECT, related_name="lot_uses")
    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name="uses")
    qty = models.DecimalField(max_digits=18, decimal_places=6)
    value = models.DecimalField(max_digits=18, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.qty} of lot {self.lot_id}"


class StockRevaluation(VoucherRef):
    """A change in the value of stock already received, with no change in its
    quantity: the supplier billed a different rate than the goods receipt
    took (rule 11). It changes the lot's value left, so later issues cost the
    corrected rate. `qty_left` is the lot's quantity when it was written; a
    cancel is refused once the lot has been issued since."""

    company = models.ForeignKey("core.Company", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("core.Branch", on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey("core.Item", on_delete=models.PROTECT, related_name="+")
    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name="revaluations")
    date = models.DateField()
    value = models.DecimalField(max_digits=18, decimal_places=2)
    qty_left = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        ordering = ["date", "id"]
        indexes = [models.Index(fields=["voucher_type", "voucher_id"])]
        constraints = [
            models.CheckConstraint(condition=~Q(value=0), name="stock_revaluation_not_zero"),
        ]

    def __str__(self) -> str:
        return f"{self.voucher_no}: lot {self.lot_id} {self.value}"
