"""Stock Receipt and Stock Delivery of a customer's own goods (Sidharth,
2026-11-22, preview 9c in mockups/planning): only items marked "Customer
Provided", quantity only (nothing in the books), held as that customer's stock
and never mixed with ours or another customer's."""

import datetime
from decimal import Decimal

import pytest

from core.models import Batch, Branch, Item, ItemUnit, Package, SalesPerson, Unit
from posting.models import GLEntry, StockMove
from tenancy.context import use_tenant
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    owner,
    world,
)
from tests.test_stock_transfers import stores  # noqa: F401  (fixture)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture
def goods(world):  # noqa: F811
    """Organic Harvest Foods' own tea (kept in batches) and pouches."""
    w = world
    with use_tenant(w["tenant"]):
        tea = Item.objects.get(pk=w["tea"])
        kg, nos = Unit.objects.get(name="Kilogram"), Unit.objects.get(name="Packet")
        more = {"hsn": "0902", "item_group": tea.item_group, "brand": tea.brand}
        ctc = Item.objects.create(
            item_number="ITEM-91", name="OHF Assam CTC", stock_unit=kg, batch_tracked=True,
            default_request_type=Item.CUSTOMER_PROVIDED, **more,
        )  # fmt: skip
        ItemUnit.objects.create(item=ctc, unit=kg, factor=1)
        pouch = Item.objects.create(
            item_number="ITEM-92", name="OHF Pouch 100 g", stock_unit=nos,
            default_request_type=Item.CUSTOMER_PROVIDED, **{**more, "hsn": "3923"},
        )  # fmt: skip
        ItemUnit.objects.create(item=pouch, unit=nos, factor=1, whole_numbers=True)
        ravi = SalesPerson.objects.create(name="Ravi Stores", is_stores=True)
    more = {"kgu": kg.pk, "nos": nos.pk, "stores_ravi": ravi.pk}
    return {**w, "ctc": ctc.pk, "pouch": pouch.pk, **more}


def url(w):
    return f"companies/{w['company']}/customer-stock/"


def receipt(w, customer="local", **more):
    return {
        "kind": "receipt",
        "customer": w[customer],
        "branch": w["branch"],
        "entry_date": TODAY.isoformat(),
        "challan_no": "OHF/DC/118",
        "challan_date": (TODAY - datetime.timedelta(days=2)).isoformat(),
        "reason": "Tea for packing, job work order JW-14",
        "vehicle_no": "wb 11 a 2290",
        "stores_person": w["stores_ravi"],
        "lines": [
            {
                "item": w["ctc"],
                "unit": w["kgu"],
                "qty": "1250",
                "location": w["bin"],
                "batch_number": "OHF-2611-A",
                "bags": 50,
            },
            {"item": w["pouch"], "unit": w["nos"], "qty": "12000", "location": w["bin"], "bags": 6},
        ],  # fmt: skip
        **more,
    }


def delivery(w, qty="250", customer="local", **more):
    return {
        "kind": "delivery",
        "customer": w[customer],
        "branch": w["branch"],
        "entry_date": TODAY.isoformat(),
        "reason": "Not needed, sent back",
        "lines": [{"item": w["ctc"], "unit": w["kgu"], "qty": qty}],
        **more,
    }


