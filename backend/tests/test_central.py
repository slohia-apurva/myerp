"""The central admin screen: platform admins only, lists the central tables."""

import pytest
from django.test import Client

from accounts.models import User
from tenancy.context import use_tenant
from tenancy.models import HsnCode

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def _client(alpha, email, owner=False):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name="Pat")
        if owner:
            from accounts.models import Role

            user.roles.set(Role.objects.filter(code="owner"))
        client = Client()
        client.force_login(user)
    return client


def test_platform_admin_sees_tables_and_tenants(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "Boss@x.in, other@x.in"
    HsnCode.objects.create(hsn_code="0910", description="Ginger, turmeric")
    client = _client(alpha, "boss@x.in")
    resp = client.get("/api/v1/central/", HTTP_HOST=HOST)
    assert resp.status_code == 200
    tables = {t["key"]: t for t in resp.json()["tables"]}
    assert tables["hsn"]["count"] == HsnCode.objects.count() >= 1
    assert tables["tenants"]["count"] >= 1
    assert "alpha" in [t["slug"] for t in resp.json()["tenants"]]


def test_session_says_who_is_platform_admin(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    assert (
        _client(alpha, "boss@x.in")
        .get("/api/auth/session/", HTTP_HOST=HOST)
        .json()["user"]["is_platform_admin"]
    )
    assert (
        not _client(alpha, "pat@x.in")
        .get("/api/auth/session/", HTTP_HOST=HOST)
        .json()["user"]["is_platform_admin"]
    )


def test_owner_and_others_are_refused(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = "boss@x.in"
    assert (
        _client(alpha, "own@x.in", owner=True).get("/api/v1/central/", HTTP_HOST=HOST).status_code
        == 403
    )


def test_nobody_is_admin_when_the_setting_is_empty(alpha, settings):
    settings.MYERP_PLATFORM_ADMINS = ""
    assert _client(alpha, "boss@x.in").get("/api/v1/central/", HTTP_HOST=HOST).status_code == 403
