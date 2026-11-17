"""Goods receipts: put-away into bins and batches, posting, over-receipt alerts, cancel."""

from decimal import Decimal as D

import pytest

from accounts.models import User
from audit.models import AuditEntry
from buying.models import GoodsReceipt, PurchaseOrder, PurchaseOrderLine
from core.models import (
    Batch,
    Item,
    ItemGroupAccount,
    Ledger,
    LedgerGroup,
    Notification,
    SalesPerson,
    WarehouseLocation,
)
from posting import accounts
from posting.models import GLEntry, StockMove
from posting.service import gl_balance, on_hand
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


@pytest.fixture
def store(alpha):
    return client_for(alpha, "stores@x.in", "storekeeper")


@pytest.fixture
def grn(alpha, world, owner, buyer):  # noqa: F811
    """A submitted order for 600 Kg of tea and 30 packets, with freight to stock by
    quantity, and the places and accounts a receipt needs."""
    with use_tenant(alpha):
        tea = Item.objects.get(pk=world["tea"])
        tea.batch_tracked = True
        tea.best_before_value, tea.best_before_unit = 24, Item.MONTHS
        tea.save()
        inventories = LedgerGroup.objects.get(company_id=world["company"], code="stock_in_hand")
        stock = Ledger.objects.create(company_id=world["company"], group=inventories, name="Stock")
        direct = LedgerGroup.objects.get(company_id=world["company"], code="direct_expenses")
        cogs = Ledger.objects.create(company_id=world["company"], group=direct, name="Cost of Tea")
        ItemGroupAccount.objects.create(
            group=tea.item_group, company_id=world["company"], stock_ledger=stock, cogs_ledger=cogs
        )
        rack = WarehouseLocation.objects.create(branch_id=world["branch"], kind="rack", name="F01")
        bin1 = WarehouseLocation.objects.create(
            branch_id=world["branch"], kind="bin", name="A-02", parent=rack
        )
        bin2 = WarehouseLocation.objects.create(
            branch_id=world["branch"], kind="bin", name="A-06", parent=rack
        )
        store_area = WarehouseLocation.objects.get(branch_id=world["branch"], is_default=True)
        more = {"hsn": "0902", "item_group": tea.item_group, "brand": tea.brand}
        more |= {"stock_unit": tea.stock_unit, "item_type": Item.SERVICE, "maintain_stock": False}
        freight = Item.objects.create(item_number="ITEM-81", name="Freight Inward",
                                      purchase_charge=True, add_to_stock="qty", **more)  # fmt: skip
    lines = [
        {"item": world["tea"], "unit": world["kg"], "qty": "600", "rate": "250"},
        {"item": world["box"], "unit": world["pack"], "qty": "30", "rate": "20"},
    ]
    charges = [{"item": freight.pk, "basis": "fixed", "rate": "6300", "gst_rate": "18"}]
    po = call(
        buyer,
        "post",
        f"companies/{world['company']}/purchase-orders/",
        order(world, lines=lines, charges=charges, submit=True),
    )
    assert po.status_code == 201, po.json()
    po = po.json()
    return {
        **world,
        "po": po["id"],
        "po_number": po["number"],
        "tea_line": po["lines"][0]["id"],
        "box_line": po["lines"][1]["id"],
        "bin1": bin1.pk,
        "bin2": bin2.pk,
        "rack": rack.pk,
        "area": store_area.pk,
        "stock": stock.pk,
    }


def receipt(g, lines, **more):
    return {
        "supplier": g["local"],
        "branch": g["branch"],
        "receipt_date": TODAY.isoformat(),
        "orders": [g["po"]],
        "challan_no": "DTT/1187",
        "vehicle_no": "wb 23 c 4471",
        "lines": lines,
        **more,
    }


def tea_line(g, received="600", rejected="0", puts=None):
    return {
        "order_line": g["tea_line"],
        "received_qty": received,
        "rejected_qty": rejected,
        "putaways": puts
        if puts is not None
        else [
            {"location": g["bin1"], "batch_number": "DTT-26-118", "mfg_date": "2026-11-02",
             "qty": "300"},
            {"location": g["bin2"], "batch_number": "DTT-26-118", "qty": "300"},
        ],
    }  # fmt: skip


def box_line(g, received="30", puts=None):
    return {
        "order_line": g["box_line"],
        "received_qty": received,
        "putaways": puts if puts is not None else [{"location": g["area"], "qty": received}],
    }


