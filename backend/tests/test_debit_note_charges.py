# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Charges on a debit note (Sidharth, 2026-11-25, preview 106): the bill's
charges' share for the goods sent back, editable, plus charges added by hand."""

from decimal import Decimal as D

import pytest

from tenancy.context import use_tenant
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import g_company, received  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401
from tests.test_purchase_returns import _bill, _dn_url, _grni, _send_back

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _entries(note):
    rows = note["entries"]
    assert sum(D(e["debit"] or 0) for e in rows) == sum(D(e["credit"] or 0) for e in rows)
    return {e["ledger"]: (D(e["debit"] or 0), D(e["credit"] or 0)) for e in rows}


def test_the_bills_freight_share_comes_back_and_nothing_goes_to_price_difference(
    store, buyer, received, alpha
):
    g = received
    ret = _send_back(store, g)
    inv = _bill(buyer, g, box_qty="30")
    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}").json()
    # The receipt spread ₹300 of freight on the 30 packets: ₹30 for the 3 sent back.
    assert [(c["item_name"], c["amount"], c["in_stock_cost"]) for c in made["charges"]] == [
        ("Freight Inward", "30.00", True)
    ]
    assert any(i["name"] == "Freight Inward" for i in made["charge_items"])
    freight = made["charges"][0]
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(),
            "lines": [{k: ln[k] for k in ("invoice_line", "return_line", "qty")}
                      for ln in made["lines"]],
            "charges": [{k: freight[k] for k in ("item", "bill_charge", "amount", "gst_rate",
                                                 "in_stock_cost")}],
            "submit": True}  # fmt: skip
    done = call(buyer, "post", _dn_url(g), body)
    assert done.status_code == 201, done.json()
    note = done.json()
    # 60 of goods and 30 of freight, both at 18%.
    assert note["taxable_total"] == "90.00" and note["cgst_total"] == "8.10"
    entries = _entries(note)
    assert entries["Goods Received but Bills not Received"] == (0, D("90.00"))
    assert "Purchase Price Difference" not in entries
    assert [c["bill_charge"] for c in note["charges"]] == [freight["bill_charge"]]
    with use_tenant(alpha):
        assert _grni(g) == 0
    pdf = buyer.get(f"/api/v1/debit-notes/{note['id']}/pdf/", HTTP_HOST="alpha.localhost")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    with use_tenant(alpha):
        from buying import purchase_prints
        from buying.models import DebitNote

        data = purchase_prints.debit_note_data(DebitNote.objects.get(pk=note["id"]))
    assert [(c["item_name"], c["basis_label"]) for c in data["charges"]] == [
        ("Freight Inward", "Share of the bill's charge")
    ]


def test_a_charge_added_by_hand_goes_back_to_its_expense(store, buyer, received, alpha):
    g = received
    ret = _send_back(store, g)
    inv = _bill(buyer, g, box_qty="30")
    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}").json()
    freight = made["charges"][0]
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(),
            "lines": [{k: ln[k] for k in ("invoice_line", "return_line", "qty")}
                      for ln in made["lines"]],
            "charges": [{"item": freight["item"], "amount": "250", "gst_rate": "18",
                         "in_stock_cost": False}]}  # fmt: skip
    note = call(buyer, "post", _dn_url(g), body).json()
    assert note["taxable_total"] == "310.00"
    entries = _entries(note)
    credited = [k for k, (dr, cr) in entries.items() if cr == D("250.00")]
    assert len(credited) == 1  # the charge's expense ledger
    # The freight share left off: it stays in Purchase Price Difference as before.
    assert entries["Purchase Price Difference"] == (D("30.00"), 0)
    # A rate note takes no charges.
    refused = call(buyer, "post", _dn_url(g), {**body, "reason": "rate"})
    assert refused.status_code == 400
