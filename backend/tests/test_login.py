"""Login: password, then an authenticator-app code. No way in with a password alone."""

import re
import time
from io import StringIO

import pyotp
import pytest
from django.core.management import call_command
from django.test import Client

from accounts import crypto
from accounts.models import User
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

PASSWORD = "Turmeric-Harvest-2026"
HOST = "alpha.localhost"


@pytest.fixture
def user(alpha):
    with use_tenant(alpha):
        u = User(username="sidharth", first_name="Sidharth")
        u.set_password(PASSWORD)
        u.save()
    return u


@pytest.fixture
def user_with_totp(alpha, user):
    secret = pyotp.random_base32()
    with use_tenant(alpha):
        user.totp_secret = crypto.encrypt(secret)
        user.totp_confirmed_at = user.date_joined
        user.save()
    return user, secret


def post(client, path, data, host=HOST):
    return client.post(f"/api/auth/{path}", data, content_type="application/json", HTTP_HOST=host)


def reload(tenant, user):
    with use_tenant(tenant):
        return User.objects.get(pk=user.pk)


def test_whoami_needs_login(client, alpha):
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 403


def test_first_login_sets_up_authenticator_then_logs_in(client, alpha, user):
    assert client.get("/api/auth/session/", HTTP_HOST=HOST).json() == {"step": "password"}

    response = post(client, "login/", {"username": "sidharth", "password": PASSWORD})
    assert response.json() == {"step": "totp_setup"}
    # A correct password alone does not log in.
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 403

    setup = post(client, "totp/setup/", {}).json()
    assert setup["uri"].startswith("otpauth://totp/MyERP:")
    assert setup["qr_svg"].startswith("<svg")

    code = pyotp.TOTP(setup["secret"]).now()
    done = post(client, "totp/verify/", {"code": code}).json()
    assert done == {"step": "done", "user": {"username": "sidharth", "name": "Sidharth"}}
    assert client.get("/api/whoami/", HTTP_HOST=HOST).json()["tenant"] == "alpha"

    stored = reload(alpha, user)
    assert stored.has_totp
    assert setup["secret"] not in stored.totp_secret  # encrypted at rest


def test_later_login_asks_for_code(client, alpha, user_with_totp):
    _, secret = user_with_totp
    assert post(client, "login/", {"username": "sidharth", "password": PASSWORD}).json() == {
        "step": "totp"
    }
    # Once 2FA is set up, the secret cannot be shown again.
    assert post(client, "totp/setup/", {}).status_code == 400
    assert post(client, "totp/verify/", {"code": pyotp.TOTP(secret).now()}).status_code == 200


def test_wrong_password_and_unknown_user_look_the_same(client, alpha, user):
    wrong = post(client, "login/", {"username": "sidharth", "password": "nope"})
    unknown = post(client, "login/", {"username": "ghost", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json() == unknown.json()


def test_code_cannot_be_used_twice(client, alpha, user_with_totp):
    _, secret = user_with_totp
    code = pyotp.TOTP(secret).now()
    post(client, "login/", {"username": "sidharth", "password": PASSWORD})
    assert post(client, "totp/verify/", {"code": code}).status_code == 200

    other = Client()
    post(other, "login/", {"username": "sidharth", "password": PASSWORD})
    assert post(other, "totp/verify/", {"code": code}).status_code == 400


def test_code_needs_the_password_step_first(client, alpha, user_with_totp):
    _, secret = user_with_totp
    response = post(client, "totp/verify/", {"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 403


def test_password_step_expires_after_five_minutes(client, alpha, user_with_totp, monkeypatch):
    _, secret = user_with_totp
    post(client, "login/", {"username": "sidharth", "password": PASSWORD})
    later = time.time() + 301
    monkeypatch.setattr("accounts.views.time.time", lambda: later)
    assert post(client, "totp/verify/", {"code": pyotp.TOTP(secret).now()}).status_code == 403


def test_five_wrong_passwords_lock_the_account(client, alpha, user):
    for _ in range(5):
        assert (
            post(client, "login/", {"username": "sidharth", "password": "nope"}).status_code == 400
        )
    # Even the right password is refused while locked.
    response = post(client, "login/", {"username": "sidharth", "password": PASSWORD})
    assert response.status_code == 429


def test_five_wrong_codes_lock_the_account(client, alpha, user_with_totp):
    _, secret = user_with_totp
    post(client, "login/", {"username": "sidharth", "password": PASSWORD})
    statuses = [post(client, "totp/verify/", {"code": "000000"}).status_code for _ in range(5)]
    assert statuses == [400, 400, 400, 400, 429]
    assert reload(alpha, user_with_totp[0]).is_locked()
    assert post(client, "login/", {"username": "sidharth", "password": PASSWORD}).status_code == 429


def test_logout(alpha, logged_in):
    client = logged_in("alpha")
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 200
    assert post(client, "logout/", {}).status_code == 200
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 403


def test_login_to_one_tenant_does_not_open_another(logged_in, beta):
    client = logged_in("alpha")
    assert client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 200
    # Same browser cookie sent to another tenant's address: no such session there.
    assert client.get("/api/whoami/", HTTP_HOST="beta.localhost").status_code == 403


def test_same_username_in_two_tenants_are_different_users(client, alpha, beta, user):
    with use_tenant(beta):
        other = User(username="sidharth")
        other.set_password("Different-Password-99")
        other.save()
    # Alpha's password does not work at beta.
    response = post(
        client, "login/", {"username": "sidharth", "password": PASSWORD}, "beta.localhost"
    )
    assert response.status_code == 400


def test_login_needs_csrf_token(alpha, user):
    client = Client(enforce_csrf_checks=True)
    assert post(client, "login/", {"username": "sidharth", "password": PASSWORD}).status_code == 403

    client.get("/api/auth/session/", HTTP_HOST=HOST)
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/api/auth/login/",
        {"username": "sidharth", "password": PASSWORD},
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200


def test_create_tenant_user_link_sets_password_once(client, alpha):
    out = StringIO()
    call_command("create_tenant_user", "alpha", "newuser", "--first-name", "New", stdout=out)
    uid, token = re.search(r"#set-password/([^/]+)/(\S+)", out.getvalue()).groups()

    # No password yet: cannot log in.
    assert post(client, "login/", {"username": "newuser", "password": ""}).status_code == 400

    weak = post(client, "password-setup/", {"uid": uid, "token": token, "password": "12345"})
    assert weak.status_code == 400

    ok = post(client, "password-setup/", {"uid": uid, "token": token, "password": PASSWORD})
    assert ok.json() == {"username": "newuser"}
    again = post(client, "password-setup/", {"uid": uid, "token": token, "password": PASSWORD})
    assert again.status_code == 400

    assert post(client, "login/", {"username": "newuser", "password": PASSWORD}).json() == {
        "step": "totp_setup"
    }


def test_create_tenant_user_reset_clears_two_factor(alpha, user_with_totp):
    user, _ = user_with_totp
    call_command("create_tenant_user", "alpha", "sidharth", "--reset", stdout=StringIO())
    stored = reload(alpha, user)
    assert not stored.has_totp
    assert not stored.has_usable_password()