def test_receipt_holds_the_customers_goods(stores, goods):  # noqa: F811
    w = goods
    made = call(stores, "post", url(w), receipt(w))
    assert made.status_code == 201, made.json()
    e = made.json()
    assert e["status"] == "draft" and e["vehicle_no"] == "WB11A2290"
    assert e["transporter_name"] == "By Customer"
    done = call(stores, "post", f"customer-stock/{e['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    e = done.json()
    assert e["status"] == "submitted" and "/SR/" in e["number"]
    assert len(e["packages"]) == 56 and e["packages"][0]["qty"] == "25"
    with use_tenant(w["tenant"]):
        moves = StockMove.objects.filter(voucher_type="stock_receipt", voucher_id=e["id"])
        assert {(m.item_id, m.qty, m.valued, m.value) for m in moves} == {
            (w["ctc"], Decimal("1250"), False, Decimal("0")),
            (w["pouch"], Decimal("12000"), False, Decimal("0")),
        }
        assert {m.owner.ledgers.first().pk for m in moves} == {w["local"]}
        assert Batch.objects.get(item=w["ctc"]).number == "OHF-2611-A"
        assert not GLEntry.objects.filter(voucher_id=e["id"], voucher_type="stock_receipt")
    # The delivery form shows what the customer holds; another customer holds nothing.
    form = f"companies/{w['company']}/customer-stock/form/?branch={w['branch']}"
    mine = call(stores, "get", f"{form}&customer={w['local']}").json()
    assert next(i for i in mine["items"] if i["id"] == w["ctc"])["held"] == "1250"
    other = call(stores, "get", f"{form}&customer={w['far']}").json()
    assert next(i for i in other["items"] if i["id"] == w["ctc"])["held"] == "0"
    assert w["tea"] not in [i["id"] for i in mine["items"]]  # our own goods are not offered
    pdf = call(stores, "get", f"customer-stock/{e['id']}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"


def test_delivery_takes_only_that_customers_stock(stores, owner, goods):  # noqa: F811
    w = goods
    r = call(stores, "post", url(w), receipt(w, submit=True)).json()
    assert r["status"] == "submitted", r
    # Another customer cannot take Organic Harvest Foods' tea.
    theirs = call(stores, "post", url(w), delivery(w, customer="far", submit=True))
    assert theirs.status_code == 400
    assert "Bengal Tea Traders has only 0 kg free" in theirs.json()["problems"][0]["text"]
    d = call(stores, "post", url(w), delivery(w)).json()
    [line] = d["lines"]
    # Whole bags (25 kg each) picked by their numbers.
    assert [(b["batch_number"], b["qty"]) for b in line["bins"]] == [("OHF-2611-A", "25")] * 10
    assert line["bins"][0]["package_number"] == "PK-000001"
    sent = call(stores, "post", f"customer-stock/{d['id']}/submit/", {})
    assert sent.status_code == 200, sent.json()
    d = sent.json()
    assert "/SD/" in d["number"]
    with use_tenant(w["tenant"]):
        held = StockMove.objects.filter(item=w["ctc"], owner__isnull=False)
        assert sum(m.qty for m in held) == Decimal("1000")
        bags = Package.objects.filter(voucher_type="stock_receipt", status="used_up")
        assert bags.count() == 10
    # The receipt cannot be cancelled while its goods are out; the delivery can.
    stuck = call(owner, "post", f"customer-stock/{r['id']}/cancel/", {"reason": "Wrong"})
    assert stuck.status_code == 400
    back = call(owner, "post", f"customer-stock/{d['id']}/cancel/", {"reason": "Kept"})
    assert back.status_code == 200, back.json()
    gone = call(owner, "post", f"customer-stock/{r['id']}/cancel/", {"reason": "Wrong"})
    assert gone.status_code == 200, gone.json()
    with use_tenant(w["tenant"]):
        assert sum(m.qty for m in StockMove.objects.filter(item=w["ctc"])) == 0
        assert not Package.objects.filter(voucher_type="stock_receipt").exclude(status="cancelled")


def test_only_customer_provided_items(stores, goods):  # noqa: F811
    w = goods
    ours = receipt(w, lines=[{"item": w["tea"], "unit": w["pcs"], "qty": "10"}])
    refused = call(stores, "post", url(w), ours)
    assert refused.status_code == 400 and "Customer Provided" in str(refused.json())
    no_batch = receipt(w, lines=[{"item": w["ctc"], "unit": w["kgu"], "qty": "10"}], submit=True)
    asked = call(stores, "post", url(w), no_batch)
    assert asked.status_code == 400 and "give the batch" in asked.json()["problems"][0]["text"]


def test_customer_goods_stay_off_stock_transfers(stores, goods):  # noqa: F811
    w = goods
    with use_tenant(w["tenant"]):
        head = Branch.objects.get(pk=w["branch"])
        depot = Branch.objects.create(
            company=head.company, name="Kolkata Depot", state_code=head.state_code,
            gstin=head.gstin,
        )  # fmt: skip
    body = {
        "from_branch": w["branch"], "to_branch": depot.pk, "transfer_date": TODAY.isoformat(),
        "lines": [{"item": w["ctc"], "unit": w["kgu"], "qty": "1"}],
    }  # fmt: skip
    refused = call(stores, "post", f"companies/{w['company']}/stock-transfers/", body)
    assert refused.status_code == 400 and "customer's own goods" in str(refused.json())
