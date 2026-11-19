"""Pick lists (Sidharth, 2026-11-19, previews mockups/sales 5 and 6): made on
Submit of a sales order with bins and batches chosen by the rule (Despatch From
only, earliest expiry, then oldest received, held batches never, stock on other
lists kept aside), editable while open, final once submitted."""

import datetime
from decimal import Decimal

import pytest

from core.models import Batch, Company, Item, WarehouseLocation
from posting import accounts
from posting.service import GLLine, StockLine, Voucher, post
from tenancy.context import use_tenant
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    order,
    owner,
    seller,
    url,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

_n = iter(range(100, 1000))


def receive(w, where, qty, batch=None, expiry=None, status=Batch.RELEASED, days_ago=0):
    """Goods put into a place with a batch, as a goods receipt would post them."""
    with use_tenant(w["tenant"]):
        company = Company.objects.get(pk=w["company"])
        loc = WarehouseLocation.objects.get(pk=where)
        tea = Item.objects.get(pk=w["tea"])
        if batch and not tea.batch_tracked:
            tea.batch_tracked = True
            tea.save(update_fields=["batch_tracked"])
        lot = None
        if batch:
            lot = Batch.objects.get_or_create(
                item=tea, number=batch, defaults={"expiry_date": expiry, "status": status}
            )[0]
        adj = accounts.system_ledger(company, accounts.STOCK_ADJUSTMENT)
        grni = accounts.system_ledger(company, accounts.GRNI)
        n = next(_n)
        day = TODAY - datetime.timedelta(days=days_ago)
        post(
            Voucher(company, loc.branch, day, "test_receipt", n, f"T-{n}"),
            stock=[StockLine(tea, loc, Decimal(qty), Decimal("10"), batch=lot)],
            gl=lambda v: [GLLine(adj, debit=v[0]), GLLine(grni, credit=v[0])],
        )


def new_bin(w, name):
    with use_tenant(w["tenant"]):
        rack = WarehouseLocation.objects.get(name="FG-R1")
        return WarehouseLocation.objects.create(
            branch_id=w["branch"], kind=WarehouseLocation.BIN, name=name, parent=rack
        ).pk


