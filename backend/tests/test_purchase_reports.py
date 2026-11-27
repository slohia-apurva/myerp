# ruff: noqa: F811  (the fixtures imported below are used by name)
"""Reports › Purchase › Pending Purchase Orders (Sidharth, 2026-11-27, preview
mockups/purchase-reports/1)."""

import datetime
from decimal import Decimal as D

import pytest
from django.utils import timezone

from buying.models import PurchaseOrder, PurchaseOrderLine
from tenancy.context import use_tenant
from tests.test_purchase_orders import (  # noqa: F401  (fixtures)
    TODAY,
    buyer,
    call,
    client_for,
    order,
    owner,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def make(client, w, submit=True, **more):
    made = call(
        client,
        "post",
        f"companies/{w['company']}/purchase-orders/",
        order(w, submit=submit, **more),
    )
    assert made.status_code == 201, made.json()
    return made.json()


def report(client, w, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    got = call(client, "get", f"companies/{w['company']}/pending-purchase-orders/?{q}")
    assert got.status_code == 200, got.json()
    return got.json()


def test_a_submitted_order_shows_what_is_still_to_come(buyer, world, alpha):
    po = make(buyer, world)
    make(buyer, world, submit=False)  # a draft is not an order yet
    with use_tenant(alpha):
        tea = PurchaseOrderLine.objects.get(order_id=po["id"], item_id=world["tea"])
        tea.received_qty = D("200")  # 300 of 500 Kg to come
        tea.save()
        PurchaseOrder.objects.filter(pk=po["id"]).update(status=PurchaseOrder.PART_RECEIVED)
    got = report(buyer, world)
    assert got["count"] == 1
    row = got["results"][0]
    assert row["number"] == po["number"]
    assert row["supplier"] == "Darjeeling Tea Traders"
    assert row["lines"] == 2
    assert row["status"] == "Part received"
    # 500 × 180 + 33 × 12.35 less 10% = 90,000 + 366.80; pending 300 × 180 + all the boxes.
    assert row["value"] == "90366.80"
    assert row["pending"] == "54366.80"
    assert row["late"] == 0
    assert got["totals"] == {"orders": 1, "lines": 2, "value": "90366.80", "pending": "54366.80"}


def test_received_and_closed_lines_are_not_pending(buyer, world, alpha):
    po = make(buyer, world)
    with use_tenant(alpha):
        tea = PurchaseOrderLine.objects.get(order_id=po["id"], item_id=world["tea"])
        tea.received_qty = tea.qty
        tea.save()
        box = PurchaseOrderLine.objects.get(order_id=po["id"], item_id=world["box"])
        box.closed_at = timezone.now()
        box.save()
    assert report(buyer, world)["count"] == 0
    with use_tenant(alpha):
        box.closed_at = None
        box.save()
    row = report(buyer, world)["results"][0]
    assert (row["lines"], row["pending"]) == (1, "366.80")


def test_late_orders_count_days_from_the_expected_date(buyer, world, alpha):
    late = make(buyer, world)
    make(buyer, world, supplier="far")
    with use_tenant(alpha):
        PurchaseOrder.objects.filter(pk=late["id"]).update(
            expected_date=TODAY - datetime.timedelta(days=12)
        )
    got = report(buyer, world, late=1)
    assert [(r["number"], r["late"]) for r in got["results"]] == [(late["number"], 12)]
    # Sorted by Days Late, most late last.
    rows = report(buyer, world, sort="late")["results"]
    assert [r["late"] for r in rows] == [0, 12]
    rows = report(buyer, world, sort="-late")["results"]
    assert [r["late"] for r in rows] == [12, 0]


def test_columns_search_and_filter_on_the_server(buyer, world):
    a = make(buyer, world)
    b = make(buyer, world, supplier="far")
    assert [r["number"] for r in report(buyer, world, supplier="assam")["results"]] == [b["number"]]
    assert report(buyer, world, status="part")["count"] == 0
    assert report(buyer, world, status="ordered")["count"] == 2
    day = TODAY.strftime("%d-%m-%Y")
    assert report(buyer, world, date=day)["count"] == 2
    tomorrow = (TODAY + datetime.timedelta(days=1)).isoformat()
    assert report(buyer, world, **{"from": tomorrow})["count"] == 0
    assert report(buyer, world, branch=world["branch"])["count"] == 2
    assert report(buyer, world, branch="x")["count"] == 0
    assert {r["number"] for r in report(buyer, world, all=1)["results"]} == {
        a["number"],
        b["number"],
    }


def test_pages_of_25(buyer, world, alpha):
    po = make(buyer, world)
    with use_tenant(alpha):
        first = PurchaseOrder.objects.get(pk=po["id"])
        lines = list(first.lines.all())
        for n in range(26):
            copy = PurchaseOrder.objects.get(pk=po["id"])
            copy.pk = None
            copy.number = f"PO-COPY-{n:02}"
            copy.save()
            for ln in lines:
                ln.pk = None
                ln.order = copy
                ln.save()
    got = report(buyer, world, page=2, sort="number")
    assert (got["count"], got["pages"], got["page"], len(got["results"])) == (27, 2, 2, 2)
    assert got["totals"]["orders"] == 27


def test_bad_dates_are_refused_and_the_right_is_needed(buyer, world, alpha):
    got = call(buyer, "get", f"companies/{world['company']}/pending-purchase-orders/?from=1-1")
    assert got.status_code == 400
    clerk = client_for(alpha, "clerk@x.in", "production")
    got = call(clerk, "get", f"companies/{world['company']}/pending-purchase-orders/")
    assert got.status_code == 403
