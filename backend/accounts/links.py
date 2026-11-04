from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import User


def password_setup_path(user: User) -> str:
    """App path for setting a password. The token is after '#', so browsers
    never send it to the server and it stays out of request logs."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"/#set-password/{uid}/{token}"
