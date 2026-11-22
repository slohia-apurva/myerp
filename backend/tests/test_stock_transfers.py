"""Stock Transfer (Sidharth, 2026-11-22, preview 9a in mockups/planning): goods
leave the From branch's bins at FIFO cost on Dispatch and sit in the To
branch's In Transit place at the same value, with nothing in the books; on
Receive they go into To's bins, and a shortfall is a transit loss (Dr Stock
Adjustment, Cr Stock). Only between branches with the same GSTIN."""

import datetime
from decimal import Decimal

import pytest

from buying import planning
from core.models import Branch, Item, Package, WarehouseLocation
from posting.models import GLEntry, StockLot, StockMove
from selling import stock
from tenancy.context import use_tenant
from tests.test_delivery_notes import books  # noqa: F401  (fixture)
from tests.test_pick_lists import receive
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    client_for,
    gstin,
    owner,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

LATER = TODAY + datetime.timedelta(days=200)


@pytest.fixture
def stores(alpha):
    return client_for(alpha, "stores@x.in", "storekeeper")


@pytest.fixture
def depot(books):  # noqa: F811
    """A second branch of the same company, same GSTIN, with a store."""
    w = books
    with use_tenant(w["tenant"]):
        head = Branch.objects.get(pk=w["branch"])
        b = Branch.objects.create(
            company=head.company, name="Kolkata Depot", state_code=head.state_code,
            gstin=head.gstin,
        )  # fmt: skip
        store = WarehouseLocation.objects.create(
            branch=b, kind=WarehouseLocation.AREA, name="Main Store", purpose="storage",
            is_default=True,
        )  # fmt: skip
    return {**w, "depot": b.pk, "depot_store": store.pk}


def url(w):
    return f"companies/{w['company']}/stock-transfers/"


def body(w, qty="5", **more):
    return {
        "from_branch": w["branch"],
        "from_area": w["fg"],
        "to_branch": w["depot"],
        "transfer_date": TODAY.isoformat(),
        "vehicle_no": "wb 23 c 4410",
        "eway_bill_no": "3412 5566 7781",
        "lines": [{"item": w["tea"], "unit": w["case"], "qty": qty}],
        **more,
    }


def moves(w, kind, pk):
    with use_tenant(w["tenant"]):
        rows = StockMove.objects.filter(voucher_type=kind, voucher_id=pk).order_by("id")
        return [(m.branch_id, m.location.name, m.qty, m.value) for m in rows]


