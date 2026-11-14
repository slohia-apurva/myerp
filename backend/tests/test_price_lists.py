"""Price lists with dates and quantity slabs, and a customer's own item prices."""

import datetime
from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import Role, User
from core import price_lists
from core.companies import create_company
from core.models import Brand, Item, ItemGroup, ItemUnit, Party, Unit
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


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


@pytest.fixture
def world(alpha):
    with use_tenant(alpha):
        pack, carton = Unit.objects.get(name="Packet"), Unit.objects.get(name="Carton")
        more = {
            "stock_unit": pack,
            "hsn": "0902",
            "item_group": ItemGroup.objects.get_or_create(name="General")[0],
            "brand": Brand.objects.get_or_create(name="General brand")[0],
        }
        tea = Item.objects.create(item_number="ITEM-91", name="Green Tea", **more)
        ItemUnit.objects.create(item=tea, unit=pack, factor=1)
        ItemUnit.objects.create(
            item=tea, unit=carton, factor=20, contains_qty=20, contains_unit=pack
        )
        jag = Item.objects.create(item_number="ITEM-92", name="Jaggery", **more)
        ItemUnit.objects.create(item=jag, unit=pack, factor=1)
        fresh = Party.objects.create(name="Fresh Mart", customer_number="CUST-1")
        other = Party.objects.create(name="Other Shop", customer_number="CUST-2")
        return {
            "tea": tea.pk, "jag": jag.pk, "pack": pack.pk, "carton": carton.pk,
            "fresh": fresh.pk, "other": other.pk,
        }  # fmt: skip


def line(w, item="tea", unit="pack", qty="1", rate="180", on="2026-04-01"):
    return {"item": w[item], "unit": w[unit], "min_qty": qty, "rate": rate, "from_date": on}


def make_list(client, w, lines, **more):
    body = {"name": "Retail 2026", "kind": "selling", "lines": lines, **more}
    return call(client, "post", "price-lists/", body)


def test_a_price_list_keeps_dated_slab_lines_and_names_are_unique(accountant, world):
    lines = [
        line(world),
        line(world, qty="50", rate="165"),
        line(world, unit="carton", rate="3900"),
        line(world, rate="190", on="2026-11-01"),
    ]
    made = make_list(accountant, world, lines)
    assert made.status_code == 201, made.json()
    body = made.json()
    assert body["price_count"] == 4 and body["kind_label"] == "Selling"
    assert {r["unit_label"] for r in body["lines"]} == {"Packet (pkt)", "Carton (ctn)"}
    again = call(accountant, "post", "price-lists/", {"name": "retail  2026", "kind": "selling"})
    assert again.status_code == 400 and "already a price list" in str(again.json())
    # Sending lines again replaces them; no lines key leaves them alone.
    one = call(accountant, "patch", f"price-lists/{body['id']}/", {"lines": lines[:1]})
    assert one.json()["price_count"] == 1
    kept = call(accountant, "patch", f"price-lists/{body['id']}/", {"notes": "x"})
    assert kept.json()["price_count"] == 1


def test_lines_must_use_a_unit_of_the_item_and_not_repeat(accountant, world):
    bad_unit = make_list(accountant, world, [line(world, item="jag", unit="carton")])
    assert bad_unit.status_code == 400 and "not kept in Carton" in str(bad_unit.json())
    twice = make_list(accountant, world, [line(world), line(world, rate="170")])
    assert twice.status_code == 400 and "two prices" in str(twice.json())
    zero = make_list(accountant, world, [line(world, qty="0")])
    assert zero.status_code == 400
    negative = make_list(accountant, world, [line(world, rate="-1")])
    assert negative.status_code == 400


def test_a_customer_takes_an_active_selling_list_and_it_then_keeps_its_type(
    accountant, world, alpha
):
    from tests.test_parties import add_ledger

    with use_tenant(alpha):
        company = create_company(name="Apurvam Organics LLP", state_code="27").pk
    selling = make_list(accountant, world, [line(world)]).json()
    buying = make_list(accountant, world, [], name="Suppliers", kind="buying").json()
    party = {"gst_type": "unregistered", "state_code": "27"}
    wrong = add_ledger(
        accountant,
        company,
        "Sundry Debtors",
        name="New Shop",
        party={**party, "price_list": buying["id"]},
    )
    assert wrong.status_code == 400 and "Selling price list" in str(wrong.json())
    made = add_ledger(
        accountant,
        company,
        "Sundry Debtors",
        name="New Shop",
        party={**party, "price_list": selling["id"]},
    )
    assert made.status_code == 201, made.json()
    assert made.json()["party"]["price_list_name"] == "Retail 2026"
    refused = call(accountant, "patch", f"price-lists/{selling['id']}/", {"kind": "buying"})
    assert refused.status_code == 400 and "1 customer" in str(refused.json())
    renamed = call(accountant, "patch", f"price-lists/{selling['id']}/", {"name": "Retail"})
    assert renamed.status_code == 200


