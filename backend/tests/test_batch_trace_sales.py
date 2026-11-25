"""Batch Trace of a sold batch: the customer, order, invoice and sales return
(Sidharth, 2026-11-25; see test_batch_trace.py)."""

import pytest

from core.models import Batch
from tenancy.context import use_tenant
from tests.test_credit_notes import billed
from tests.test_delivery_notes import books  # noqa: F401
from tests.test_sales_orders import call, owner, seller, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def batch_id(tenant, number):
    with use_tenant(tenant):
        return Batch.objects.get(number=number).pk


def test_a_sold_batch_names_the_customer_order_invoice_and_return(seller, owner, books):  # noqa: F811
    w = books
    inv = billed(seller, w)  # 300 packets of A-LATE in; 10 cartons (240) sent and billed
    made = call(seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "goods_back"})
    note = made.json()
    [line] = note["lines"]
    body = {"kind": note["kind"], "reason": note["reason"], "note_date": note["note_date"]}
    call(
        seller,
        "patch",
        f"credit-notes/{note['id']}/",
        {**body, "lines": [{"id": line["id"], "qty": "2"}]},
    )
    cn = call(seller, "post", f"credit-notes/{note['id']}/submit/", {})
    assert cn.status_code == 200, cn.json()

    t = call(owner, "get", f"batches/{batch_id(w['tenant'], 'A-LATE')}/trace/").json()
    [came] = t["came_from"]
    assert came["qty"] == "300" and came["party"] is None
    out, back = t["went"]
    assert out["entry"]["page"] == "delivery-notes" and out["qty"] == "240"
    assert out["party"]["name"] == "Organic Harvest Foods"
    assert [b["number"] for b in out["bills"]] == [inv["number"]]
    assert out["orders"][0]["page"] == "sales-orders" and out["note"].startswith("Pick List ")
    assert back["entry"]["number"] == cn.json()["number"] and back["back"] == "48"
    assert [(c["name"], c["qty"], c["entries"]) for c in t["customers"]] == [
        ("Organic Harvest Foods", "192", 2)
    ]
    assert t["balance"] == {
        "received": "300",
        "sent": "240",
        "back": "48",
        "moved": "0",
        "in_stock": "108",
        "held": "0",
    }