def test_draft_dispatch_receive(stores, owner, depot):  # noqa: F811
    w = depot
    receive(w, w["bin"], "100", "A-SOON", TODAY + datetime.timedelta(days=60))
    receive(w, w["bin"], "200", "A-LATE", LATER)  # both at 10 a packet
    made = call(stores, "post", url(w), body(w))  # 5 cartons = 120 packets
    assert made.status_code == 201, made.json()
    t = made.json()
    assert t["status"] == "draft" and t["number"] == "" and t["vehicle_no"] == "WB23C4410"
    # Picked by the rule: earliest expiry first.
    picked = [(b["batch_number"], b["qty"]) for b in t["lines"][0]["bins"]]
    assert picked == [("A-SOON", "100"), ("A-LATE", "20")]
    # A draft counts in the Stock Check: Reserved at From, Incoming at To.
    with use_tenant(w["tenant"]):
        head, dep = Branch.objects.get(pk=w["branch"]), Branch.objects.get(pk=w["depot"])
        assert planning.reserved(head, [w["tea"]])[w["tea"]] == 120
        assert planning.incoming(dep, [w["tea"]])[w["tea"]] == 120
    sent = call(stores, "post", f"stock-transfers/{t['id']}/dispatch/", {})
    assert sent.status_code == 200, sent.json()
    t = sent.json()
    assert t["status"] == "in_transit" and "/ST/" in t["number"] and t["value"] == "1200.00"
    assert moves(w, "stock_transfer", t["id"]) == [
        (w["branch"], "FG-R1-B1", Decimal("-100"), Decimal("-1000.00")),
        (w["branch"], "FG-R1-B1", Decimal("-20"), Decimal("-200.00")),
    ]
    assert moves(w, "stock_transfer_in", t["id"]) == [
        (w["depot"], "In Transit", Decimal("100"), Decimal("1000.00")),
        (w["depot"], "In Transit", Decimal("20"), Decimal("200.00")),
    ]
    with use_tenant(w["tenant"]):
        # Nothing in the books on Dispatch.
        assert not GLEntry.objects.filter(voucher_id=t["id"], voucher_type__startswith="stock_t")
        head, dep = Branch.objects.get(pk=w["branch"]), Branch.objects.get(pk=w["depot"])
        tea = Item.objects.get(pk=w["tea"])
        # In transit is not stock the depot can use, but it is Incoming.
        assert stock.on_hand([tea], dep).get(tea.pk, 0) == 0
        assert stock.on_hand([tea], head)[tea.pk] == 180
        assert planning.reserved(head, [tea.pk]).get(tea.pk, 0) == 0
        assert planning.incoming(dep, [tea.pk])[tea.pk] == 120
    assert "cannot be changed" in str(
        call(stores, "patch", f"stock-transfers/{t['id']}/", body(w)).json()
    )
    # Receive: 10 packets of A-LATE short.
    where = call(stores, "get", f"stock-transfers/{t['id']}/receive/").json()
    assert where["default"] == w["depot_store"]
    assert "In Transit" not in [p["label"] for p in where["places"]]
    rows = [
        {"bin": b["id"], "received_qty": b["qty"] if b["batch_number"] == "A-SOON" else "10"}
        for b in t["lines"][0]["bins"]
    ]
    path = f"stock-transfers/{t['id']}/receive/"
    day = {"received_date": TODAY.isoformat(), "rows": rows}
    assert "say why" in str(call(stores, "post", path, day).json())
    got = call(stores, "post", path, {**day, "shortfall_reason": "Wet in the truck"})
    assert got.status_code == 200, got.json()
    t = got.json()
    assert t["status"] == "received" and t["shortfall_value"] == "100.00"
    assert t["lines"][0]["received"] == "4.583"  # 110 packets in cartons
    assert moves(w, "stock_transfer_receipt", t["id"]) == [
        (w["depot"], "In Transit", Decimal("-100"), Decimal("-1000.00")),
        (w["depot"], "In Transit", Decimal("-20"), Decimal("-200.00")),
        (w["depot"], "Main Store", Decimal("100"), Decimal("1000.00")),
        (w["depot"], "Main Store", Decimal("10"), Decimal("100.00")),
    ]
    with use_tenant(w["tenant"]):
        rows = GLEntry.objects.filter(voucher_type="stock_transfer_receipt", voucher_id=t["id"])
        assert {(e.ledger.name, e.debit, e.credit) for e in rows} == {
            ("Stock Adjustment", Decimal("100.00"), Decimal("0.00")),
            ("Stock", Decimal("0.00"), Decimal("100.00")),
        }
        dep = Branch.objects.get(pk=w["depot"])
        assert stock.on_hand([w["tea"]], dep)[w["tea"]] == 110
        assert planning.incoming(dep, [w["tea"]]).get(w["tea"], 0) == 0
        # The depot's lots carry the head office's cost.
        lots = StockLot.objects.filter(branch=dep, qty_left__gt=0)
        assert sorted(lot.value_left for lot in lots) == [Decimal("100.00"), Decimal("1000.00")]
    posting = call(stores, "get", f"stock-transfers/{t['id']}/stock-posting/").json()
    assert [s["step"] for s in posting["steps"]] == ["Dispatch", "Receive"]
    assert "Stock Adjustment" in posting["steps"][1]["books"]
    challan = call(stores, "get", f"stock-transfers/{t['id']}/pdf/")
    assert challan.status_code == 200 and challan["Content-Type"] == "application/pdf"
    refused = call(owner, "post", f"stock-transfers/{t['id']}/cancel/", {"reason": "x"})
    assert "Send the goods back" in str(refused.json())


