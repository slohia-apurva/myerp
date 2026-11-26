# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Connections along the sales chain (see test_connections.py)."""

import pytest

from tests.test_connections import _found
from tests.test_credit_notes import billed
from tests.test_delivery_notes import books  # noqa: F401
from tests.test_sales_orders import call as scall
from tests.test_sales_orders import owner, seller, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _conn(client, company, kind, pk, caller=scall):
    got = caller(client, "get", f"companies/{company}/connections/{kind}/{pk}/")
    assert got.status_code == 200, got.json()
    return got.json()


def test_the_sales_chain_is_seen_from_each_entry(seller, books):
    w = books
    inv = billed(seller, w)
    made = scall(
        seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "goods_back"}
    ).json()
    co = w["company"]

    si = _conn(seller, co, "sales_invoice", inv["id"], scall)
    found = _found(si)
    assert len(found["sales_order"]) == 1 and len(found["delivery_note"]) == 1
    assert len(found["pick_list"]) == 1
    assert found["credit_note"] == [""]  # a draft has no number yet
    assert "later:Receipt" in found
    [cn_doc] = si["groups"][1]["kinds"][0]["docs"]
    assert cn_doc["status"] == "draft" and cn_doc["id"] == made["id"]

    so_id = si["groups"][0]["kinds"][0]["docs"][0]["id"]
    so = _found(_conn(seller, co, "sales_order", so_id, scall))
    assert so["sales_invoice"] == [inv["number"]] and so["credit_note"] == [""]
    assert len(so["pick_list"]) == 1 and len(so["delivery_note"]) == 1
    cn = _found(_conn(seller, co, "credit_note", made["id"], scall))
    assert cn["sales_invoice"] == [inv["number"]] and len(cn["sales_order"]) == 1
