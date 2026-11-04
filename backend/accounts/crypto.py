"""Encrypts small secrets (TOTP keys) stored in tenant databases.

The key is derived from DJANGO_SECRET_KEY, so a copy of the database alone does
not reveal anyone's authenticator secret. Rotating DJANGO_SECRET_KEY makes
existing secrets unreadable: every user then sets up 2FA again.
"""

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"myerp-field-encryption:" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
