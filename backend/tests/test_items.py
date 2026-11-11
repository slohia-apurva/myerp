"""Items: the shared catalogue and each item's chain of units."""

from decimal import Decimal

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


@pytest.fixture
def unit(accountant, company):
    ids = {u["name"]: u["id"] for u in call(accountant, "get", "units/").json()}
    return lambda name: ids[name]


def chain(unit):
    return [
        {
            "unit": unit("Packet"),
            "length_cm": "18",
            "breadth_cm": "12",
            "height_cm": "5",
            "net_kg": "0.5",
            "gross_kg": "0.52",
            "barcode": "8901234500011",
            "used_for": ["stock"],
        },
        {"unit": unit("Inner box"), "contains_qty": "6", "contains_unit": unit("Packet")},
        {
            "unit": unit("Carton"),
            "contains_qty": "4",
            "contains_unit": unit("Inner box"),
            "length_cm": "54",
            "breadth_cm": "40",
            "height_cm": "34",
            "used_for": ["purchase"],
        },
        {"unit": unit("Pallet"), "contains_qty": "40", "contains_unit": unit("Carton")},
    ]


def make(client, unit, **data):
    body = {
        "name": "Jaggery Powder 500 g",
        "stock_unit": unit("Packet"),
        "units": chain(unit),
        **data,
    }
    return call(client, "post", "items/", body)


def test_item_with_a_chain_of_units(accountant, unit):
    made = make(accountant, unit, hsn="1701", shelf_life_days=365, batch_tracked=True)
    assert made.status_code == 201, made.json()
    item = made.json()
    assert item["item_number"] == "ITEM-00001"
    rows = {r["unit_name"]: r for r in item["units"]}
    assert Decimal(rows["Packet"]["factor"]) == 1
    assert Decimal(rows["Inner box"]["factor"]) == 6
    assert Decimal(rows["Carton"]["factor"]) == 24
    assert Decimal(rows["Pallet"]["factor"]) == 960
    assert rows["Carton"]["volume_m3"] == "0.07344"
    assert rows["Packet"]["volume_m3"] == "0.00108"
    assert rows["Pallet"]["volume_m3"] is None
    assert item["warnings"] == ["Size missing for: Inner box, Pallet."]
    # numbers keep counting
    second = make(accountant, unit, name="Turmeric", units=[])
    assert second.json()["item_number"] == "ITEM-00002"


def test_the_stock_unit_always_has_a_row(accountant, unit):
    made = call(
        accountant, "post", "items/", {"name": "Bag of rice", "stock_unit": unit("Kilogram")}
    )
    assert made.status_code == 201, made.json()
    assert [(r["unit_name"], r["factor"]) for r in made.json()["units"]] == [
        ("Kilogram", "1.000000")
    ]


def test_change_keeps_units_unless_sent(accountant, unit):
    item = make(accountant, unit).json()
    changed = call(accountant, "patch", f"items/{item['id']}/", {"hsn": "1701", "is_active": False})
    assert changed.status_code == 200, changed.json()
    assert changed.json()["is_active"] is False
    assert len(changed.json()["units"]) == 4

    fewer = call(accountant, "patch", f"items/{item['id']}/", {"units": chain(unit)[:2]})
    assert fewer.status_code == 200, fewer.json()
    assert [r["unit_name"] for r in fewer.json()["units"]] == ["Packet", "Inner box"]

    entries = call(accountant, "get", f"audit/?type=item&id={item['id']}").json()["entries"]
    assert [e["action"] for e in entries] == ["update", "update", "create"]
    added = {c["label"]: c["new"] for c in entries[2]["changes"]}
    assert added["Item number"] == "ITEM-00001"
    assert "Carton = 4 Inner box (24 Packet)" in added["Units"]


def test_chain_checks(accountant, unit):
    def error(units, **data):
        r = make(accountant, unit, units=units, **data)
        assert r.status_code == 400, r.json()
        return r.json()

    packet = {"unit": unit("Packet")}
    assert "units" in error([packet, {"unit": unit("Packet")}])  # twice
    assert "units" in error([packet, {"unit": unit("Carton")}])  # says nothing
    assert "units" in error(
        [packet, {"unit": unit("Carton"), "contains_qty": "0", "contains_unit": unit("Packet")}]
    )
    assert "units" in error(
        [packet, {"unit": unit("Carton"), "contains_qty": "4", "contains_unit": unit("Pallet")}]
    )  # Pallet is not listed
    assert "units" in error(
        [packet, {"unit": unit("Carton"), "contains_qty": "4", "contains_unit": unit("Carton")}]
    )
    assert "units" in error(
        [
            packet,
            {"unit": unit("Carton"), "contains_qty": "4", "contains_unit": unit("Pallet")},
            {"unit": unit("Pallet"), "contains_qty": "4", "contains_unit": unit("Carton")},
        ]
    )  # a circle
    assert "units" in error(
        [{"unit": unit("Packet"), "contains_qty": "2", "contains_unit": unit("Nos")}]
    )  # the stock unit contains nothing


def test_item_checks(accountant, unit):
    assert make(accountant, unit).status_code == 201
    clash = make(accountant, unit, name="jaggery powder 500 G", units=[])
    assert clash.status_code == 400 and "name" in clash.json()
    assert "hsn" in make(accountant, unit, name="X", units=[], hsn="17A1").json()
    # the same barcode on another item
    again = make(accountant, unit, name="Other", units=chain(unit)[:1])
    assert again.status_code == 400 and "barcode" in str(again.json())


def test_disabled_units_cannot_be_newly_added(accountant, unit):
    call(accountant, "patch", f"units/{unit('Pallet')}/", {"is_active": False})
    r = make(
        accountant,
        unit,
        name="New",
        units=[
            {"unit": unit("Packet")},
            {"unit": unit("Pallet"), "contains_qty": "5", "contains_unit": unit("Packet")},
        ],
    )
    assert r.status_code == 400 and "disabled" in str(r.json())


def test_changing_the_stock_unit_must_keep_the_chain_whole(accountant, unit):
    item = make(accountant, unit).json()
    r = call(accountant, "patch", f"items/{item['id']}/", {"stock_unit": unit("Carton")})
    # Carton becomes the stock unit, but Packet no longer chains to it.
    assert r.status_code == 400, r.json()


def test_viewer_may_read_but_not_change(viewer, accountant, unit):
    make(accountant, unit)
    assert len(call(viewer, "get", "items/").json()) == 1
    assert (
        call(viewer, "post", "items/", {"name": "X", "stock_unit": unit("Nos")}).status_code == 403
    )
