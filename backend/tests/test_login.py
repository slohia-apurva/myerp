"""Sign in with Google: only people a tenant admin added, only at that tenant."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from accounts.models import User
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"
CLIENT_ID = "test-client.apps.googleusercontent.com"
SID = {"sub": "1001", "email": "Sidharth@Apurva.org.in", "email_verified": True, "name": "Sidharth"}


@pytest.fixture(autouse=True)
def google(settings, monkeypatch):
    """Stand-in for Google: a credential is just the key of a claims dict."""
    settings.MYERP_GOOGLE_CLIENT_ID = CLIENT_ID
    tokens: dict[str, dict] = {}

    def verify(credential, client_id):
        assert client_id == CLIENT_ID
        if credential not in tokens:
            raise ValueError("bad token")
        return tokens[credential]

    monkeypatch.setattr("accounts.google.verify_credential", verify)
    return tokens


@pytest.fixture
def sidharth(alpha):
    with use_tenant(alpha):
        return User.objects.create_user("sidharth@apurva.org.in")


def sign_in(client, credential, host=HOST):
    return client.post(
        "/api/auth/google/",
        {"credential": credential},
        content_type="application/json",
        HTTP_HOST=host,
    )


def test_signed_out_session_offers_google(client, alpha):
    assert client.get("/api/auth/session/", HTTP_HOST=HOST).json() == {
        "signed_in": False,
        "google_client_id": CLIENT_ID,
    }
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 403


def test_added_person_signs_in_with_google(client, alpha, sidharth, google):
    google["tok"] = SID
    response = sign_in(client, "tok")
    assert response.json() == {
        "signed_in": True,
        "user": {"email": "sidharth@apurva.org.in", "name": "Sidharth", "is_owner": False},
        "permissions": [],
    }
    assert client.get("/api/whoami/", HTTP_HOST=HOST).json()["tenant"] == "alpha"
    with use_tenant(alpha):
        stored = User.objects.get(pk=sidharth.pk)
    assert stored.google_sub == "1001"
    assert not stored.has_usable_password()


def test_person_not_added_is_refused(client, alpha, google):
    google["tok"] = SID
    response = sign_in(client, "tok")
    assert response.status_code == 403
    assert "Ask your MyERP admin" in response.json()["detail"]
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 403


def test_deactivated_person_is_refused(client, alpha, sidharth, google):
    call_command(
        "create_tenant_user", "alpha", "sidharth@apurva.org.in", "--deactivate", stdout=StringIO()
    )
    google["tok"] = SID
    assert sign_in(client, "tok").status_code == 403


def test_unverified_email_is_refused(client, alpha, sidharth, google):
    google["tok"] = {**SID, "email_verified": False}
    assert sign_in(client, "tok").status_code == 400


def test_invalid_credential_is_refused(client, alpha, sidharth):
    assert sign_in(client, "forged").status_code == 400


def test_email_moved_to_another_google_account_is_refused(client, alpha, sidharth, google):
    google["first"] = SID
    assert sign_in(client, "first").status_code == 200
    google["other"] = {**SID, "sub": "2002"}
    assert sign_in(Client(), "other").status_code == 403


def test_added_at_one_tenant_only(client, alpha, beta, sidharth, google):
    google["tok"] = SID
    assert sign_in(client, "tok", host="beta.localhost").status_code == 403


def test_sign_in_at_one_tenant_does_not_open_another(logged_in, beta):
    client = logged_in("alpha")
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 200
    # Same browser cookie sent to another tenant's address: no such session there.
    assert client.get("/api/whoami/", HTTP_HOST="beta.localhost").status_code == 403


def test_sign_out(alpha, logged_in):
    client = logged_in("alpha")
    response = client.post("/api/auth/logout/", HTTP_HOST=HOST)
    assert response.json()["signed_in"] is False
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 403


def test_not_configured_says_so(client, alpha, settings):
    settings.MYERP_GOOGLE_CLIENT_ID = ""
    assert sign_in(client, "tok").status_code == 503


def test_sign_in_needs_csrf_token(alpha, sidharth, google):
    google["tok"] = SID
    client = Client(enforce_csrf_checks=True)
    assert sign_in(client, "tok").status_code == 403

    client.get("/api/auth/session/", HTTP_HOST=HOST)
    response = client.post(
        "/api/auth/google/",
        {"credential": "tok"},
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert response.status_code == 200


def test_create_tenant_user_adds_and_restores(alpha):
    out = StringIO()
    call_command(
        "create_tenant_user", "alpha", " New.Person@Example.com ", "--name", "New", stdout=out
    )
    assert "Added new.person@example.com" in out.getvalue()
    call_command(
        "create_tenant_user", "alpha", "new.person@example.com", "--deactivate", stdout=out
    )
    call_command("create_tenant_user", "alpha", "new.person@example.com", stdout=out)
    with use_tenant(alpha):
        user = User.objects.get(email="new.person@example.com")
    assert user.is_active and user.full_name == "New"


def test_google_popup_can_report_back(client, tenants):
    response = client.get("/api/health/", HTTP_HOST="localhost")
    assert response["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
