"""Delivery notes (Sidharth, 2026-11-20, previews 7-9 in mockups/sales): made
from a picked pick list; Submit takes the goods out of their bins at FIFO cost,
Dr "Goods Delivered but Bills not Made" (decided 2026-11-19), Cr Stock, and the
order counts them as delivered. Problems on Submit come back together, each
with its line."""

import datetime
from decimal import Decimal

import pytest

from core.models import Batch, ItemGroupAccount, Ledger, LedgerGroup
from posting import accounts
from posting.models import GLEntry, StockMove
from selling.models import SalesOrderLine
from tenancy.context import use_tenant
from tests.test_pick_lists import new_bin, picked, receive, submit
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    owner,
    seller,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

LATER = TODAY + datetime.timedelta(days=200)


@pytest.fixture
def books(world):  # noqa: F811
    """The item group's ledgers a delivery note posts to."""
    with use_tenant(world["tenant"]):
        from core.models import Item

        tea = Item.objects.get(pk=world["tea"])
        company = world["company"]
        stock = Ledger.objects.create(
            company_id=company,
            group=LedgerGroup.objects.get(company_id=company, code="stock_in_hand"),
            name="Stock",
        )
        cogs = Ledger.objects.create(
            company_id=company,
            group=LedgerGroup.objects.get(company_id=company, code="direct_expenses"),
            name="Cost of Tea",
        )
        ItemGroupAccount.objects.create(
            group=tea.item_group, company_id=company, stock_ledger=stock, cogs_ledger=cogs
        )
    return world


