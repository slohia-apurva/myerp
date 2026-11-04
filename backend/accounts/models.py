"""Users live in each tenant's own database, so a person added to one tenant
cannot sign in to another (design rule 16).

People are known by email address. They sign in with Google; MyERP keeps no
passwords (see docs/decisions/0007-login-with-google.md).
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


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
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    # Google's permanent account id, recorded at first sign-in. If the email
    # address is later given to a different Google account, it cannot sign in.
    google_sub = models.CharField(max_length=255, blank=True, default="")

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

    @property
    def display_name(self) -> str:
        return self.full_name or self.email
