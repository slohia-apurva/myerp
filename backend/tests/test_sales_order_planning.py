"""Sales order Submit plans its shortages (Sidharth, 2026-11-21): an item the
branch buys that falls below its safety stock gets a draft purchase order,
one per supplier, linked to the order; items to make are noted; Submit never
fails because of it, and "Purchase Orders for Shortages" never orders twice."""

from decimal import Decimal

import pytest

from buying.models import PurchaseOrder
from core.models import Item, ItemPlan
from tenancy.context import use_tenant
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    call,
    order,
    owner,
    seller,
    stock_in,
    url,
    world,
)
from tests.test_stock_check import planned  # noqa: F401  (fixture)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def submit(client, w, cartons: str) -> dict:
    lines = [{"item": w["tea"], "unit": w["case"], "qty": cartons, "rate": "2280"}]
    response = call(client, "post", url(w), order(w, lines=lines, submit=True))
    assert response.status_code == 201, response.json()
    return response.json()


def test_submit_makes_a_draft_po_for_the_shortage_once(seller, planned):  # noqa: F811
    w = planned
    stock_in(w, "fg", "420")
    so = submit(seller, w, "25")  # 600 Packets out: Expected -180, safety 600
    [po] = so["purchase_orders"]
    assert po["status"] == "draft" and po["supplier_name"] == "Leaf Supplier"
    with use_tenant(w["tenant"]):
        made = PurchaseOrder.objects.get(pk=po["id"])
        assert made.sales_order_id == so["id"]
        assert [(ln.qty, ln.rate) for ln in made.lines.all()] == [
            (Decimal("120"), Decimal("2040"))
        ]  # refill to 2,400: 2,580 Packets, up to whole steps of 24 Cartons
        assert so["number"] in made.notes
    [line] = so["lines"]
    assert line["expected"] == "-7.5"  # -180 Packets in Cartons
    assert line["cover"] == {
        "kind": "po",
        "text": "Draft PO",
        "order": po["id"],
        "supplier": "Leaf Supplier",
    }
    [note] = so["shortages"]
    assert (note["action"], note["qty"], note["unit_name"]) == ("po", "120", "ctn")

    again = call(seller, "post", f"sales-orders/{so['id']}/plan/", {})
    assert again.status_code == 200, again.json()
    assert len(again.json()["purchase_orders"]) == 1  # the draft is Incoming now


def test_main_fulfilment_purchase_buys_the_shortage_only(seller, planned):  # noqa: F811
    w = planned
    with use_tenant(w["tenant"]):
        ItemPlan.objects.filter(item_id=w["tea"]).delete()
    stock_in(w, "fg", "100")
    so = submit(seller, w, "10")  # 240 Packets out: 140 short = 5.8 Cartons, MOQ 24
    [po] = so["purchase_orders"]
    with use_tenant(w["tenant"]):
        [ln] = PurchaseOrder.objects.get(pk=po["id"]).lines.all()
        assert ln.qty == Decimal("24")


def test_enough_stock_orders_nothing(seller, planned):  # noqa: F811
    w = planned
    stock_in(w, "fg", "3000")
    so = submit(seller, w, "25")
    assert so["purchase_orders"] == []
    assert so["lines"][0]["cover"]["kind"] == "ok"


def test_items_to_make_or_without_supplier_are_noted_and_submit_goes_on(seller, planned):  # noqa: F811
    w = planned
    with use_tenant(w["tenant"]):
        ItemPlan.objects.filter(item_id=w["tea"]).update(fulfilment=ItemPlan.MANUFACTURE)
    so = submit(seller, w, "25")
    assert so["status"] == "ordered" and so["purchase_orders"] == []
    assert so["lines"][0]["cover"] == {"kind": "make", "text": "To make 125", "order": None}

    with use_tenant(w["tenant"]):
        ItemPlan.objects.filter(item_id=w["tea"]).update(fulfilment=ItemPlan.PURCHASE)
        Item.objects.filter(pk=w["tea"]).update(preferred_supplier=None)
    so = submit(seller, w, "1")
    assert so["status"] == "ordered" and so["purchase_orders"] == []
    assert so["lines"][0]["cover"]["kind"] == "no_supplier"
