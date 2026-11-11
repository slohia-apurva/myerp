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
