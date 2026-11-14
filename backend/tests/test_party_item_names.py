"""What a customer or supplier calls our items (kept on the item, shown on Products)."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from core.models import Brand, Item, ItemGroup, Party, Unit
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

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
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


@pytest.fixture
def world(alpha):
    """Two items, a customer and a supplier."""
    with use_tenant(alpha):
        unit = Unit.objects.get(name="Packet")
        more = {
            "stock_unit": unit,
            "hsn": "0902",
            "item_group": ItemGroup.objects.get_or_create(name="General")[0],
            "brand": Brand.objects.get_or_create(name="General brand")[0],
        }
        a = Item.objects.create(item_number="ITEM-91", name="Tea A", **more)
        b = Item.objects.create(item_number="ITEM-92", name="Tea B", **more)
        cust = Party.objects.create(name="Spice Route", customer_number="CUST-1")
        vend = Party.objects.create(name="Darjeeling Estates", vendor_number="VEND-1")
        return {"a": a.pk, "b": b.pk, "cust": cust.pk, "vend": vend.pk}


def put(client, item, rows):
    return call(client, "patch", f"items/{item}/", {"party_names": rows})


def test_the_item_keeps_what_each_party_calls_it(accountant, world):
    rows = [
        {"party": world["cust"], "name": "CTC Dust 1", "code": "SRT-1"},
        {"party": world["vend"], "name": "", "code": "DE/A"},
    ]
    saved = put(accountant, world["a"], rows)
    assert saved.status_code == 200, saved.json()
    got = {r["party_name"]: r for r in saved.json()["party_names"]}
    assert got["Spice Route"]["party_kind"] == "Customer"
    assert got["Darjeeling Estates"]["party_kind"] == "Supplier"
    assert got["Spice Route"]["code"] == "SRT-1"
    # Sending the list again replaces it; an empty list clears it.
    assert put(accountant, world["a"], rows[:1]).json()["party_names"][0]["name"] == "CTC Dust 1"
    assert len(put(accountant, world["a"], rows[:1]).json()["party_names"]) == 1
    assert put(accountant, world["a"], []).json()["party_names"] == []


def test_a_row_needs_a_name_or_a_code_and_a_party_is_listed_once(accountant, world):
    empty = put(accountant, world["a"], [{"party": world["cust"], "name": " ", "code": ""}])
    assert empty.status_code == 400 and "name, their item code" in str(empty.json())
    twice = put(
        accountant,
        world["a"],
        [{"party": world["cust"], "name": "X"}, {"party": world["cust"], "name": "Y"}],
    )
    assert twice.status_code == 400 and "listed twice" in str(twice.json())


def test_a_partys_code_belongs_to_one_item(accountant, world):
    assert (
        put(accountant, world["a"], [{"party": world["cust"], "code": "SRT-1"}]).status_code == 200
    )
    clash = put(accountant, world["b"], [{"party": world["cust"], "code": "srt-1"}])
    assert clash.status_code == 400 and 'already on the item "Tea A"' in str(clash.json())
    # Another party may use the same code; the item itself may keep its own.
    assert (
        put(accountant, world["b"], [{"party": world["vend"], "code": "SRT-1"}]).status_code == 200
    )
    assert (
        put(accountant, world["a"], [{"party": world["cust"], "code": "SRT-1"}]).status_code == 200
    )


def test_the_partys_products_tab_shows_their_names_read_only(accountant, company, world):
    debtors = next(
        g["id"]
        for g in call(accountant, "get", f"companies/{company}/").json()["ledger_groups"]
        if g["name"] == "Sundry Debtors"
    )
    ledger = call(
        accountant,
        "post",
        f"companies/{company}/ledgers/",
        {
            "name": "Tea Traders",
            "group": debtors,
            "party": {"gst_type": "unregistered", "state_code": "27"},
        },
    )
    assert ledger.status_code == 201, ledger.json()
    party = ledger.json()["party"]["id"]
    named = put(accountant, world["a"], [{"party": party, "name": "CTC Dust 1", "code": "SRT-1"}])
    assert named.json()["party_names"][0]["party_kind"] == "Customer"
    saved = call(
        accountant,
        "patch",
        f"ledgers/{ledger.json()['id']}/",
        {"party": {"products": [{"item": world["a"]}, {"item": world["b"]}]}},
    )
    assert saved.status_code == 200, saved.json()
    rows = saved.json()["party"]["products"]
    assert [(r["their_name"], r["their_code"]) for r in rows] == [("CTC Dust 1", "SRT-1"), ("", "")]


def test_item_export_has_a_sheet_for_the_names(accountant, world):
    from core import exchange

    sheet = next(s for s in exchange.MASTERS["items"].sheets() if s.field == "party_names")
    assert [c.label for c in sheet.columns] == [
        "Customer or supplier",
        "Their item name",
        "Their item code",
    ]