def url(g):
    return f"companies/{g['company']}/goods-receipts/"


def test_pending_orders_bring_the_lines_still_to_come(store, grn):
    rows = call(store, "get", f"{url(grn)}pending/?supplier={grn['local']}").json()
    assert [o["number"] for o in rows] == [grn["po_number"]]
    got = [(x["item_name"], x["pending"], x["batch_tracked"]) for x in rows[0]["lines"]]
    assert got == [("CTC Tea", "600.000000", True), ("Tea Box", "30.000000", False)]


def test_a_storekeeper_saves_a_draft_then_submits_it(store, grn, alpha):
    made = call(store, "post", url(grn), receipt(grn, [tea_line(grn), box_line(grn)]))
    assert made.status_code == 201, made.json()
    draft = made.json()
    assert draft["status"] == "draft" and draft["number"] == ""
    assert draft["vehicle_no"] == "WB 23 C 4471"
    assert draft["lines"][0]["putaways"][0]["new_batch"] is True
    done = call(store, "post", f"goods-receipts/{draft['id']}/submit/")
    assert done.status_code == 200, done.json()
    body = done.json()
    assert body["status"] == "submitted" and "GRN" in body["number"]
    # Tea 600 x 250 = 1,50,000 + freight 6,300 (all on stock lines by quantity: 600 of 630).
    # Box 30 x 20 = 600 + 300 freight.
    assert body["stock_value"] == "156900.00"
    tea, box = body["lines"]
    assert (tea["value"], tea["charges_value"]) == ("156000.00", "6000.00")
    assert (box["value"], box["charges_value"]) == ("900.00", "300.00")
    with use_tenant(alpha):
        batch = Batch.objects.get(item_id=grn["tea"], number="DTT-26-118")
        assert str(batch.expiry_date) == "2028-11-02"  # from the item's 24 months
        tea_item = Item.objects.get(pk=grn["tea"])
        assert on_hand(tea_item, WarehouseLocation.objects.get(pk=grn["bin1"]), batch) == 300
        assert StockMove.objects.filter(voucher_type="goods_receipt").count() == 3
        assert gl_balance(Ledger.objects.get(pk=grn["stock"])) == D("156900.00")
        company = Ledger.objects.get(pk=grn["stock"]).company
        grni = accounts.system_ledger(company, accounts.GRNI)
        assert gl_balance(grni) == D("-156900.00")
        po = PurchaseOrder.objects.get(pk=grn["po"])
        assert po.status == PurchaseOrder.RECEIVED
        assert PurchaseOrderLine.objects.get(pk=grn["tea_line"]).received_qty == 600


def test_rejected_goods_stay_out_and_the_order_is_part_received(store, grn, alpha):
    puts = [{"location": grn["bin1"], "batch_number": "B1", "qty": "590"}]
    body = receipt(grn, [tea_line(grn, "600", "10", puts)], submit=True)
    done = call(store, "post", url(grn), body)
    assert done.status_code == 201, done.json()
    assert done.json()["lines"][0]["accepted_qty"] == "590.000000"
    with use_tenant(alpha):
        assert PurchaseOrder.objects.get(pk=grn["po"]).status == PurchaseOrder.PART_RECEIVED
    later = call(store, "get", f"{url(grn)}pending/?supplier={grn['local']}").json()
    assert later[0]["lines"][0]["pending"] == "10.000000"


def test_everything_accepted_must_be_put_away_with_its_batch(store, grn):
    short = [{"location": grn["bin1"], "batch_number": "B1", "qty": "500"}]
    res = call(store, "post", url(grn), receipt(grn, [tea_line(grn, puts=short)], submit=True))
    assert res.status_code == 400
    assert "600 kg accepted but the bins hold 500 (100 kg short)" in str(res.json())
    over = [{"location": grn["bin1"], "batch_number": "B1", "qty": "640"}]
    res = call(store, "post", url(grn), receipt(grn, [tea_line(grn, puts=over)], submit=True))
    assert res.status_code == 400 and "hold 640 (40 kg over)" in str(res.json())
    nobatch = [{"location": grn["bin1"], "qty": "600"}]
    res = call(store, "post", url(grn), receipt(grn, [tea_line(grn, puts=nobatch)], submit=True))
    assert "give the batch" in str(res.json())
    rack = [{"location": grn["rack"], "batch_number": "B1", "qty": "600"}]
    res = call(store, "post", url(grn), receipt(grn, [tea_line(grn, puts=rack)]))
    assert "pick a bin or area" in str(res.json())


