"""Batch Trace (Sidharth, 2026-11-25, preview mockups/batch-trace/1): where a
batch came from, where it is now and where it went, read from the stock ledger,
for recall. The retention sample label QR opens #/batches/<id>/trace."""

import pytest

from accounts.models import Role
from core.models import Batch, Item, Ledger, PartyContact
from posting.trace import _ranges
from tenancy.context import use_tenant
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_orders import buyer, call, client_for, owner, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def batch_id(tenant, number):
    with use_tenant(tenant):
        return Batch.objects.get(number=number).pk


def test_bag_numbers_fold_into_ranges():
    assert _ranges([]) == ""
    assert _ranges(["PK-000003", "PK-000001", "PK-000002", "PK-000007"]) == (
        "PK-000001 to PK-000003, PK-000007 (4)"
    )


def test_a_received_batch_shows_supplier_order_bins_and_bags(store, owner, grn, alpha):  # noqa: F811
    puts = [
        {"location": grn["bin1"], "batch_number": "DTT-26-118", "qty": "0",
         "packages": 15, "package_type": "bag", "package_qty": "20"},
        {"location": grn["bin2"], "batch_number": "DTT-26-118", "qty": "300"},
    ]  # fmt: skip
    # A first receipt of the batch, cancelled: it nets to nothing and is left out.
    more = [{"location": grn["bin1"], "batch_number": "DTT-26-118", "mfg_date": "2026-11-02",
             "qty": "40"}]  # fmt: skip
    first = call(
        store, "post", url(grn), receipt(grn, [tea_line(grn, "40", puts=more)], submit=True)
    )
    assert first.status_code == 201, first.json()
    gone = call(owner, "post", f"goods-receipts/{first.json()['id']}/cancel/", {"reason": "Wrong"})
    assert gone.status_code == 200, gone.json()
    lines = [tea_line(grn, puts=puts), box_line(grn)]
    done = call(store, "post", url(grn), receipt(grn, lines, submit=True))
    assert done.status_code == 201, done.json()
    with use_tenant(alpha):
        party = Ledger.objects.get(pk=grn["local"]).party
        PartyContact.objects.create(party=party, name="Ravi", phone="9820012345", is_primary=True)

    got = call(owner, "get", f"batches/{batch_id(alpha, 'DTT-26-118')}/trace/")
    assert got.status_code == 200, got.json()
    t = got.json()
    assert (t["batch"]["number"], t["batch"]["mfg_date"], t["unit"]) == (
        "DTT-26-118",
        "2026-11-02",
        "kg",
    )
    [came] = t["came_from"]
    assert came["entry"]["number"] == done.json()["number"]
    assert (came["entry"]["page"], came["entry"]["company"]) == ("goods-receipts", grn["company"])
    assert came["party"]["name"] == "Darjeeling Tea Traders"
    assert came["party"]["contact"] == "Ravi · 9820012345"
    assert [o["number"] for o in came["orders"]] == [grn["po_number"]]
    assert came["orders"][0]["page"] == "purchase-orders"
    assert came["qty"] == "600"
    assert t["went"] == [] and t["customers"] == []
    assert [(n["location_name"], n["qty"], n["bags"]) for n in t["now"]] == [
        ("A-02", "300", "PK-000001 to PK-000015 (15)"),
        ("A-06", "300", ""),
    ]
    assert t["balance"]["received"] == "600" and t["balance"]["in_stock"] == "600"
    # Every move is listed, the cancelled receipt and its reversal too.
    assert len(t["moves"]) == 4 and t["moves"][-1]["balance"] == "600"


def test_trace_needs_the_right_to_see_stock(owner, grn, alpha):  # noqa: F811
    with use_tenant(alpha):
        tea = Item.objects.get(pk=grn["tea"])
        b = Batch.objects.create(item=tea, number="X1")
    assert call(owner, "get", f"batches/{b.pk}/trace/").status_code == 200
    assert call(owner, "get", "batches/999999/trace/").status_code == 404
    with use_tenant(alpha):
        Role.objects.create(code="lister", name="Lister", permissions=["masters.view"])
    lister = client_for(alpha, "lister@x.in", "lister")
    assert call(lister, "get", f"batches/{b.pk}/trace/").status_code == 403
