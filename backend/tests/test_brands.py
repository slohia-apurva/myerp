"""Brands: the group's shared list, and an item's brand."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HOST = "alpha.localhost"


def _client(alpha, email, role):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=email.split("@")[0])
        user.roles.set(Role.objects.filter(code=role))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def accountant(alpha):
    return _client(alpha, "accounts@x.in", "accountant")


@pytest.fixture
def viewer(alpha):
    return _client(alpha, "view@x.in", "viewer")


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def kg(client):
    return next(u["id"] for u in call(client, "get", "units/").json() if u["name"] == "Kilogram")


def test_add_rename_and_disable_a_brand(accountant, company):
    made = call(accountant, "post", "brands/", {"name": "Apurvam", "notes": "House brand"})
    assert made.status_code == 201, made.json()
    pk = made.json()["id"]
    renamed = call(accountant, "patch", f"brands/{pk}/", {"name": "Apurvam Organics"})
    assert renamed.json()["name"] == "Apurvam Organics"
    off = call(accountant, "patch", f"brands/{pk}/", {"is_active": False})
    assert off.json()["is_active"] is False


def test_brand_names_are_unique_whatever_the_case(accountant, company):
    call(accountant, "post", "brands/", {"name": "Apurvam"})
    bad = call(accountant, "post", "brands/", {"name": "APURVAM"})
    assert bad.status_code == 400
    assert "already a brand" in str(bad.json())


def test_an_item_has_a_brand_and_counts_show(accountant, company):
    brand = call(accountant, "post", "brands/", {"name": "Apurvam"}).json()
    made = call(
        accountant,
        "post",
        "items/",
        {
            "name": "Turmeric powder",
            "stock_unit": kg(accountant),
            "brand": brand["id"],
            "hsn": "0902",
        },
    )
    assert made.status_code == 201, made.json()
    assert made.json()["brand_name"] == "Apurvam"
    rows = call(accountant, "get", "brands/").json()
    assert rows[0]["item_count"] == 1
    cleared = call(accountant, "patch", f"items/{made.json()['id']}/", {"brand": None})
    # Brand is required (Sidharth, 2026-11-13).
    assert cleared.status_code == 400 and "brand" in cleared.json()


def test_a_disabled_brand_takes_no_new_items(accountant, company):
    brand = call(accountant, "post", "brands/", {"name": "Old brand"}).json()
    call(accountant, "patch", f"brands/{brand['id']}/", {"is_active": False})
    bad = call(
        accountant,
        "post",
        "items/",
        {"name": "Cumin", "stock_unit": kg(accountant), "brand": brand["id"], "hsn": "0902"},
    )
    assert bad.status_code == 400
    assert "disabled" in str(bad.json())


def test_viewers_read_but_cannot_change(viewer, accountant, company):
    call(accountant, "post", "brands/", {"name": "Apurvam"})
    assert call(viewer, "get", "brands/").status_code == 200
    assert call(viewer, "post", "brands/", {"name": "Nope"}).status_code == 403