def test_an_existing_batch_is_reused_by_its_number(store, grn, alpha):
    with use_tenant(alpha):
        old = Batch.objects.create(item_id=grn["tea"], number="DTT-1")
    puts = [{"location": grn["bin1"], "batch_number": "dtt-1", "qty": "600"}]
    done = call(store, "post", url(grn), receipt(grn, [tea_line(grn, puts=puts)], submit=True))
    assert done.status_code == 201, done.json()
    assert done.json()["lines"][0]["putaways"][0]["batch"] == old.pk


def test_over_receipt_tells_purchase_and_the_owner(store, buyer, grn, alpha):  # noqa: F811
    puts = [{"location": grn["bin1"], "batch_number": "B1", "qty": "650"}]
    body = receipt(grn, [tea_line(grn, "650", puts=puts)], submit=True)
    done = call(store, "post", url(grn), body)
    assert done.status_code == 201, done.json()
    with use_tenant(alpha):
        told = set(Notification.objects.values_list("user__email", flat=True))
        assert {"buyer@x.in", "owner@x.in"} <= told and "stores@x.in" not in told
        mine = Notification.objects.filter(user__email="buyer@x.in")
        note = mine.get(title__startswith="Over-receipt")
        assert note.link.endswith(f"purchase-orders?view={grn['po']}&grn={done.json()['id']}")
        assert "650 kg received against 600 ordered" in note.body and "50 over" in note.body
        po_log = AuditEntry.objects.filter(record_type="purchase_order", record_id=grn["po"])
        assert any(c["field"] == "over_receipt" for e in po_log for c in e.changes)
    mine = call(buyer, "get", "notifications/").json()
    # The packets did not come with it: a second notice says so.
    assert mine["unread"] == 2
    assert {r["title"].split(" on ")[0] for r in mine["rows"]} == {"Over-receipt", "Not received"}
    call(buyer, "post", "notifications/read/", {})
    assert call(buyer, "get", "notifications/").json()["unread"] == 0


def test_cancel_reverses_stock_gl_and_the_order(owner, store, grn, alpha):  # noqa: F811
    made = call(
        store, "post", url(grn), receipt(grn, [tea_line(grn), box_line(grn)], submit=True)
    ).json()
    cancel = f"goods-receipts/{made['id']}/cancel/"
    assert call(store, "post", cancel, {"reason": "x"}).status_code == 403
    res = call(owner, "post", f"goods-receipts/{made['id']}/cancel/", {"reason": "Wrong supplier"})
    assert res.status_code == 200, res.json()
    assert res.json()["status"] == "cancelled"
    with use_tenant(alpha):
        assert gl_balance(Ledger.objects.get(pk=grn["stock"])) == 0
        assert PurchaseOrder.objects.get(pk=grn["po"]).status == PurchaseOrder.ORDERED
        assert PurchaseOrderLine.objects.get(pk=grn["tea_line"]).received_qty == 0
        assert GLEntry.objects.filter(voucher_type="goods_receipt", is_reversal=True).exists()


def test_orders_must_be_the_suppliers_and_open(store, grn, owner):  # noqa: F811
    res = call(store, "post", url(grn), receipt(grn, [], supplier=grn["far"]))
    assert "is not an order of" in str(res.json())
    draft = call(owner, "post", f"companies/{grn['company']}/purchase-orders/", order(grn)).json()
    res = call(store, "post", url(grn), receipt(grn, [], orders=[draft["id"]]))
    assert "is draft" in str(res.json())


def test_a_submitted_receipt_is_fixed_and_puts_places_in_use(store, grn, alpha):
    from core import locks

    made = call(store, "post", url(grn), receipt(grn, [box_line(grn)], submit=True)).json()
    res = call(store, "patch", f"goods-receipts/{made['id']}/", receipt(grn, [box_line(grn)]))
    assert res.status_code == 400 and "cannot be changed" in str(res.json())
    with use_tenant(alpha):
        area = WarehouseLocation.objects.get(pk=grn["area"])
        assert "1 goods receipt" in locks.uses("warehouse_location", area)
        user = User.objects.get(email="stores@x.in")
        assert AuditEntry.objects.filter(record_type="goods_receipt", user=user).exists()


