"""Locking customers' API secrets before they are stored.

The key (settings.MYERP_SECRETS_KEY, a Fernet key) lives in the server's
environment, never in the database, so a copy of the database alone does not
reveal a secret. While developing and testing a key is derived from
SECRET_KEY; in production a missing key means secrets cannot be saved."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class SecretsNotSetUp(Exception):
    pass


def _fernet() -> Fernet:
    key = settings.MYERP_SECRETS_KEY
    if key:
        return Fernet(key.encode())
    if settings.DEBUG:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    raise SecretsNotSetUp("Secret storage is not set up on the server yet.")


def lock(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def unlock(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretsNotSetUp("A saved secret cannot be read with the server's key.") from exc
