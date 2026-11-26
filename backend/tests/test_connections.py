# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Connections on every entry's view (Sidharth, 2026-11-26, previews
mockups/connections/1 and 2): the entries it came from, the ones made from it,
and the returns and notes against it, read in the entry's own company."""

import pytest

from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import received  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401
from tests.test_purchase_returns import _bill, _dn_url, _send_back

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _conn(client, company, kind, pk, caller=call):
    got = caller(client, "get", f"companies/{company}/connections/{kind}/{pk}/")
    assert got.status_code == 200, got.json()
    return got.json()


def _found(c):
    """{kind: [numbers]} of everything shown, and the "later" boxes by name."""
    out = {}
    for g in c["groups"]:
        for k in g["kinds"]:
            out[k["type"] if k["type"] != "later" else f"later:{k['name']}"] = [
                d["number"] for d in k.get("docs", [])
            ]
    return out


def _kinds(c):
    return {k["type"] for grp in c["groups"] for k in grp["kinds"]}


def _debit_note(client, g, ret, inv):
    made = call(client, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}").json()
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(),
            "lines": [{k: ln[k] for k in ("invoice_line", "return_line", "qty")}
                      for ln in made["lines"]],
            "submit": True}  # fmt: skip
    done = call(client, "post", _dn_url(g), body)
    assert done.status_code == 201, done.json()
    return done.json()


def test_the_purchase_chain_is_seen_from_each_entry(store, buyer, owner, received):
    g = received
    ret = _send_back(store, g)
    inv = _bill(buyer, g, box_qty="30")
    note = _debit_note(buyer, g, ret, inv)
    co = g["company"]

    pi = _conn(owner, co, "purchase_invoice", inv["id"])
    found = _found(pi)
    assert found["purchase_order"] == [g["po_number"]]
    assert found["goods_receipt"] == [g["receipt_number"]]
    assert found["purchase_return"] == [ret["number"]]
    assert found["debit_note"] == [note["number"]]
    assert found["supplementary_bill"] == [] and found["tds_adjustment"] == []
    assert "later:Payment" in found
    assert [s["type"] for s in pi["chain"] if s["me"]] == ["purchase_invoice"]
    assert pi["summary"] == "PO 1 · GRN 1 · Return 1 · Debit Note 1"
    [doc] = pi["groups"][0]["kinds"][0]["docs"]
    assert doc["status_label"] and doc["date"]
    assert pi["groups"][0]["kinds"][0]["page"] == "purchase-orders"

    # From the order, two and three steps down; from the note, back up.
    po = _found(_conn(owner, co, "purchase_order", g["po"]))
    assert po["goods_receipt"] == [g["receipt_number"]] and po["purchase_invoice"] == [
        inv["number"]
    ]
    assert po["purchase_return"] == [ret["number"]] and po["debit_note"] == [note["number"]]
    dn = _found(_conn(owner, co, "debit_note", note["id"]))
    assert dn["purchase_invoice"] == [inv["number"]] and dn["purchase_return"] == [ret["number"]]
    assert dn["purchase_order"] == [g["po_number"]]
    pr = _found(_conn(owner, co, "purchase_return", ret["id"]))
    assert pr["debit_note"] == [note["number"]] and pr["goods_receipt"] == [g["receipt_number"]]
    gr = _found(_conn(owner, co, "goods_receipt", g["receipt"]))
    assert gr["purchase_order"] == [g["po_number"]] and gr["debit_note"] == [note["number"]]


def test_kinds_the_role_may_not_see_are_left_out(store, buyer, owner, received):
    """The storekeeper may see purchase entries but not the accounts' TDS adjustments."""
    g = received
    inv = _bill(buyer, g)
    kinds = _kinds(_conn(store, g["company"], "purchase_invoice", inv["id"]))
    assert "goods_receipt" in kinds and "tds_adjustment" not in kinds
    kinds = _kinds(_conn(owner, g["company"], "purchase_invoice", inv["id"]))
    assert "tds_adjustment" in kinds


def test_an_entry_of_another_company_or_kind_is_not_found(owner, received):
    g = received
    assert (
        call(
            owner, "get", f"companies/{g['company']}/connections/nothing/{g['receipt']}/"
        ).status_code
        == 404
    )
    assert (
        call(
            owner, "get", f"companies/{g['company']}/connections/goods_receipt/999999/"
        ).status_code
        == 404
    )


def _kind(c, name):
    return next(k for g in c["groups"] for k in g["kinds"] if k["type"] == name)


def test_a_supplier_shows_counts_and_opens_each_list_searched_for_it(buyer, owner, received, alpha):
    """Masters (preview mockups/connections/3): counts for the company, and "All n"."""
    from core.models import Ledger
    from tenancy.context import use_tenant

    g = received
    inv = _bill(buyer, g)
    with use_tenant(alpha):
        ledger = Ledger.objects.get(pk=g["local"])
        party, name = ledger.party_id, ledger.name
    c = _conn(owner, g["company"], "party", party)
    po, bill = _kind(c, "purchase_order"), _kind(c, "purchase_invoice")
    assert po["count"] == 1 and po["all"] == {"col": "supplier", "q": name}
    assert bill["count"] == 1 and bill["page"] == "purchase-invoices"
    assert _kind(c, "sales_order")["count"] == 0 and _kind(c, "sales_order")["all"] is None
    assert c["summary"].startswith("PO 1 · GRN 1 · Bill 1")
    assert inv["number"]


def test_an_item_names_its_latest_entries_batches_and_boms(owner, received):
    g = received
    c = _conn(owner, g["company"], "item", g["tea"])
    assert _kind(c, "purchase_order")["docs"][0]["number"] == g["po_number"]
    assert [d["number"] for d in _kind(c, "goods_receipt")["docs"]] == [g["receipt_number"]]
    [batch] = _kind(c, "batch")["docs"]
    assert batch["number"] == "DTT-26-118" and batch["href"] == f"#/batches/{batch['id']}/trace"
    assert (
        call(owner, "get", f"companies/{g['company']}/connections/item/999999/").status_code == 404
    )
