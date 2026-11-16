# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Rate changes on a bill already entered (Sidharth, 2026-11-16, previews
78/79): a Debit Note "Rate charged higher" and a Supplementary Bill."""

from decimal import Decimal as D

import pytest

from core.models import Ledger
from posting.service import gl_balance, stock_value
from tenancy.context import use_tenant
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import _body, _inv_url, g_company, received  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401
from tests.test_purchase_returns import _bill, _dn_url

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _sup_url(g):
    return f"companies/{g['company']}/supplementary-bills/"


def _tea(lines):
    return next(ln for ln in lines if ln["item_name"] != "Tea Box")


def _balanced(entries):
    assert sum(D(e["debit"]) for e in entries) == sum(D(e["credit"]) for e in entries)
    return {e["ledger"]: (D(e["debit"]), D(e["credit"])) for e in entries}


def test_a_lower_agreed_rate_comes_off_stock_on_hand_and_used(buyer, owner, received, alpha):
    g = received
    inv = _bill(buyer, g)
    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?invoice={inv['id']}&reason=rate").json()
    tea = _tea(made["lines"])
    assert tea["qty"] == "600" and tea["in_stock"] == "450" and tea["new_rate"] == tea["rate"]
    new_rate = str(D(tea["rate"]) - 10)
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(), "reason": "rate",
            "lines": [{"invoice_line": ln["invoice_line"], "qty": ln["qty"],
                       "new_rate": new_rate if ln is tea else ln["rate"]}
                      for ln in made["lines"]]}  # fmt: skip
    draft = call(buyer, "post", _dn_url(g), body)
    assert draft.status_code == 201, draft.json()
    note = draft.json()
    assert len(note["lines"]) == 1 and note["taxable_total"] == "6000.00"
    preview = _balanced(note["entries"])
    assert preview["Purchase Price Difference"] == (0, D("1500.00"))
    with use_tenant(alpha):
        before = stock_value(g_company(g))
    done = call(buyer, "patch", f"debit-notes/{note['id']}/", {**body, "submit": True})
    assert done.status_code == 200, done.json()
    note = done.json()
    entries = _balanced(note["entries"])
    assert entries["Input CGST"][1] + entries["Input SGST"][1] + entries.get("Input IGST", (0, 0))[
        1
    ] == D(note["total"]) - D("6000.00") - D(note["round_off"])
    assert note["lines"][0]["stock_difference"] == "-4500.00"
    with use_tenant(alpha):
        assert stock_value(g_company(g)) == before - D("4500.00")
        supplier = Ledger.objects.get(pk=g["local"])
        assert gl_balance(supplier) == -D(inv["total"]) + D(note["total"])

    # The bill is held; cancelling the note puts the stock value back.
    held = call(owner, "post", f"purchase-invoices/{inv['id']}/cancel/", {"reason": "x"})
    assert held.status_code == 400
    gone = call(owner, "post", f"debit-notes/{note['id']}/cancel/", {"reason": "Wrong"})
    assert gone.status_code == 200, gone.json()
    with use_tenant(alpha):
        assert stock_value(g_company(g)) == before


def test_a_debit_note_cannot_raise_a_rate(buyer, received):
    g = received
    inv = _bill(buyer, g)
    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?invoice={inv['id']}&reason=rate").json()
    tea = _tea(made["lines"])
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(), "reason": "rate",
            "lines": [{"invoice_line": tea["invoice_line"], "qty": tea["qty"],
                       "new_rate": str(D(tea["rate"]) + 1)}]}  # fmt: skip
    refused = call(buyer, "post", _dn_url(g), body)
    assert refused.status_code == 400 and "Supplementary Bill" in str(refused.json())


def test_a_supplementary_bill_adds_to_stock_on_hand_and_the_supplier(buyer, owner, received, alpha):
    g = received
    inv = _bill(buyer, g)
    made = call(buyer, "get", f"{_sup_url(g)}draft-from/?invoice={inv['id']}").json()
    tea = _tea(made["lines"])
    body = {"original": inv["id"], "bill_no": "DTT/1322", "bill_date": TODAY.isoformat(),
            "lines": [{"invoice_line": ln["invoice_line"], "qty": ln["qty"],
                       "new_rate": str(D(ln["rate"]) + 5) if ln is tea else ln["rate"]}
                      for ln in made["lines"]]}  # fmt: skip
    draft = call(buyer, "post", _sup_url(g), body)
    assert draft.status_code == 201, draft.json()
    bill = draft.json()
    assert bill["kind"] == "supplementary" and bill["original_number"] == inv["number"]
    assert bill["taxable_total"] == "3000.00" and len(bill["rate_lines"]) == 1
    _balanced(bill["entries"])
    # The same supplier bill number cannot be used twice.
    clash = call(buyer, "patch", f"supplementary-bills/{bill['id']}/",
                 {**body, "bill_no": inv["bill_no"], "bill_total": bill["total"],
                  "submit": True})  # fmt: skip
    assert clash.status_code == 400 and "already entered" in str(clash.json())
    with use_tenant(alpha):
        before = stock_value(g_company(g))
    done = call(buyer, "patch", f"supplementary-bills/{bill['id']}/",
                {**body, "bill_total": bill["total"], "submit": True})  # fmt: skip
    assert done.status_code == 200, done.json()
    bill = done.json()
    assert bill["number"] and bill["dues"]
    entries = _balanced(bill["entries"])
    assert entries["Purchase Price Difference"] == (D("750.00"), 0)
    with use_tenant(alpha):
        assert stock_value(g_company(g)) == before + D("2250.00")
        supplier = Ledger.objects.get(pk=g["local"])
        assert gl_balance(supplier) == -D(inv["total"]) - D(bill["total"])

    # The original lists it and cannot be cancelled while it stands.
    original = call(buyer, "get", f"purchase-invoices/{inv['id']}/").json()
    assert [x["number"] for x in original["later"]] == [bill["number"]]
    held = call(owner, "post", f"purchase-invoices/{inv['id']}/cancel/", {"reason": "x"})
    assert held.status_code == 400 and bill["number"] in str(held.json())
    # A supplementary bill is changed only on its own form, and has no supplementary of its own.
    assert call(buyer, "get", f"{_sup_url(g)}draft-from/?invoice={bill['id']}").status_code == 400
    gone = call(owner, "post", f"purchase-invoices/{bill['id']}/cancel/", {"reason": "Wrong"})
    assert gone.status_code == 200, gone.json()
    with use_tenant(alpha):
        assert stock_value(g_company(g)) == before
