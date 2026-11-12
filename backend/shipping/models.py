"""Shipments of sales consignments by courier, and their tracking (spec 06).

A shipment is one AWB (or docket or LR number) with one courier account.
Its status comes from its tracking events, which are never edited or deleted:
typed by a person today, pulled from the courier or aggregator later. Nothing
here posts to the ledgers.
"""

import datetime
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from core import india
from core.models import Branch, Company, Party

# Letters, digits and hyphens: what any carrier's tracking number looks like
# when the carrier master has no stricter pattern.
ANY_AWB = re.compile(r"^[A-Z0-9-]{6,30}$")


def clean_awb(value: str) -> str:
    """The tracking number as stored: spaces dropped, capitals."""
    return re.sub(r"\s+", "", value or "").upper()


def check_awb(awb: str, carrier) -> str:
    """Why `awb` is not a valid number for `carrier` (a tenancy.Carrier), or ""."""
    if not ANY_AWB.match(awb):
        return "A tracking number is 6 to 30 letters, digits or hyphens."
    if carrier is not None and carrier.awb_pattern and not re.fullmatch(carrier.awb_pattern, awb):
        hint = f" ({carrier.awb_hint})" if carrier.awb_hint else ""
        return f"This does not look like a {carrier.name} number{hint}."
    return ""


class CourierAccount(models.Model):
    """A transporter of a company (shown as "Transporter" on the screens): a
    courier, aggregator, airline or road transporter it ships with, e.g.
    "Delhivery B2B". It may point at a carrier of the central list (for AWB
    checks, tracking pages and PIN coverage) or stand alone for a local
    transporter. One carrier can have several (B2C parcel and B2B freight),
    each with its own rates and, later, its own API keys (kept in Secret
    Manager, never here). The GSTIN is the Transporter ID of an e-way bill.
    Never deleted, only disabled."""

    B2C, B2B, AGGREGATOR = "b2c", "b2b", "aggregator"
    SERVICES = [
        (B2C, "B2C (parcel / express)"),
        (B2B, "B2B (freight)"),
        (AGGREGATOR, "Aggregator"),
    ]
    TYPED, AUTOMATIC = "typed", "automatic"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="courier_accounts")
    # tenancy.Carrier lives in the platform database, so it is kept by id.
    carrier_id = models.PositiveIntegerField(null=True, blank=True)
    name = models.CharField(max_length=60)
    # Required on the screen (an e-way bill needs the Transporter ID); the
    # state comes from its first two digits.
    gstin = models.CharField(max_length=15, blank=True, validators=[india.validate_gstin])
    state_code = models.CharField(max_length=2, blank=True)
    address = models.TextField(blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    city = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[india.validate_phone])
    email = models.EmailField(blank=True)
    contact_person = models.CharField(max_length=100, blank=True)
    service = models.CharField(max_length=12, choices=SERVICES, default=B2C)
    account_code = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "company", Lower("name"), name="courier_account_name_unique_per_company"
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        self.gstin = self.gstin.strip().upper()
        self.state_code = self.gstin[:2]
        if self.pincode and not re.fullmatch(r"[1-9][0-9]{5}", self.pincode):
            raise ValidationError({"pincode": "A PIN code is 6 digits."})


class Status(models.TextChoices):
    """One list every carrier's own status codes are mapped to (spec 06)."""

    BOOKED = "booked", "Booked"
    PICKED_UP = "picked_up", "Picked up"
    IN_TRANSIT = "in_transit", "In transit"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
    DELIVERY_FAILED = "delivery_failed", "Delivery failed"
    HELD = "held", "Held"
    RTO = "rto", "Returning to us (RTO)"
    DELIVERED = "delivered", "Delivered"
    RTO_DELIVERED = "rto_delivered", "Returned to us"
    LOST = "lost", "Lost or damaged"
    CANCELLED = "cancelled", "Booking cancelled"
    UNKNOWN = "unknown", "Unknown carrier status"


CLOSED = {Status.DELIVERED, Status.RTO_DELIVERED, Status.LOST, Status.CANCELLED}
NEEDS_ACTION = {Status.DELIVERY_FAILED, Status.HELD, Status.RTO, Status.LOST, Status.UNKNOWN}

# Settings the despatch email will share: when an open shipment counts as late.
NOT_PICKED_UP_AFTER = datetime.timedelta(hours=24)
NO_MOVEMENT_DAYS = 3


