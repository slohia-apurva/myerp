"""Users live in each tenant's own database, so a user of one tenant cannot
log in to another (design rule 16)."""

from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)


class User(AbstractUser):
    # Authenticator-app (TOTP) secret, encrypted with accounts.crypto.
    totp_secret = models.TextField(blank=True, default="")
    totp_confirmed_at = models.DateTimeField(null=True, blank=True)
    # Last 30-second step accepted, so a code cannot be used twice.
    totp_last_step = models.BigIntegerField(default=0)

    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    @property
    def has_totp(self) -> bool:
        return self.totp_confirmed_at is not None

    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > timezone.now()

    def record_failure(self) -> None:
        self.failed_logins += 1
        if self.failed_logins >= MAX_FAILED_LOGINS:
            self.locked_until = timezone.now() + LOCKOUT
            self.failed_logins = 0
        self.save(update_fields=["failed_logins", "locked_until"])

    def clear_failures(self) -> None:
        if self.failed_logins or self.locked_until:
            self.failed_logins = 0
            self.locked_until = None
            self.save(update_fields=["failed_logins", "locked_until"])

    def reset_two_factor(self) -> None:
        self.totp_secret = ""
        self.totp_confirmed_at = None
        self.totp_last_step = 0