def test_missing_ledgers_stop_the_submit_all_listed_and_the_draft_is_kept(store, grn, alpha):
    """Sidharth, 2026-11-17: every missing item group ledger in one popup, not an
    error at the top; the draft stays saved."""
    with use_tenant(alpha):
        ItemGroupAccount.objects.all().delete()
    lines = [tea_line(grn), box_line(grn)]
    res = call(store, "post", url(grn), receipt(grn, lines, submit=True))
    assert res.status_code == 400
    body = res.json()
    assert body["missing_accounts"] == [
        {
            "group": body["missing_accounts"][0]["group"],
            "group_name": "General",
            "missing": ["Stock Ledger", "COGS/Expense Ledger"],
            "lines": ["Line 1 CTC Tea", "Line 2 Tea Box"],
        }
    ]
    assert body["may_set"] is False  # a storekeeper may not change masters
    with use_tenant(alpha):
        draft = GoodsReceipt.objects.get(pk=body["id"])
        assert draft.status == "draft" and not GLEntry.objects.exists()
    # Submitting the saved draft is refused the same way.
    res = call(store, "post", f"goods-receipts/{draft.pk}/submit/")
    assert res.status_code == 400 and res.json()["missing_accounts"][0]["group_name"] == "General"


def test_a_missing_cogs_ledger_alone_stops_the_submit(store, owner, grn, alpha):  # noqa: F811
    with use_tenant(alpha):
        ItemGroupAccount.objects.update(cogs_ledger=None)
    draft = call(store, "post", url(grn), receipt(grn, [box_line(grn)])).json()
    res = call(owner, "post", f"goods-receipts/{draft['id']}/submit/")
    assert res.status_code == 400
    assert res.json()["missing_accounts"][0]["missing"] == ["COGS/Expense Ledger"]
    assert res.json()["may_set"] is True  # the owner may set it himself


def test_ask_to_set_notifies_those_who_may_change_masters(store, owner, grn, alpha):  # noqa: F811
    with use_tenant(alpha):
        ItemGroupAccount.objects.update(cogs_ledger=None)
        group = ItemGroupAccount.objects.get().group_id
    body = {"group": group, "document": "the goods receipt from Darjeeling Tea Traders"}
    res = call(store, "post", f"companies/{grn['company']}/ask-ledgers/", body)
    assert res.status_code == 200, res.json()
    with use_tenant(alpha):
        notes = Notification.objects.filter(title="Set ledgers on item group General")
        assert notes.exists()
        assert not notes.filter(user__email="stores@x.in").exists()
        note = notes.first()
        assert "COGS/Expense Ledger of General not set" in note.body
        assert note.link == f"#/item-groups?form={group}&at=ledgers"
        ItemGroupAccount.objects.update(
            cogs_ledger_id=ItemGroupAccount.objects.get().stock_ledger_id
        )
    again = call(store, "post", f"companies/{grn['company']}/ask-ledgers/", body)
    assert again.status_code == 400 and "set now" in str(again.json())


def test_ledger_posting_previews_a_draft_and_shows_what_was_posted(store, grn, alpha):
    lines = [tea_line(grn, "600"), box_line(grn)]
    draft = call(store, "post", url(grn), receipt(grn, lines)).json()
    preview = call(store, "get", f"goods-receipts/{draft['id']}/ledger-posting/").json()
    assert preview["posted"] is False
    rows = {r["ledger_name"]: (r["debit"], r["credit"]) for r in preview["rows"]}
    # 600 Kg at 250 + 30 at 20, plus freight 6,300 spread by quantity.
    assert rows["Stock"][0] == "156900.00"
    assert rows["Goods Received but Bills not Received"] == ("0.00", "156900.00")
    done = call(store, "post", f"goods-receipts/{draft['id']}/submit/").json()
    posted = call(store, "get", f"goods-receipts/{done['id']}/ledger-posting/").json()
    assert posted["posted"] is True and posted["reversed"] is False
    assert {r["ledger_name"]: (r["debit"], r["credit"]) for r in posted["rows"]} == rows
    assert posted["rows"][0]["group_name"] == "Stock-in-Hand"


def test_ledger_posting_preview_names_a_missing_stock_ledger(store, grn, alpha):
    with use_tenant(alpha):
        ItemGroupAccount.objects.all().delete()
    draft = call(store, "post", url(grn), receipt(grn, [box_line(grn)])).json()
    rows = call(store, "get", f"goods-receipts/{draft['id']}/ledger-posting/").json()["rows"]
    assert rows[0]["missing"] is True
    assert rows[0]["ledger_name"] == "Stock Ledger of item group General not set"