def submit(client, w, cases="25", area=True, **more):
    lines = [{"item": w["tea"], "unit": w["case"], "qty": cases, "rate": "2280"}]
    body = order(w, lines=lines, area=w["fg"] if area else None, **more)
    so = call(client, "post", url(w), body).json()
    done = call(client, "post", f"sales-orders/{so['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    return done.json()


def picked(client, so):
    pl = so["pick_lists"][-1]
    return call(client, "get", f"pick-lists/{pl['id']}/").json()


def rows_of(pl):
    return [
        (r["location_name"], r["batch_number"], r["qty"]) for i in pl["items"] for r in i["rows"]
    ]


def test_submit_picks_by_expiry_in_the_area_only(seller, world):  # noqa: F811
    soon = TODAY + datetime.timedelta(days=60)
    later = TODAY + datetime.timedelta(days=200)
    receive(world, world["bin"], "300", "A-LATE", later)
    receive(world, world["bin"], "200", "Q-HELD", TODAY, status=Batch.QUARANTINE)
    receive(world, world["store"], "500", "B-SOON", soon)  # outside the area
    so = submit(seller, world)
    assert len(so["pick_lists"]) == 1
    head = so["pick_lists"][0]
    assert "/PL/" in head["number"] and head["status"] == "open"
    assert head["all_in"] is False and head["full_count"] == 0
    # 25 cartons = 600 packets; only 300 of the released batch are in the area.
    assert head["text"].startswith("Not all in stock: 0 of 1 items fully picked")
    assert "found 12.5" in head["text"] and "(300 " in head["text"]
    pl = picked(seller, so)
    assert rows_of(pl) == [("FG-R1-B1", "A-LATE", "300")]
    assert pl["items"][0]["short"] == "12.5" and pl["items"][0]["picked"] == "12.5"


def test_from_the_branch_earliest_expiry_first_and_kept_aside(seller, owner, world):  # noqa: F811
    soon = TODAY + datetime.timedelta(days=60)
    later = TODAY + datetime.timedelta(days=200)
    receive(world, world["bin"], "300", "A-LATE", later)
    receive(world, world["store"], "500", "B-SOON", soon)
    first = submit(seller, world, area=False)
    assert first["pick_lists"][0]["all_in"] is True
    one = rows_of(picked(seller, first))
    assert [(b, q) for _, b, q in one] == [("B-SOON", "500"), ("A-LATE", "100")]
    # The next order finds only what the first list left: 200 of A-LATE.
    second = submit(seller, world, cases="10", area=False)
    two = picked(seller, second)
    assert rows_of(two) == [("FG-R1-B1", "A-LATE", "200")]
    assert two["items"][0]["short_stock"] == "40"
    # Only one live list per order; cancelling frees its stock for a new one.
    again = f"sales-orders/{second['id']}/pick-list/"
    assert "already has a pick list" in str(call(seller, "post", again, {}).json())
    first_list = first["pick_lists"][0]["id"]
    cancel = f"pick-lists/{first_list}/cancel/"
    assert "Say why" in str(call(owner, "post", cancel, {}).json())
    assert call(owner, "post", cancel, {"reason": "Order on hold"}).json()["status"] == "cancelled"
    call(owner, "post", f"pick-lists/{two['id']}/cancel/", {"reason": "Pick again"})
    fresh = call(seller, "post", again, {})
    assert fresh.status_code == 201, fresh.json()
    assert fresh.json()["all_in"] is True
    assert [r[1] for r in rows_of(fresh.json())] == ["B-SOON"]


def test_oldest_received_first_when_no_expiry(seller, world):  # noqa: F811
    newer = new_bin(world, "FG-R1-B2")
    receive(world, newer, "400", days_ago=1)
    receive(world, world["bin"], "400", days_ago=20)
    pl = picked(seller, submit(seller, world))
    assert rows_of(pl) == [("FG-R1-B1", "", "400"), ("FG-R1-B2", "", "200")]


def test_an_open_list_can_be_changed_then_submitted(seller, owner, world):  # noqa: F811
    later = TODAY + datetime.timedelta(days=200)
    other = new_bin(world, "FG-R1-B2")
    receive(world, world["bin"], "300", "A-LATE", later)
    receive(world, other, "300", "C-OTHER", later)
    receive(world, other, "100", "Q-HELD", later, status=Batch.QUARANTINE)
    so = submit(seller, world, cases="10")  # 240 packets
    pl = picked(seller, so)
    line = pl["items"][0]["order_line"]
    with use_tenant(world["tenant"]):
        ids = {b.number: b.pk for b in Batch.objects.all()}
    path = f"pick-lists/{pl['id']}/"
    places = call(seller, "get", f"{path}places/?item={world['tea']}").json()
    assert {p["batch_number"] for p in places} == {"A-LATE", "C-OTHER"}  # held batch left out
    row = {"order_line": line, "location": other, "batch": ids["C-OTHER"]}
    too_much = call(seller, "patch", path, {"rows": [{**row, "qty": "400"}]})
    assert "has 300 free" in str(too_much.json())
    over = call(seller, "patch", path, {"rows": [{**row, "qty": "250"}]})
    assert "more than the 240 still to go" in str(over.json())
    held = call(seller, "patch", path, {"rows": [{**row, "batch": ids["Q-HELD"], "qty": "10"}]})
    assert "Quarantine" in str(held.json())
    changed = call(
        seller,
        "patch",
        path,
        {
            "rows": [
                {**row, "qty": "140"},
                {**row, "location": world["bin"], "batch": ids["A-LATE"], "qty": "100"},
            ]
        },
    )
    assert changed.status_code == 200, changed.json()
    assert sorted(rows_of(changed.json())) == [
        ("FG-R1-B1", "A-LATE", "100"),
        ("FG-R1-B2", "C-OTHER", "140"),
    ]
    done = call(seller, "post", f"{path}submit/", {}).json()
    assert done["status"] == "picked" and done["all_in"] is True
    assert "Only an open" in str(call(seller, "patch", path, {"rows": []}).json())
    # Cancelling the order cancels its list and frees the stock.
    gone = call(owner, "post", f"sales-orders/{so['id']}/cancel/", {"reason": "Withdrawn"}).json()
    assert gone["pick_lists"][0]["status"] == "cancelled"
    listed = call(seller, "get", f"companies/{world['company']}/pick-lists/?view=all").json()
    assert [p["number"] for p in listed] == [pl["number"]]


def test_no_stock_items_no_list(seller, world):  # noqa: F811
    with use_tenant(world["tenant"]):
        Item.objects.filter(pk=world["tea"]).update(maintain_stock=False)
    so = submit(seller, world)
    assert so["pick_lists"] == []


def test_the_list_prints(seller, world):  # noqa: F811
    receive(world, world["bin"], "100")
    pl = picked(seller, submit(seller, world))
    got = seller.get(f"/api/v1/pick-lists/{pl['id']}/pdf/", HTTP_HOST="alpha.localhost")
    assert got.status_code == 200 and got["Content-Type"] == "application/pdf"
    assert got["Content-Disposition"].startswith("inline")
