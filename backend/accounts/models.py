"""Users live in each tenant's own database, so a person added to one tenant
cannot sign in to another (design rule 16).

People are known by email address. They sign in with Google; MyERP keeps no
passwords (see docs/decisions/0007-login-with-google.md).
"""

import base64

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from accounts import permissions
from accounts.roles import OWNER
from core import india


class Role(models.Model):
    """A named set of permissions, e.g. Accountant. Stored per tenant."""

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    # Came with MyERP (can be edited, not disabled); Owner cannot be edited.
    is_standard = models.BooleanField(default=False)
    # Roles are never deleted, only disabled (Sidharth, 12 Nov 2026).
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="role_name_unique")]

    def __str__(self) -> str:
        return self.name

    @property
    def is_owner(self) -> bool:
        return self.code == OWNER


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, full_name: str = "", **extra) -> "User":
        user = self.model(email=email, full_name=full_name, **extra)
        user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    # Printed as "Our Contact" on documents this person makes.
    phone = models.CharField("mobile", max_length=20, blank=True, validators=[india.validate_phone])
    # A small PNG or JPG, printed above "Authorised Signatory" on documents
    # this person submits. Kept in the tenant database with the books.
    signature = models.BinaryField(null=True, blank=True, editable=False)
    signature_type = models.CharField(max_length=20, blank=True, editable=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    # Google's permanent account id, recorded at first sign-in. If the email
    # address is later given to a different Google account, it cannot sign in.
    google_sub = models.CharField(max_length=255, blank=True, default="")
    roles = models.ManyToManyField(Role, blank=True, related_name="users")
    # Companies this person may work in; none ticked means all companies.
    companies = models.ManyToManyField("core.Company", blank=True, related_name="+")

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["email"]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email

    def signature_url(self) -> str:
        """The signature as a data: URL for an <img>, or "" when there is none."""
        if not self.signature:
            return ""
        encoded = base64.b64encode(bytes(self.signature)).decode()
        return f"data:{self.signature_type};base64,{encoded}"

    @property
    def display_name(self) -> str:
        return self.full_name or self.email

    @property
    def is_owner(self) -> bool:
        return self.roles.filter(code=OWNER).exists()

    def permission_codes(self) -> frozenset[str]:
        if not self.is_active:
            return frozenset()
        if self.is_owner:
            return permissions.ALL
        codes: set[str] = set()
        for perms in self.roles.values_list("permissions", flat=True):
            codes.update(perms)
        return frozenset(codes & permissions.ALL)

    def can(self, code: str) -> bool:
        return code in self.permission_codes()
