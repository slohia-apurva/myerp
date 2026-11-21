"""Stock Check (Sidharth, 2026-11-21): Expected = In Stock - Reserved + Incoming;
an item below its branch's safety stock is refilled to Order Up To, in the
purchase unit, rounded up to the minimum order; "Create Purchase Orders" makes
one draft per supplier, and the drafts count as Incoming at once."""

import datetime
from decimal import Decimal

import pytest

from core.models import Item, ItemPlan, Ledger, PartyItemPrice, PriceList
from selling.models import SalesOrder
from tenancy.context import use_tenant
from tests.test_purchase_orders import client_for
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    order,
    owner,
    seller,
    stock_in,
    url,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture
def buyer(alpha):
    return client_for(alpha, "buyer@x.in", "purchase")


@pytest.fixture
def planned(world):  # noqa: F811
    """Green Tea: stock in Packets, bought in Cartons of 24, at least 24 Cartons
    an order, safety 600 and up to 2,400 Packets at the branch."""
    with use_tenant(world["tenant"]):
        maker = Ledger.objects.get(pk=world["maker"])
        tea = Item.objects.get(pk=world["tea"])
        tea.purchase_unit_id = world["case"]
        tea.min_order_qty = Decimal("576")
        tea.lead_time_days = 14
        tea.preferred_supplier = maker.party
        tea.default_request_type = Item.PURCHASE
        tea.save()
        ItemPlan.objects.create(
            item=tea,
            branch_id=world["branch"],
            fulfilment=ItemPlan.PURCHASE,
            safety_qty=600,
            order_up_to=2400,
        )
        PartyItemPrice.objects.create(
            party=maker.party,
            side=PriceList.BUYING,
            item=tea,
            unit_id=world["case"],
            min_qty=0,
            rate=Decimal("2040"),
            from_date=TODAY.replace(day=1),
        )
    return world


def check(client, w, show="short"):
    response = call(
        client, "get", f"companies/{w['company']}/stock-check/?branch={w['branch']}&show={show}"
    )
    assert response.status_code == 200, response.json()
    return response.json()


def test_shortage_is_worked_out_and_bought_once(buyer, seller, planned):  # noqa: F811
    w = planned
    stock_in(w, "fg", "420")
    # a DRAFT sales order already reserves its goods: 25 Cartons = 600 Packets
    draft = call(
        seller,
        "post",
        url(w),
        order(w, lines=[{"item": w["tea"], "unit": w["case"], "qty": "25", "rate": "2280"}]),
    )
    assert draft.status_code == 201, draft.json()

    rows = check(buyer, w)["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert (row["in_stock"], row["reserved"], row["incoming"], row["expected"]) == (
        "420", "600", "0", "-180",
    )  # fmt: skip
    # refill 2,400 + 180 = 2,580 Packets = 107.5 Cartons, up to whole steps of 24 Cartons
    assert row["suggested"] == "120" and row["unit"] == w["case"]
    assert row["rate"] == "2040"
    assert row["supplier"] == w["maker"]
    assert row["by"] == (TODAY + datetime.timedelta(days=14)).isoformat()

    made = call(
        buyer,
        "post",
        f"companies/{w['company']}/stock-check/orders/",
        {
            "branch": w["branch"],
            "lines": [
                {
                    "item": w["tea"],
                    "unit": row["unit"],
                    "qty": row["suggested"],
                    "supplier": row["supplier"],
                }
            ],
        },
    )
    assert made.status_code == 201, made.json()
    [po] = made.json()
    detail = call(buyer, "get", f"purchase-orders/{po['id']}/").json()
    assert detail["status"] == "draft"
    assert detail["expected_date"] == (TODAY + datetime.timedelta(days=14)).isoformat()
    assert [(Decimal(ln["qty"]), Decimal(ln["rate"])) for ln in detail["lines"]] == [
        (Decimal("120"), Decimal("2040"))
    ]

    # the draft is Incoming now, so the item is no longer short
    assert check(buyer, w)["rows"] == []
    again = check(buyer, w, "all")["rows"][0]
    assert again["incoming"] == "2880" and again["short"] is False


def test_cancelled_orders_and_other_fulfilments_are_left_out(buyer, seller, planned):  # noqa: F811
    w = planned
    stock_in(w, "fg", "1000")
    so = call(
        seller,
        "post",
        url(w),
        order(w, lines=[{"item": w["tea"], "unit": w["case"], "qty": "40", "rate": "2280"}]),
    ).json()
    with use_tenant(w["tenant"]):
        SalesOrder.objects.filter(pk=so["id"]).update(status=SalesOrder.CANCELLED)
    assert check(buyer, w)["rows"] == []
    with use_tenant(w["tenant"]):
        ItemPlan.objects.filter(item_id=w["tea"]).update(
            fulfilment=ItemPlan.MANUFACTURE, safety_qty=5000
        )
    assert check(buyer, w, "all")["rows"] == []


def test_suggestion_without_a_minimum_rounds_to_whole_cartons(buyer, planned):  # noqa: F811
    w = planned
    with use_tenant(w["tenant"]):
        Item.objects.filter(pk=w["tea"]).update(min_order_qty=None)
        ItemPlan.objects.filter(item_id=w["tea"]).update(order_up_to=None)
    stock_in(w, "fg", "100")
    row = check(buyer, w)["rows"][0]
    # refill to the safety stock: 500 Packets = 20.83 Cartons, up to 21
    assert row["suggested"] == "21"


def test_needs_the_purchase_rights(seller, planned):  # noqa: F811
    w = planned
    refused = call(
        seller,
        "post",
        f"companies/{w['company']}/stock-check/orders/",
        {
            "branch": w["branch"],
            "lines": [{"item": w["tea"], "unit": w["case"], "qty": "1", "supplier": w["maker"]}],
        },
    )
    assert refused.status_code == 403
