from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

slug_validator = RegexValidator(
    r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$",
    "Use 3-40 lowercase letters, digits or hyphens, starting with a letter.",
)


class Tenant(models.Model):
    """A customer: one group of companies with its own database and users.

    Lives in the platform database. Everything the tenant owns (companies,
    users, masters, ledgers) lives in the tenant's own database.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    slug = models.CharField(max_length=40, unique=True, validators=[slug_validator])
    name = models.CharField(max_length=200)
    db_name = models.CharField(max_length=63, unique=True)
    # Blank host/port = same PostgreSQL server as the platform database.
    # A large tenant moves to its own server by filling these in.
    db_host = models.CharField(max_length=255, blank=True)
    db_port = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return self.slug

    @property
    def db_alias(self) -> str:
        return "tenant_" + self.slug.replace("-", "_")


class HsnCode(models.Model):
    """An HSN (goods) or SAC (services) code with its description. One central
    list for every tenant (decision: global masters live in the platform
    database), searched as people type an item's HSN and read-only to them.
    Loaded with `manage.py import_hsn`. The GST rate belongs to a separate
    dated master."""

    hsn_code = models.CharField(max_length=8, unique=True)
    description = models.CharField(max_length=500)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["hsn_code"]

    def __str__(self) -> str:
        return f"{self.hsn_code} {self.description}"

    def clean(self):
        if not self.hsn_code.isdigit() or len(self.hsn_code) not in (2, 4, 6, 8):
            raise ValidationError({"hsn_code": "An HSN code is 2, 4, 6 or 8 digits."})


class State(models.Model):
    """A GST state or union territory. One central list for every tenant."""

    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Country(models.Model):
    """A country (ISO 3166-1 alpha-2 code). One central list for every tenant."""

    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self) -> str:
        return self.name


class PinCode(models.Model):
    """An Indian PIN code with its city and state. One central list for every
    tenant; typing a PIN on a party form fills the state from it. Loaded with
    `manage.py import_pins`."""

    pin = models.CharField(max_length=6, unique=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.ForeignKey(State, null=True, blank=True, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["pin"]

    def __str__(self) -> str:
        return f"{self.pin} {self.city}"


class CourierPin(models.Model):
    """Whether a carrier delivers to a PIN code, and its out-of-delivery-area
    (ODA) flag. One row per carrier and PIN, so lists from other couriers sit
    beside the first and are merged by PIN."""

    carrier = models.ForeignKey("Carrier", on_delete=models.PROTECT, related_name="pins")
    pin = models.ForeignKey(PinCode, on_delete=models.CASCADE, related_name="couriers")
    oda = models.BooleanField(null=True, blank=True)  # blank = not known
    dispatch_center = models.CharField(max_length=120, blank=True)
    origin_center = models.CharField(max_length=120, blank=True)
    return_center = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["carrier__name", "pin_id"]
        constraints = [
            models.UniqueConstraint(fields=["carrier", "pin"], name="one_row_per_courier_pin")
        ]

    def __str__(self) -> str:
        return f"{self.carrier} {self.pin_id}"


class GstRate(models.Model):
    """A GST rate (0, 5, 18...) offered when setting an item's rate. One central
    list for every tenant, read-only to them, like HSN codes. Items keep their
    own dated history of which rate applied from when (core.ItemGstRate); this
    list only says which rates exist. Never deleted, only disabled."""

    rate = models.DecimalField(max_digits=5, decimal_places=2, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["rate"]

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        return f"GST {self.rate.normalize():f}%"


class Carrier(models.Model):
    """A courier, aggregator or transporter (Delhivery, Blue Dart, Shiprocket...).
    One central list for every tenant, read-only to them, like HSN codes; a
    tenant's own accounts with a carrier (B2C, B2B) live in its database
    (shipping.CourierAccount). Spec 06. The PIN serviceability rows of each
    courier point here too."""

    COURIER, AGGREGATOR, AIRLINE, TRANSPORTER = "courier", "aggregator", "airline", "transporter"
    KINDS = [
        (COURIER, "Courier"),
        (AGGREGATOR, "Aggregator (books with many couriers)"),
        (AIRLINE, "Airline or air cargo"),
        (TRANSPORTER, "Road transporter"),
    ]

    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=12, choices=KINDS, default=COURIER)
    # A regular expression a tracking number must match, when the carrier's
    # format is known; blank accepts any letters, digits and hyphens.
    awb_pattern = models.CharField(max_length=120, blank=True)
    awb_hint = models.CharField(max_length=80, blank=True)  # e.g. "11 digits"
    # The carrier's public tracking page, with {awb} where the number goes.
    tracking_url = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="carrier_name_unique")]

    def __str__(self) -> str:
        return self.name


class CentralRequest(models.Model):
    """A customer's request to add an entry to a central list (an HSN or SAC code,
    a GST rate...), sent to the MyERP team from a "Request Addition" screen. The
    team adds the entry on the Central screen and marks the request Added."""

    HSN, GST_RATE = "hsn", "gst_rate"
    COUNTRY, PIN = "country", "pin"
    KINDS = [
        (HSN, "HSN or SAC code"),
        (GST_RATE, "GST rate"),
        (COUNTRY, "Country"),
        (PIN, "PIN code"),
    ]
    OPEN, ADDED, DECLINED = "open", "added", "declined"
    STATUSES = [(OPEN, "Open"), (ADDED, "Added to the list"), (DECLINED, "Not needed")]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="central_requests")
    kind = models.CharField(max_length=12, choices=KINDS)
    # The HSN code, GST rate, country name or PIN asked for. A country's 2-letter code is
    # kept in `description`; a PIN's city and GST state code in `city` and `state_code`.
    entry = models.CharField(max_length=40)
    description = models.CharField(max_length=500, blank=True)
    note = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state_code = models.CharField(max_length=2, blank=True)
    requested_by = models.CharField(max_length=254, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # The requester has read the decision (the notice on their Home screen is dismissed).
    seen = models.BooleanField(default=False)

    class Meta:
        ordering = ["status", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("entry"),
                "kind",
                "tenant",
                condition=models.Q(status="open"),
                name="one_open_central_request_per_entry",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.entry}"


class CarrierRequest(models.Model):
    """A customer's transporter that is not in the central list of couriers.
    Saving such a transporter leaves a request here, with an optional note, so
    the MyERP team can add the courier to the central list (Central screen)."""

    OPEN, ADDED, DECLINED = "open", "added", "declined"
    STATUSES = [(OPEN, "Open"), (ADDED, "Added to the list"), (DECLINED, "Not needed")]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="carrier_requests")
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=15, blank=True)
    note = models.TextField(blank=True)
    requested_by = models.CharField(max_length=254, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "tenant",
                condition=models.Q(status="open"),
                name="one_open_carrier_request_per_name",
            )
        ]

    def __str__(self) -> str:
        return self.name