class Shipment(models.Model):
    """One AWB with one courier account: what was sent, to whom, and where it
    is now. Before Sales is built the despatch team types the customer and
    the ERPNext invoice or delivery note number; delivery notes link here
    later. A wrong entry is cancelled, never deleted."""

    PREPAID, TO_PAY, COD = "prepaid", "to_pay", "cod"
    PAYMENTS = [(PREPAID, "Prepaid"), (TO_PAY, "To pay"), (COD, "Cash on delivery")]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="shipments")
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="shipments"
    )
    account = models.ForeignKey(CourierAccount, on_delete=models.PROTECT, related_name="shipments")
    # Copied from the account, for the AWB check; empty for a transporter that
    # is not in the central list.
    carrier_id = models.PositiveIntegerField(null=True, blank=True)
    awb = models.CharField(max_length=30)
    booked_on = models.DateField()
    party = models.ForeignKey(
        Party, null=True, blank=True, on_delete=models.PROTECT, related_name="shipments"
    )
    # The invoice or delivery note this went out against (typed until Sales exists).
    reference = models.CharField(max_length=60, blank=True)
    ship_to_city = models.CharField(max_length=60, blank=True)
    ship_to_pincode = models.CharField(max_length=6, blank=True)
    packages = models.PositiveIntegerField(default=1)
    weight_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    payment = models.CharField(max_length=8, choices=PAYMENTS, default=PREPAID)
    cod_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    expected_on = models.DateField(null=True, blank=True)  # the carrier's EDD
    notes = models.TextField(blank=True)

    # Worked out from the events (refresh_status); never typed.
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOOKED)
    last_event_at = models.DateTimeField(null=True, blank=True)
    last_place = models.CharField(max_length=100, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    received_by = models.CharField(max_length=100, blank=True)

    cancelled = models.BooleanField(default=False)
    cancel_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-booked_on", "-id"]
        constraints = [
            models.UniqueConstraint(
                "carrier_id",
                "awb",
                condition=Q(cancelled=False),
                name="shipment_awb_unique_per_carrier",
            ),
            models.UniqueConstraint(
                "account",
                "awb",
                condition=Q(cancelled=False, carrier_id__isnull=True),
                name="shipment_awb_unique_per_account",
            ),
        ]

    def __str__(self) -> str:
        return self.awb

    @property
    def is_open(self) -> bool:
        return not self.cancelled and self.status not in CLOSED

    def refresh_status(self) -> None:
        """Set the status and last event from the latest event; save."""
        last = self.events.order_by("-at", "-id").first()
        self.status = last.status if last else Status.BOOKED
        self.last_event_at = last.at if last else None
        self.last_place = last.place if last else ""
        delivered = self.events.filter(status=Status.DELIVERED).order_by("-at", "-id").first()
        self.delivered_at = delivered.at if delivered else None
        self.received_by = delivered.received_by if delivered else ""
        self.save(
            update_fields=[
                "status",
                "last_event_at",
                "last_place",
                "delivered_at",
                "received_by",
            ]
        )

    def alerts(self, now: datetime.datetime | None = None) -> list[str]:
        """Why this shipment needs the despatch team's attention, for the
        screen's "Needs action" list and the daily email."""
        if not self.is_open:
            return ["Lost or damaged"] if self.status == Status.LOST and not self.cancelled else []
        now = now or timezone.now()
        today = timezone.localdate(now)
        out = []
        if self.status in NEEDS_ACTION:
            out.append(self.get_status_display())
        if self.expected_on and today > self.expected_on:
            out.append("Past expected delivery date")
        if self.status == Status.BOOKED:
            booked = timezone.make_aware(
                datetime.datetime.combine(self.booked_on, datetime.time(18, 0))
            )
            if now - booked > NOT_PICKED_UP_AFTER:
                out.append("Not picked up")
        elif self.last_event_at and now - self.last_event_at > datetime.timedelta(
            days=NO_MOVEMENT_DAYS
        ):
            out.append(f"No movement for {NO_MOVEMENT_DAYS} days")
        return out


class TrackingEvent(models.Model):
    """One status update of a shipment. Never edited or deleted: a wrong one
    is followed by a correct one. The same event arriving twice (same time,
    status and carrier code) is dropped."""

    TYPED, PULLED, WEBHOOK = "typed", "pulled", "webhook"
    SOURCES = [(TYPED, "Typed"), (PULLED, "Fetched from carrier"), (WEBHOOK, "Sent by carrier")]

    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="events")
    at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices)
    place = models.CharField(max_length=100, blank=True)
    carrier_code = models.CharField(max_length=40, blank=True)
    carrier_text = models.CharField(max_length=200, blank=True)
    received_by = models.CharField(max_length=100, blank=True)  # on a delivery
    source = models.CharField(max_length=8, choices=SOURCES, default=TYPED)
    raw = models.JSONField(null=True, blank=True)  # the carrier's reply, as sent
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]
        constraints = [
            models.UniqueConstraint(
                "shipment", "at", "status", "carrier_code", name="tracking_event_once"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_status_display()} at {self.at:%d-%m-%Y %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Tracking events cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Tracking events cannot be deleted.")
