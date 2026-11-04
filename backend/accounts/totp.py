"""Authenticator-app codes (RFC 6238: 6 digits, 30 seconds)."""

import hmac
import time

import pyotp
import segno

from accounts import crypto
from accounts.models import User

ISSUER = "MyERP"
STEP_SECONDS = 30
# Accept the previous and next code too, for phones whose clock is a little off.
DRIFT_STEPS = 1


def start_setup(user: User) -> str:
    """Give the user a fresh secret (not active until confirmed). Returns it."""
    secret = pyotp.random_base32()
    user.totp_secret = crypto.encrypt(secret)
    user.totp_confirmed_at = None
    user.totp_last_step = 0
    user.save(update_fields=["totp_secret", "totp_confirmed_at", "totp_last_step"])
    return secret


def provisioning_uri(user: User, secret: str, tenant_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=f"{user.username} ({tenant_name})", issuer_name=ISSUER
    )


def qr_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_inline(scale=5, border=2)


def verify(user: User, code: str, now: float | None = None) -> bool:
    """True if code is valid and not used before. Records the step used."""
    code = "".join(code.split())
    if not user.totp_secret or not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(crypto.decrypt(user.totp_secret))
    now = time.time() if now is None else now
    for offset in range(-DRIFT_STEPS, DRIFT_STEPS + 1):
        moment = now + offset * STEP_SECONDS
        if hmac.compare_digest(totp.at(moment), code):
            step = int(moment // STEP_SECONDS)
            if step <= user.totp_last_step:
                return False
            user.totp_last_step = step
            user.save(update_fields=["totp_last_step"])
            return True
    return False
