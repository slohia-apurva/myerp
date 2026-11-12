"""The Disable / Enable button on edit forms saves just `is_active`."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


@pytest.fixture
def owner(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("owner@x.in", full_name="Olive")
        user.roles.set(Role.objects.filter(code="owner"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def flip(client, path):
    off = call(client, "patch", path, {"is_active": False})
    assert off.status_code == 200, off.json()
    assert off.json()["is_active"] is False
    on = call(client, "patch", path, {"is_active": True})
    assert on.status_code == 200, on.json()
    assert on.json()["is_active"] is True


def test_disable_and_enable_each_master(owner, company):
    term = call(owner, "get", "credit-terms/").json()[0]["id"]
    flip(owner, f"credit-terms/{term}/")

    unit = call(owner, "get", "units/").json()[0]["id"]
    flip(owner, f"units/{unit}/")

    item = call(owner, "post", "items/", {"name": "Tea", "stock_unit": unit, "hsn": "0902"})
    assert item.status_code == 201, item.json()
    flip(owner, f"items/{item.json()['id']}/")

    made = call(
        owner, "post", f"companies/{company}/branches/", {"name": "Godown", "state_code": "27"}
    )
    assert made.status_code == 201, made.json()
    flip(owner, f"branches/{made.json()['id']}/")

    detail = call(owner, "get", f"companies/{company}/").json()
    group = next(g["id"] for g in detail["ledger_groups"] if g["name"] == "Indirect Expenses")
    ledger = call(owner, "post", f"companies/{company}/ledgers/", {"name": "Rent", "group": group})
    assert ledger.status_code == 201, ledger.json()
    flip(owner, f"ledgers/{ledger.json()['id']}/")

    role = call(owner, "get", "roles/").json()["roles"][0]["id"]
    other = call(
        owner, "post", "users/", {"email": "new@x.in", "full_name": "New", "roles": [role]}
    )
    assert other.status_code == 201, other.json()
    flip(owner, f"users/{other.json()['id']}/")
