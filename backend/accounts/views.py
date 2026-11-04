"""Login in two steps: password, then a code from an authenticator app.

Every user must set up the authenticator app on first login; there is no way
to finish logging in with a password alone. Five wrong passwords or codes lock
the account for 15 minutes.
"""

import time

from django.contrib.auth import login, logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import totp
from accounts.models import User

PENDING_USER = "myerp_pending_user"
PENDING_SINCE = "myerp_pending_since"
# Time allowed between a correct password and the authenticator code.
PENDING_SECONDS = 5 * 60

WRONG_LOGIN = "Wrong username or password."
WRONG_CODE = "That code is not right. Use the current 6-digit code from the app."
LOCKED = "Too many failed attempts. Try again in 15 minutes."
EXPIRED = "Please log in again."


def _pending_user(request) -> User | None:
    user_id = request.session.get(PENDING_USER)
    since = request.session.get(PENDING_SINCE, 0)
    if user_id is None or time.time() - since > PENDING_SECONDS:
        return None
    return User.objects.filter(pk=user_id, is_active=True).first()


def _clear_pending(request) -> None:
    request.session.pop(PENDING_USER, None)
    request.session.pop(PENDING_SINCE, None)


def session_state(request) -> dict:
    """What the login screen should show next."""
    user = request.user
    if user.is_authenticated:
        return {
            "step": "done",
            "user": {"username": user.username, "name": user.get_full_name() or user.username},
        }
    pending = _pending_user(request)
    if pending is not None:
        return {"step": "totp" if pending.has_totp else "totp_setup"}
    return {"step": "password"}


@method_decorator(csrf_protect, name="dispatch")
class AuthView(APIView):
    """Login endpoints work before login, but still require the CSRF token."""

    permission_classes = [AllowAny]


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(AuthView):
    def get(self, request):
        return Response(session_state(request))


class PasswordView(AuthView):
    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        user = User.objects.filter(username=username).first() if username else None

        if user is not None and user.is_locked():
            return Response({"detail": LOCKED}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if user is None or not user.is_active or not user.has_usable_password():
            make_password(password)  # same work as a real check, so timing reveals nothing
            return Response({"detail": WRONG_LOGIN}, status=status.HTTP_400_BAD_REQUEST)
        if not user.check_password(password):
            user.record_failure()
            return Response({"detail": WRONG_LOGIN}, status=status.HTTP_400_BAD_REQUEST)

        request.session.cycle_key()
        request.session[PENDING_USER] = user.pk
        request.session[PENDING_SINCE] = time.time()
        return Response(session_state(request))


class TotpSetupView(AuthView):
    """Shows a new secret as a QR code for a user who has not set up 2FA."""

    def post(self, request):
        user = _pending_user(request)
        if user is None:
            return Response({"detail": EXPIRED}, status=status.HTTP_403_FORBIDDEN)
        if user.has_totp:
            return Response(
                {"detail": "Two-factor is already set up."}, status=status.HTTP_400_BAD_REQUEST
            )
        secret = totp.start_setup(user)
        uri = totp.provisioning_uri(user, secret, request.tenant.name)
        return Response({"secret": secret, "uri": uri, "qr_svg": totp.qr_svg(uri)})


class TotpVerifyView(AuthView):
    def post(self, request):
        user = _pending_user(request)
        if user is None:
            return Response({"detail": EXPIRED}, status=status.HTTP_403_FORBIDDEN)
        if user.is_locked():
            _clear_pending(request)
            return Response({"detail": LOCKED}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if not totp.verify(user, str(request.data.get("code", ""))):
            user.record_failure()
            if user.is_locked():
                _clear_pending(request)
                return Response({"detail": LOCKED}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response({"detail": WRONG_CODE}, status=status.HTTP_400_BAD_REQUEST)

        if not user.has_totp:
            user.totp_confirmed_at = timezone.now()
            user.save(update_fields=["totp_confirmed_at"])
        user.clear_failures()
        _clear_pending(request)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(session_state(request))


class LogoutView(AuthView):
    def post(self, request):
        logout(request)
        return Response({"step": "password"})


class PasswordSetupView(AuthView):
    """Sets a password from a one-time link made by `create_tenant_user`.

    The link stops working once used, because the token covers the password.
    """

    def post(self, request):
        user = _user_from_uid(str(request.data.get("uid", "")))
        token = str(request.data.get("token", ""))
        if user is None or not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "This link is invalid or has expired. Ask for a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        password = str(request.data.get("password", ""))
        try:
            validate_password(password, user)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.failed_logins = 0
        user.locked_until = None
        user.save()
        return Response({"username": user.username})


def _user_from_uid(uid: str) -> User | None:
    try:
        pk = int(force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, OverflowError):
        return None
    return User.objects.filter(pk=pk, is_active=True).first()
