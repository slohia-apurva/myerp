from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

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
    """Whether a courier delivers to a PIN code, and its out-of-delivery-area
    (ODA) flag. One row per courier and PIN, so lists from other couriers sit
    beside the first and are merged by PIN."""

    courier = models.CharField(max_length=60)
    pin = models.ForeignKey(PinCode, on_delete=models.CASCADE, related_name="couriers")
    oda = models.BooleanField(null=True, blank=True)  # blank = not known
    dispatch_center = models.CharField(max_length=120, blank=True)
    origin_center = models.CharField(max_length=120, blank=True)
    return_center = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["courier", "pin_id"]
        constraints = [
            models.UniqueConstraint(fields=["courier", "pin"], name="one_row_per_courier_pin")
        ]

    def __str__(self) -> str:
        return f"{self.courier} {self.pin_id}"
