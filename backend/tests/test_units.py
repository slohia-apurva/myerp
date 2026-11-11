"""Units of measure: the group's shared list."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


@pytest.fixture
def accountant(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("accounts@x.in", full_name="Asha")
        user.roles.set(Role.objects.filter(code="accountant"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def viewer(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("view@x.in", full_name="Vee")
        user.roles.set(Role.objects.filter(code="viewer"))
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


def units(client):
    return {u["name"]: u for u in call(client, "get", "units/").json()}


def test_the_group_starts_with_the_usual_units(accountant, company):
    have = units(accountant)
    assert {"Packet", "Carton", "Kilogram", "Nos"} <= set(have)
    assert have["Carton"]["whole_numbers"] is True
    assert have["Kilogram"]["whole_numbers"] is False


def test_add_change_and_disable_a_unit(accountant, company):
    made = call(
        accountant,
        "post",
        "units/",
        {"name": "Drum", "short_name": "drm", "gst_code": "DRM", "whole_numbers": True},
    )
    assert made.status_code == 201, made.json()
    unit = made.json()
    assert unit["is_active"] is True

    changed = call(accountant, "patch", f"units/{unit['id']}/", {"is_active": False})
    assert changed.status_code == 200
    assert changed.json()["is_active"] is False

    entries = call(accountant, "get", f"audit/?type=unit&id={unit['id']}").json()["entries"]
    assert [e["action"] for e in entries] == ["update", "create"]
    added = {c["label"]: c["new"] for c in entries[1]["changes"]}
    assert added["Whole numbers only"] == "Yes"
    assert added["Short name"] == "drm"


def test_unit_checks(accountant, company):
    def error(**data):
        response = call(
            accountant,
            "post",
            "units/",
            {"name": "X", "short_name": "x", "gst_code": "OTH", **data},
        )
        assert response.status_code == 400, response.json()
        return response.json()

    assert "name" in error(name="packet")  # same name, any case
    assert "short_name" in error(name="Something else", short_name="KG")
    assert "name" in error(name="  ")
    assert "short_name" in error(short_name="")
    assert "gst_code" in error(gst_code="XYZ")  # not an official code
    assert "gst_code" in error(gst_code="")  # required


def test_starting_units_carry_gst_codes_and_the_list_is_served(accountant, company):
    have = units(accountant)
    assert have["Carton"]["gst_code"] == "CTN"
    assert have["Litre"]["gst_code"] == "LTR"
    assert have["Pallet"]["gst_code"] == "OTH"
    codes = {c["code"] for c in call(accountant, "get", "units/gst-codes/").json()}
    assert {"NOS", "KGS", "LTR", "OTH"} <= codes
    assert all(u["gst_code"] in codes for u in have.values())


def test_gst_code_can_be_changed_and_is_logged(accountant, company):
    carton = units(accountant)["Carton"]
    done = call(accountant, "patch", f"units/{carton['id']}/", {"gst_code": "BOX"})
    assert done.status_code == 200 and done.json()["gst_code"] == "BOX"
    entries = call(accountant, "get", f"audit/?type=unit&id={carton['id']}").json()["entries"]
    assert any(c["label"] == "GST unit code" for c in entries[0]["changes"])


def test_viewer_may_read_but_not_change(viewer, accountant, company):
    assert call(viewer, "get", "units/").status_code == 200
    denied = call(viewer, "post", "units/", {"name": "Drum", "short_name": "drm"})
    assert denied.status_code == 403
