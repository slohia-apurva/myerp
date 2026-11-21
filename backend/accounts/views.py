"""Sign in with Google.

A person can sign in only if a tenant admin has added their email address to
this tenant, and only with a Google account whose email Google has verified.
Google handles the password and 2-step verification.
"""

from django.conf import settings
from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import google
from accounts.models import User
from core.central import is_platform_admin
from tenancy.context import current_tenant

FAILED = "Google sign-in did not work. Please try again."
NOT_SET_UP = "Google sign-in is not set up for this address yet."


def _migration_tools() -> bool:
    """Whether Admin > Migration Tools is on for this customer."""
    tenant = current_tenant()
    return bool(tenant and tenant.migration_tools)


def session_state(request) -> dict:
    """Whether someone is signed in, and what the sign-in screen needs."""
    user = request.user
    if user.is_authenticated:
        return {
            "signed_in": True,
            "user": {
                "email": user.email,
                "name": user.display_name,
                "is_owner": user.is_owner,
                "is_platform_admin": is_platform_admin(user),
            },
            "permissions": sorted(user.permission_codes()),
            "migration_tools": _migration_tools(),
        }
    return {"signed_in": False, "google_client_id": settings.MYERP_GOOGLE_CLIENT_ID}


@method_decorator(csrf_protect, name="dispatch")
class AuthView(APIView):
    """Sign-in endpoints work before sign-in, but still require the CSRF token."""

    permission_classes = [AllowAny]


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(AuthView):
    def get(self, request):
        return Response(session_state(request))


class GoogleSignInView(AuthView):
    def post(self, request):
        client_id = settings.MYERP_GOOGLE_CLIENT_ID
        if not client_id:
            return Response({"detail": NOT_SET_UP}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            claims = google.verify_credential(str(request.data.get("credential", "")), client_id)
        except ValueError:
            return Response({"detail": FAILED}, status=status.HTTP_400_BAD_REQUEST)
        if not claims.get("email_verified") or not claims.get("email"):
            return Response({"detail": FAILED}, status=status.HTTP_400_BAD_REQUEST)

        email = claims["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user is None or (user.google_sub and user.google_sub != claims["sub"]):
            return Response(
                {
                    "detail": f"{email} does not have access to {request.tenant.name}. "
                    "Ask your MyERP admin to add you."
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if not user.google_sub:
            user.google_sub = claims["sub"]
            user.save(update_fields=["google_sub"])
        if not user.full_name and claims.get("name"):
            user.full_name = claims["name"][:150]
            user.save(update_fields=["full_name"])

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(session_state(request))


class SignOutView(AuthView):
    def post(self, request):
        logout(request)
        return Response(session_state(request))