def picked_list(client, w, cases="10"):
    """An order submitted and its pick list submitted ("Picked")."""
    so = submit(client, w, cases=cases)
    pl = picked(client, so)
    done = call(client, "post", f"pick-lists/{pl['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    return so, done.json()


def new_note(client, pl):
    made = call(client, "post", f"pick-lists/{pl['id']}/delivery-note/", {})
    assert made.status_code in (200, 201), made.json()
    return made.json()


def body(note, **more):
    bins = [
        {
            "line": ln["id"],
            "location": b["location"],
            "batch": b["batch"],
            "package": b["package"],
            "qty": b["qty"],
        }
        for ln in note["lines"]
        for b in ln["bins"]
    ]
    return {
        "note_date": TODAY.isoformat(),
        "transporter": None,
        "mode": "road",
        "vehicle_no": "wb 11 d 2290",
        "distance_km": 1968,
        "lr_no": "SFX-77812",
        "bins": bins,
        **more,
    }


def test_from_pick_list_to_posting(seller, owner, books):  # noqa: F811
    w = books
    receive(w, w["bin"], "300", "A-LATE", LATER)  # at 10 a packet
    so, pl = picked_list(seller, w)  # 10 cartons = 240 packets
    note = new_note(seller, pl)
    assert note["status"] == "draft" and note["pick_list_number"] == pl["number"]
    line = note["lines"][0]
    assert (line["qty"], line["picked"], line["unit_name"], line["rate"]) == (
        "10",
        "10",
        "ctn",
        "2280",
    )
    assert line["taxable"] == "22800.00" and line["bins"][0]["batch_number"] == "A-LATE"
    # The same pick list gives the same draft, not a second one.
    assert new_note(seller, pl)["id"] == note["id"]
    # The draft shows what Submit will post, at cost.
    preview = call(seller, "get", f"delivery-notes/{note['id']}/ledger-posting/").json()
    assert preview["posted"] is False
    assert [(r["ledger_name"], r["debit"], r["credit"]) for r in preview["rows"]] == [
        ("Goods Delivered but Bills not Made", "2400.00", "0.00"),
        ("Stock", "0.00", "2400.00"),
    ]
    done = call(seller, "patch", f"delivery-notes/{note['id']}/", body(note, submit=True))
    assert done.status_code == 200, done.json()
    sent = done.json()
    assert sent["status"] == "submitted" and "/DC/" in sent["number"]
    assert sent["vehicle_no"] == "WB11D2290" and sent["cost_total"] == "2400.00"
    assert sent["pick_list_status"] == "Delivered"
    with use_tenant(w["tenant"]):
        gdnb = accounts.system_ledger(
            Ledger.objects.get(pk=w["local"]).company, accounts.GOODS_DELIVERED_NOT_BILLED
        )
        rows = GLEntry.objects.filter(voucher_type="delivery_note", voucher_id=sent["id"])
        assert {(e.ledger.name, e.debit, e.credit) for e in rows} == {
            (gdnb.name, Decimal("2400.00"), Decimal("0.00")),
            ("Stock", Decimal("0.00"), Decimal("2400.00")),
        }
        moves = StockMove.objects.filter(voucher_type="delivery_note", voucher_id=sent["id"])
        assert [(m.qty, m.batch.number) for m in moves] == [(Decimal("-240"), "A-LATE")]
        assert SalesOrderLine.objects.get(order_id=so["id"]).delivered_qty == 10
    order = call(seller, "get", f"sales-orders/{so['id']}/").json()
    assert order["status"] == "delivered" and order["lines"][0]["pending_qty"] == "0"
    assert [n["number"] for n in order["delivery_notes"]] == [sent["number"]]
    posted = call(seller, "get", f"delivery-notes/{note['id']}/ledger-posting/").json()
    assert posted["posted"] is True and len(posted["rows"]) == 2
    assert "cannot be changed" in str(
        call(seller, "patch", f"delivery-notes/{note['id']}/", body(note)).json()
    )
    # Cancel: the goods come back, the order is pending again, the list is picked again.
    path = f"delivery-notes/{note['id']}/cancel/"
    assert "Say why" in str(call(owner, "post", path, {}).json())
    gone = call(owner, "post", path, {"reason": "Truck did not come"}).json()
    assert gone["status"] == "cancelled" and gone["pick_list_status"] == "Picked"
    order = call(seller, "get", f"sales-orders/{so['id']}/").json()
    assert order["status"] == "ordered" and order["lines"][0]["pending_qty"] == "10"
    with use_tenant(w["tenant"]):
        moves = StockMove.objects.filter(voucher_type="delivery_note", voucher_id=sent["id"])
        assert sum(m.qty for m in moves) == 0


def test_sending_less_leaves_the_rest_pending(seller, books):  # noqa: F811
    w = books
    receive(w, w["bin"], "300", "A-LATE", LATER)
    so, pl = picked_list(seller, w)
    note = new_note(seller, pl)
    less = body(note)
    less["bins"][0]["qty"] = "120"  # 5 cartons
    saved = call(seller, "patch", f"delivery-notes/{note['id']}/", less)
    assert saved.status_code == 200, saved.json()
    line = saved.json()["lines"][0]
    assert line["qty"] == "5" and line["taxable"] == "11400.00" and line["picked"] == "10"
    too_many = body(note)
    too_many["bins"][0]["qty"] = "250"
    assert "more than the 240 still to go" in str(
        call(seller, "patch", f"delivery-notes/{note['id']}/", too_many).json()
    )
    done = call(seller, "post", f"delivery-notes/{note['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    order = call(seller, "get", f"sales-orders/{so['id']}/").json()
    assert order["status"] == "part_delivered" and order["lines"][0]["pending_qty"] == "5"
    # A new pick list takes what is pending.
    again = call(seller, "post", f"sales-orders/{so['id']}/pick-list/", {})
    assert again.status_code == 201, again.json()
    assert again.json()["items"][0]["ordered"] == "5"


def test_problems_come_back_together_with_their_lines(seller, books):  # noqa: F811
    w = books
    other = new_bin(w, "FG-R1-B2")
    receive(w, w["bin"], "300", "A-LATE", LATER)
    receive(w, other, "100", "Q-HELD", LATER, status=Batch.QUARANTINE)
    so, pl = picked_list(seller, w)
    note = new_note(seller, pl)
    with use_tenant(w["tenant"]):
        held = Batch.objects.get(number="Q-HELD").pk
    moved = body(note)
    moved["bins"] = [
        {**moved["bins"][0], "qty": "200"},
        {"line": note["lines"][0]["id"], "location": other, "batch": held, "qty": "40"},
    ]
    assert call(seller, "patch", f"delivery-notes/{note['id']}/", moved).status_code == 200
    # Someone else takes stock from the bin since it was picked.
    receive_out(w, "150")
    res = call(seller, "post", f"delivery-notes/{note['id']}/submit/", {})
    assert res.status_code == 400
    found = res.json()
    assert found["id"] == note["id"]
    texts = [p["text"] for p in found["problems"]]
    assert all(p["line"] == 1 for p in found["problems"])
    assert any("Q-HELD is held back (Quarantine)" in t for t in texts)
    assert any("FG-R1-B1, batch A-LATE now has 150" in t for t in texts)
    with use_tenant(w["tenant"]):
        assert not StockMove.objects.filter(voucher_type="delivery_note").exists()


def receive_out(w, qty):
    """Stock taken out of the first bin by another entry (not on a pick list)."""
    from core.models import Company, Item, WarehouseLocation
    from posting.service import GLLine, StockLine, Voucher, post

    with use_tenant(w["tenant"]):
        company = Company.objects.get(pk=w["company"])
        loc = WarehouseLocation.objects.get(pk=w["bin"])
        tea = Item.objects.get(pk=w["tea"])
        adj = accounts.system_ledger(company, accounts.STOCK_ADJUSTMENT)
        grni = accounts.system_ledger(company, accounts.GRNI)
        post(
            Voucher(company, loc.branch, TODAY, "test_issue", 1, "X-1"),
            stock=[
                StockLine(
                    tea, loc, -Decimal(qty), batch=Batch.objects.get(number="A-LATE", item=tea)
                )
            ],
            gl=lambda v: [GLLine(grni, debit=-v[0]), GLLine(adj, credit=-v[0])],
        )


def test_missing_ledgers_and_an_unpicked_list(seller, world):  # noqa: F811
    receive(world, world["bin"], "300", "A-LATE", LATER)
    so = submit(seller, world, cases="10")
    pl = picked(seller, so)
    early = call(seller, "post", f"pick-lists/{pl['id']}/delivery-note/", {})
    assert "Submit the pick list first" in str(early.json())
    call(seller, "post", f"pick-lists/{pl['id']}/submit/", {})
    note = new_note(seller, pl)
    res = call(seller, "post", f"delivery-notes/{note['id']}/submit/", {})
    assert res.status_code == 400
    assert res.json()["missing_accounts"][0]["missing"] == ["Stock Ledger", "COGS/Expense Ledger"]
    assert res.json()["id"] == note["id"]


def test_list_and_prints(seller, books):  # noqa: F811
    w = books
    receive(w, w["bin"], "300", "A-LATE", LATER)
    _so, pl = picked_list(seller, w)
    note = new_note(seller, pl)
    listed = call(seller, "get", f"companies/{w['company']}/delivery-notes/?view=draft").json()
    assert [n["id"] for n in listed] == [note["id"]]
    for layout in ("challan", "packing"):
        got = seller.get(
            f"/api/v1/delivery-notes/{note['id']}/pdf/?layout={layout}", HTTP_HOST="alpha.localhost"
        )
        assert got.status_code == 200 and got["Content-Type"] == "application/pdf"
    places = call(seller, "get", f"delivery-notes/{note['id']}/places/?item={w['tea']}").json()
    assert [p["batch_number"] for p in places] == ["A-LATE"]
