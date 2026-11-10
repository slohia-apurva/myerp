"""GSTIN lookup through a GST provider (not connected yet)."""

import pytest
from django.test import Client, override_settings

from accounts.models import Role, User
from core.india import gstin_check_char
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def gstin(state="27", pan="AAPFU0939F"):
    first14 = f"{state}{pan}1Z"
    return first14 + gstin_check_char(first14)


def fake_provider(number):
    if number == gstin("29"):
        return {}
    return {
        "legal_name": "FRESH MART PRIVATE LIMITED",
        "trade_name": "Fresh Mart",
        "pincode": "411004",
    }


@pytest.fixture
def accountant(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("accounts@x.in", full_name="Asha")
        user.roles.set(Role.objects.filter(code="accountant"))
        client = Client()
        client.force_login(user)
    return client


def lookup(client, number):
    return client.get(f"/api/v1/gstin-lookup/?gstin={number}", HTTP_HOST=HOST)


def test_lookup_says_when_it_is_not_set_up(accountant):
    reply = lookup(accountant, gstin())
    assert reply.status_code == 503
    assert "not set up" in reply.json()["detail"]


def test_lookup_checks_the_number_first(accountant):
    bad = lookup(accountant, gstin()[:14] + "0")
    assert bad.status_code == 400
    assert "gstin" in bad.json()


@override_settings(GSTIN_LOOKUP_PROVIDER="tests.test_gstin_lookup.fake_provider")
def test_lookup_returns_the_provider_details(accountant):
    reply = lookup(accountant, gstin())
    assert reply.status_code == 200, reply.json()
    body = reply.json()
    assert body["legal_name"] == "FRESH MART PRIVATE LIMITED"
    assert (body["state_code"], body["pan"]) == ("27", "AAPFU0939F")
    missing = lookup(accountant, gstin("29"))
    assert missing.status_code == 400