def test_bags_in_bins_get_their_own_numbers_on_submit(store, grn, alpha):
    """Sidharth's example: 5 bags of 20 in one bin, 1 bag of 10 in another."""
    puts = [
        {"location": grn["bin1"], "batch_number": "DTT-9", "qty": "0",
         "packages": 5, "package_type": "bag", "package_qty": "20"},
        {"location": grn["bin2"], "batch_number": "DTT-9", "qty": "0",
         "packages": 1, "package_type": "bag", "package_qty": "10"},
    ]  # fmt: skip
    draft = call(store, "post", url(grn), receipt(grn, [tea_line(grn, "110", puts=puts)])).json()
    first = draft["lines"][0]["putaways"][0]
    assert (first["qty"], first["packages"], first["package_type_label"]) == (
        "100.000000",
        5,
        "Bag",
    )
    assert draft["packages"] == []  # numbers come on Submit
    done = call(store, "post", f"goods-receipts/{draft['id']}/submit/").json()
    bags = done["packages"]
    assert [b["number"] for b in bags] == [f"PK-{n:06d}" for n in range(1, 7)]
    assert [(b["location_name"], b["qty"]) for b in bags[4:]] == [
        ("F01 / A-02", "20.000000"),
        ("F01 / A-06", "10.000000"),
    ]
    assert (bags[5]["batch"], bags[5]["position"], bags[5]["of_count"]) == ("DTT-9", 6, 6)
    assert {b["status_label"] for b in bags} == {"In stock"}

    # The next receipt carries on the numbers; a cancelled one keeps its bags as "Cancelled".
    more = [{"location": grn["bin1"], "batch_number": "DTT-9", "qty": "0",
             "packages": 2, "package_type": "bag", "package_qty": "20"}]  # fmt: skip
    second = call(
        store, "post", url(grn), receipt(grn, [tea_line(grn, "40", puts=more)], submit=True)
    )
    assert [b["number"] for b in second.json()["packages"]] == ["PK-000007", "PK-000008"]
    boss = client_for(alpha, "boss@x.in", "owner")
    gone = call(boss, "post", f"goods-receipts/{second.json()['id']}/cancel/", {"reason": "Wrong"})
    assert {b["status_label"] for b in gone.json()["packages"]} == {"Cancelled"}


def test_packages_need_all_three_figures(store, grn):
    puts = [{"location": grn["bin1"], "batch_number": "B1", "qty": "600", "packages": 5}]
    res = call(store, "post", url(grn), receipt(grn, [tea_line(grn, puts=puts)]))
    assert "number of packages, the package and the quantity in each" in str(res.json())


def test_the_print_brings_the_letterhead_and_a_bin_shows_its_bags(store, grn, alpha):
    puts = [
        {"location": grn["bin1"], "batch_number": "DTT-7", "qty": "0",
         "packages": 3, "package_type": "bag", "package_qty": "20"},
    ]  # fmt: skip
    body = receipt(grn, [tea_line(grn, "60", puts=puts)], submit=True)
    done = call(store, "post", url(grn), body).json()
    plain = call(store, "get", f"goods-receipts/{done['id']}/").json()
    assert "letterhead" not in plain
    printed = call(store, "get", f"goods-receipts/{done['id']}/?print=1").json()
    assert printed["letterhead"]["name"] and printed["supplier_place"]["name"]
    assert printed["packages"][0]["seq"] == 1 and printed["packages"][0]["location"] == grn["bin1"]

    there = call(store, "get", f"bins/{grn['bin1']}/").json()
    assert there["code"] == f"LOC-{grn['bin1']:06d}" and there["name"] == "F01 / A-02"
    assert [(s["item_name"], s["batch"], s["qty"]) for s in there["stock"]] == [
        ("CTC Tea", "DTT-7", "60.000000")
    ]
    assert [k["number"] for k in there["packages"]] == ["PK-000001", "PK-000002", "PK-000003"]
    rack = call(store, "get", f"bins/{grn['rack']}/").json()  # a rack shows its bins
    assert len(rack["packages"]) == 3
    assert call(store, "get", "bins/999999/").status_code == 404


def test_a_qr_code_comes_as_a_picture(store):
    res = call(store, "get", "qr/?text=https://x.in/%23/bins/3")
    assert res["Content-Type"] == "image/svg+xml"
    assert res.content.startswith(b"<svg") and b"<path" in res.content
    assert call(store, "get", "qr/").status_code == 400