def test_cancel_in_transit_puts_goods_back(stores, owner, depot):  # noqa: F811
    w = depot
    receive(w, w["bin"], "300", "A-LATE", LATER)
    t = call(stores, "post", url(w), body(w, dispatch=True)).json()
    assert t["status"] == "in_transit", t
    gone = call(owner, "post", f"stock-transfers/{t['id']}/cancel/", {"reason": "Truck broke"})
    assert gone.status_code == 200, gone.json()
    assert gone.json()["status"] == "cancelled"
    with use_tenant(w["tenant"]):
        head, dep = Branch.objects.get(pk=w["branch"]), Branch.objects.get(pk=w["depot"])
        assert stock.on_hand([w["tea"]], head)[w["tea"]] == 300
        transit = WarehouseLocation.objects.get(branch=dep, purpose="transit")
        assert not transit.is_active
        held = StockMove.objects.filter(location=transit).values_list("qty", flat=True)
        assert sum(held) == 0


def test_short_stock_and_other_gstin_are_refused(stores, depot):  # noqa: F811
    w = depot
    receive(w, w["bin"], "50", "A-LATE", LATER)
    t = call(stores, "post", url(w), body(w)).json()  # 120 wanted, 50 there
    assert t["lines"][0]["picked"] == "2.083" and t["lines"][0]["short_picked"]
    no = call(stores, "post", f"stock-transfers/{t['id']}/dispatch/", {})
    assert no.status_code == 400
    assert "only 2.083 ctn is free" in no.json()["problems"][0]["text"]
    with use_tenant(w["tenant"]):
        head = Branch.objects.get(pk=w["branch"])
        other = Branch.objects.create(
            company=head.company, name="Mumbai", state_code="27",
            gstin=gstin("27", "AAPFA9999F"),
        )  # fmt: skip
    refused = call(stores, "post", url(w), body({**w, "depot": other.pk}))
    assert refused.status_code == 400 and "different GSTINs" in str(refused.json())
    same = call(stores, "post", url(w), body({**w, "depot": w["branch"]}))
    assert "different branch" in str(same.json())


def test_whole_package_moves_with_the_goods(stores, depot):  # noqa: F811
    w = depot
    receive(w, w["bin"], "24", "A-LATE", LATER)
    with use_tenant(w["tenant"]):
        tea = Item.objects.get(pk=w["tea"])
        bin_ = WarehouseLocation.objects.get(pk=w["bin"])
        pk = Package.objects.create(
            company_id=w["company"], seq=1, number="PK-000001", kind="box", item=tea,
            batch=tea.batches.get(number="A-LATE"), location=bin_, qty=24, left_qty=24,
            voucher_type="test", voucher_id=1, voucher_number="T", position=1, of_count=1,
        )  # fmt: skip
    t = call(stores, "post", url(w), body(w, qty="1", dispatch=True)).json()
    assert t["status"] == "in_transit" and t["lines"][0]["bins"][0]["whole_package"]
    with use_tenant(w["tenant"]):
        assert Package.objects.get(pk=pk.pk).location.name == "In Transit"
    rows = [{"bin": t["lines"][0]["bins"][0]["id"], "received_qty": "24"}]
    day = {"received_date": TODAY.isoformat(), "rows": rows}
    assert call(stores, "post", f"stock-transfers/{t['id']}/receive/", day).status_code == 200
    with use_tenant(w["tenant"]):
        assert Package.objects.get(pk=pk.pk).location_id == w["depot_store"]


def test_rights(alpha, depot):  # noqa: F811
    w = depot
    seller = client_for(alpha, "s2@x.in", "sales")
    assert call(seller, "get", url(w)).status_code == 200  # sales may view stock
    assert call(seller, "post", url(w), body(w)).status_code == 403