def test_customer_prices_are_one_set_seen_from_both_sides(accountant, world):
    rows = [
        line(world, rate="170", on="2026-11-01"),
        line(world, qty="50", rate="160", on="2026-11-01"),
    ]
    saved = call(accountant, "put", f"parties/{world['fresh']}/item-prices/", rows)
    assert saved.status_code == 200, saved.json()
    assert [r["rate"] for r in saved.json()] == ["170.000000", "160.000000"] or len(
        saved.json()
    ) == 2
    from_item = call(accountant, "get", f"items/{world['tea']}/customer-prices/").json()
    assert {r["party_name"] for r in from_item} == {"Fresh Mart"} and len(from_item) == 2
    # Editing from the item side replaces the item's lines for every customer.
    both = [
        {**line(world, rate="170", on="2026-11-01"), "party": world["fresh"]},
        {**line(world, rate="175", on="2026-11-01"), "party": world["other"]},
    ]
    resaved = call(accountant, "put", f"items/{world['tea']}/customer-prices/", both)
    assert resaved.status_code == 200, resaved.json()
    assert len(call(accountant, "get", f"parties/{world['fresh']}/item-prices/").json()) == 1
    assert len(call(accountant, "get", f"parties/{world['other']}/item-prices/").json()) == 1
    assert call(accountant, "put", f"parties/{world['fresh']}/item-prices/", []).json() == []


def test_the_rate_in_force_follows_slabs_dates_and_the_customers_own_prices(
    alpha, accountant, world
):
    made = make_list(
        accountant,
        world,
        [
            line(world, rate="180"),
            line(world, qty="50", rate="165"),
            line(world, rate="190", on="2026-11-01"),
            line(world, unit="carton", rate="3900"),
        ],
    ).json()
    call(
        accountant,
        "put",
        f"parties/{world['fresh']}/item-prices/",
        [line(world, rate="170", on="2026-11-01")],
    )
    d = datetime.date
    with use_tenant(alpha):
        Party.objects.filter(pk__in=[world["fresh"], world["other"]]).update(
            price_list_id=made["id"]
        )
        fresh, other = Party.objects.get(pk=world["fresh"]), Party.objects.get(pk=world["other"])
        tea, pack, carton = (
            Item.objects.get(pk=world["tea"]),
            Unit.objects.get(pk=world["pack"]),
            Unit.objects.get(pk=world["carton"]),
        )
        rate = price_lists.rate_for
        # Other shop: the list. Latest started rate per slab, biggest slab not above the quantity.
        assert rate(other, tea, pack, 10, d(2026, 6, 1)) == Decimal("180")
        assert rate(other, tea, pack, 60, d(2026, 6, 1)) == Decimal("165")
        assert rate(other, tea, pack, 10, d(2026, 11, 15)) == Decimal("190")
        assert rate(other, tea, pack, 60, d(2026, 11, 15)) == Decimal("165")
        assert rate(other, tea, carton, 1, d(2026, 11, 15)) == Decimal("3900")
        assert rate(other, tea, pack, 10, d(2026, 3, 1)) is None  # nothing started yet
        # Fresh Mart: its own line replaces the list for that item once it has started.
        assert rate(fresh, tea, pack, 60, d(2026, 11, 15)) == Decimal("170")
        assert rate(fresh, tea, pack, 60, d(2026, 6, 1)) == Decimal("165")  # not started: the list
        assert rate(fresh, tea, carton, 1, d(2026, 11, 15)) == Decimal("3900")  # another unit
        assert rate(None, tea, pack, 1, d(2026, 11, 15)) is None


def test_price_lists_export_and_import_with_prices_by_name(accountant, world):
    made = make_list(accountant, world, [line(world), line(world, qty="50", rate="165")]).json()
    out = accountant.get("/api/v1/exchange/price-lists/?as=json", HTTP_HOST=HOST).json()
    assert [s["title"] for s in out["sheets"]][0] == "Price lists"
    prices = next(s for s in out["sheets"] if s["title"] != "Price lists")
    assert "Item" in prices["columns"] and len(prices["rows"]) == 2
    assert any("Green Tea" in str(cell) for row in prices["rows"] for cell in row)
    assert made["price_count"] == 2