def test_short_and_missing_lines_are_told_and_a_line_can_be_closed(store, buyer, grn, alpha):  # noqa: F811
    puts = [{"location": grn["bin1"], "batch_number": "B1", "qty": "400"}]
    done = call(
        store, "post", url(grn), receipt(grn, [tea_line(grn, "400", puts=puts)], submit=True)
    )
    assert done.status_code == 201, done.json()
    with use_tenant(alpha):
        mine = Notification.objects.filter(user__email="buyer@x.in")
        short = mine.get(title__startswith="Short receipt")
        assert "400 kg received against 600 ordered" in short.body and "200 short" in short.body
        missing = mine.get(title__startswith="Not received")
        assert "none came with" in missing.body and "(30 " in missing.body
        logged = AuditEntry.objects.filter(record_type="purchase_order", record_id=grn["po"])
        fields = {c["field"] for e in logged for c in e.changes}
        assert {"short_receipt", "not_received"} <= fields

    close = f"purchase-orders/{grn['po']}/lines/{grn['tea_line']}/close/"
    assert call(store, "post", close, {"reason": "x"}).status_code == 403
    res = call(buyer, "post", close, {"reason": " "})
    assert "Say why" in str(res.json())
    po = call(buyer, "post", close, {"reason": "Supplier will not send balance"}).json()
    tea = po["lines"][0]
    assert (
        tea["closed_at"]
        and tea["pending_qty"] == "0"
        and tea["close_reason"].startswith("Supplier")
    )
    assert po["status"] == "part_received"  # the packets are still to come
    box = f"purchase-orders/{grn['po']}/lines/{grn['box_line']}/close/"
    po = call(buyer, "post", box, {"reason": "Not needed"}).json()
    assert po["status"] == "closed"
    # A closed line is no longer offered to the next receipt.
    pending = call(store, "get", f"companies/{grn['company']}/goods-receipts/pending/").json()
    assert all(o["id"] != grn["po"] for o in pending) or not any(
        o["lines"] for o in pending if o["id"] == grn["po"]
    )
    po = call(buyer, "post", close, {"reopen": True}).json()
    assert po["lines"][0]["closed_at"] is None and po["lines"][0]["pending_qty"] == "200"
    assert po["status"] == "part_received"
    with use_tenant(alpha):
        logged = AuditEntry.objects.filter(record_type="purchase_order", record_id=grn["po"])
        assert any("200 kg not coming" in str(c["new"]) for e in logged for c in e.changes)


def test_a_line_on_a_draft_receipt_cannot_be_closed(store, buyer, grn):  # noqa: F811
    assert call(store, "post", url(grn), receipt(grn, [tea_line(grn)])).status_code == 201
    close = f"purchase-orders/{grn['po']}/lines/{grn['tea_line']}/close/"
    res = call(buyer, "post", close, {"reason": "No more"})
    assert res.status_code == 400 and "draft goods receipt" in str(res.json())


def test_received_by_and_qc_by_are_stores_people(store, owner, grn, alpha):  # noqa: F811
    """Received By and QC By pick from Masters > People ticked "Stores", signed in
    or not (Sidharth, 2026-11-17, preview 88)."""
    with use_tenant(alpha):
        ramesh = SalesPerson.objects.create(name="Ramesh", is_stores=True).pk
        sunil = SalesPerson.objects.create(name="Sunil", is_stores=True, is_active=False).pk
        amit = SalesPerson.objects.create(name="Amit", is_purchaser=True).pk
    setup = call(store, "get", f"companies/{grn['company']}/goods-receipts/setup/").json()
    assert {p["name"] for p in setup["stores_people"]} == {"Ramesh", "Sunil"}

    # A purchaser is not on the list, nor is a disabled stores person.
    for bad in (amit, sunil):
        refused = call(store, "post", url(grn), receipt(grn, [tea_line(grn)], received_by=bad))
        assert refused.status_code == 400 and "received_by" in refused.json()

    made = call(
        store, "post", url(grn), receipt(grn, [tea_line(grn)], received_by=ramesh, qc_by=ramesh)
    )
    assert made.status_code == 201, made.json()
    body = made.json()
    assert body["received_by_name"] == "Ramesh" and body["qc_by_name"] == "Ramesh"

    # Named on a receipt: stays ticked Stores.
    untick = call(
        owner, "patch", f"sales-people/{ramesh}/", {"is_stores": False, "is_purchaser": True}
    )
    assert untick.status_code == 400 and "is_stores" in untick.json()
