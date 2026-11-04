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
