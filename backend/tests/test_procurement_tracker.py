# ruff: noqa: F811  (the fixtures imported below are used by name)
"""Reports › Purchase › Procurement Tracker (Sidharth, 2026-11-27, preview
mockups/purchase-reports/2): one row per order line, ordered, received, billed
and still to come."""

from decimal import Decimal as D

import pytest
from django.utils import timezone

from buying.models import GoodsReceiptLine, PurchaseOrderLine
from tenancy.context import use_tenant
from tests.test_goods_receipts import (  # noqa: F401  (fixtures)
    TODAY,
    buyer,
    call,
    client_for,
    grn,
    owner,
    receipt,
    store,
    tea_line,
    url,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture
def received(alpha, grn, store):
    """The fixture order with 590 of 600 Kg tea accepted (10 rejected), the 30
    boxes not come yet, and 300 Kg of the tea billed."""
    puts = [{"location": grn["bin1"], "batch_number": "B1", "qty": "590"}]
    body = receipt(grn, [tea_line(grn, "600", "10", puts)], submit=True)
    done = call(store, "post", url(grn), body)
    assert done.status_code == 201, done.json()
    with use_tenant(alpha):
        GoodsReceiptLine.objects.filter(order_line_id=grn["tea_line"]).update(billed_qty=D("300"))
    return {**grn, "grn_number": done.json()["number"], "grn_id": done.json()["id"]}


def tracker(client, w, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    got = call(client, "get", f"companies/{w['company']}/procurement-tracker/?{q}")
    assert got.status_code == 200, got.json()
    return got.json()


def test_each_line_shows_ordered_received_billed_and_balance(buyer, received):
    got = tracker(buyer, received, sort="item_name")
    assert got["count"] == 2
    tea, box = sorted(got["results"], key=lambda r: r["item_name"])
    assert (tea["item_name"], tea["unit"]) == ("CTC Tea", "kg")
    assert (D(tea["ordered"]), D(tea["received"]), D(tea["balance"])) == (600, 590, 10)
    assert (tea["grn"], tea["grn_id"], D(tea["billed"])) == (
        received["grn_number"],
        received["grn_id"],
        300,
    )
    assert tea["status"] == "Part received"
    assert tea["pending"] == "2500.00"  # 10 Kg at 250
    assert tea["number"] == received["po_number"] and tea["supplier"] == "Darjeeling Tea Traders"
    assert (D(box["received"]), D(box["balance"]), box["grn"], box["status"]) == (
        0,
        30,
        "",
        "Pending",
    )
    assert tea["late"] is False  # expected in a week


def test_lines_pick_pending_received_or_all(buyer, received, alpha):
    with use_tenant(alpha):
        tea = PurchaseOrderLine.objects.get(pk=received["tea_line"])
        tea.closed_at = timezone.now()
        tea.close_reason = "Supplier short of stock"
        tea.save()
    pending = tracker(buyer, received)["results"]
    assert [r["item_name"] for r in pending] == ["Tea Box"]
    done = tracker(buyer, received, lines="received")["results"]
    assert [(r["item_name"], r["status"], r["reason"], D(r["balance"])) for r in done] == [
        ("CTC Tea", "Closed", "Supplier short of stock", 0)
    ]
    assert tracker(buyer, received, lines="all")["count"] == 2
    got = call(buyer, "get", f"companies/{received['company']}/procurement-tracker/?lines=x")
    assert got.status_code == 400


def test_columns_search_and_sort_on_the_server(buyer, received):
    assert [r["item_name"] for r in tracker(buyer, received, item_name="box")["results"]] == [
        "Tea Box"
    ]
    assert tracker(buyer, received, grn=received["grn_number"])["count"] == 1
    assert tracker(buyer, received, status="part")["count"] == 1
    assert tracker(buyer, received, supplier="assam")["count"] == 0
    assert tracker(buyer, received, date=TODAY.strftime("%d-%m-%Y"))["count"] == 2
    rows = tracker(buyer, received, sort="-balance")["results"]
    assert [D(r["balance"]) for r in rows] == [30, 10]
    assert len(tracker(buyer, received, all=1)["results"]) == 2


def test_drafts_are_left_out_and_the_right_is_needed(buyer, world, alpha):
    from tests.test_purchase_orders import order

    call(buyer, "post", f"companies/{world['company']}/purchase-orders/", order(world))
    assert tracker(buyer, world, lines="all")["count"] == 0
    clerk = client_for(alpha, "clerk@x.in", "production")
    got = call(clerk, "get", f"companies/{world['company']}/procurement-tracker/")
    assert got.status_code == 403
