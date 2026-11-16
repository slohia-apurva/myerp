# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""TDS on every purchase bill (Sidharth, 2026-11-16, previews 86a/86b): the
section from the item, ledger or supplier, the limits and the supplier's year
so far, the rate for the deductee, TDS Payable, net dues, debit notes."""

from decimal import Decimal as D

import pytest

from core.models import Company, Item, Ledger, Party
from posting.service import gl_balance
from tenancy.context import use_tenant
from tests.test_direct_bills import _body, _url, office  # noqa: F401
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import _inv_url, g_company, received  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401
from tests.test_purchase_returns import _bill, _dn_url

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _entries(bill):
    rows = bill["entries"]
    assert sum(D(e["debit"] or 0) for e in rows) == sum(D(e["credit"] or 0) for e in rows)
    return {e["ledger"]: (D(e["debit"] or 0), D(e["credit"] or 0)) for e in rows}


def _sections(alpha, o, amc="194C", courier="194C"):
    with use_tenant(alpha):
        Item.objects.filter(pk=o["amc"]).update(tds_section=amc)
        Ledger.objects.filter(pk=o["courier"]).update(tds_section=courier)


def _amc(o, rate):
    body = _body(o)
    body["lines"][0]["rate"] = rate
    return body


def test_a_bill_over_the_one_bill_limit_deducts_and_pays_the_supplier_net(
    buyer, owner, office, alpha
):
    _sections(alpha, office)
    made = call(buyer, "post", _url(office), _amc(office, "40000"))
    assert made.status_code == 201, made.json()
    bill = made.json()
    rows = bill["tds"]["rows"]
    assert bill["tds"]["deductee"] == "Firm or LLP (from PAN AAPFD1234F)"
    # AMC 40,000 and courier 1,500 are 194C: together over ₹30,000 in one bill, 2% for a firm.
    assert [(r["label"], r["section"], r["base"], r["amount"]) for r in rows] == [
        ("Printer AMC", "194C", "40000.00", "800.00"),
        ("Copier Paper", "", "0.00", "0.00"),
        ("Courier", "194C", "1500.00", "30.00"),
    ]
    assert "does not deduct on purchase of goods" in rows[1]["note"]
    assert bill["tds_total"] == "830.00"
    preview = _entries(bill)
    assert preview["TDS Payable 194C"] == (0, D("830"))
    assert preview["Darjeeling Tea Traders"][1] == D(bill["total"]) - 830

    done = call(buyer, "patch", f"direct-bills/{bill['id']}/",
                {**_amc(office, "40000"), "bill_total": bill["total"], "submit": True})  # fmt: skip
    assert done.status_code == 200, done.json()
    bill = done.json()
    assert sum(D(d["amount"]) for d in bill["dues"]) == D(bill["total"]) - 830
    with use_tenant(alpha):
        assert gl_balance(Ledger.objects.get(pk=office["local"])) == -(D(bill["total"]) - 830)
        tds = Ledger.objects.get(company_id=office["company"], system_code="tds_194c")
        assert tds.name == "TDS Payable 194C" and tds.group.code == "duties_taxes"
        assert gl_balance(tds) == -D("830")


def test_the_year_passing_its_limit_catches_up_earlier_bills(buyer, office, alpha):
    _sections(alpha, office)
    first = call(buyer, "post", _url(office), _amc(office, "25000")).json()
    assert first["tds_total"] == "0.00"
    note = first["tds"]["rows"][0]["note"]
    assert "Below the limits (one bill ₹30,000 and year ₹1,00,000)" in note
    body = {**_amc(office, "25000"), "bill_total": first["total"], "submit": True}
    done = call(buyer, "patch", f"direct-bills/{first['id']}/", body)
    assert done.status_code == 200, done.json()
    # 26,500 so far; a second bill of 80,000 + 1,500 takes the year past 1,00,000.
    second = call(buyer, "post", _url(office), _amc(office, "80000") | {"bill_no": "SOS/0419"})
    bill = second.json()
    amc = bill["tds"]["rows"][0]
    assert amc["base"] == "106500.00" and "includes ₹26,500 of earlier bills" in amc["note"]
    assert bill["tds_total"] == str(D("2130") + D("30")) + ".00"
    assert bill["tds"]["year_so_far"] == [{"section": "194C", "amount": "26500.00"}]


def test_goods_deduct_194q_above_the_limit_when_the_company_ticks_it(buyer, office, alpha):
    with use_tenant(alpha):
        Company.objects.filter(pk=office["company"]).update(deduct_194q=True)
    body = _body(office)
    body["lines"] = [{"item": office["paper"], "qty": "40", "rate": "150000", "gst_rate": "12"}]
    bill = call(buyer, "post", _url(office), body).json()
    row = bill["tds"]["rows"][0]
    # 60,00,000 in the year: 0.1% on the 10,00,000 above 50,00,000.
    assert (row["section"], row["base"], row["amount"]) == ("194Q", "1000000.00", "1000.00")


def test_a_section_changed_on_the_bill_and_no_pan(buyer, office, alpha):
    _sections(alpha, office)
    bill = call(buyer, "post", _url(office), _amc(office, "40000")).json()
    link = f"purchase-invoices/{bill['id']}/tds/"
    # Clear the AMC's section: only the courier is left, below the limits.
    res = call(buyer, "put", link, {"rows": [{"line_kind": "expense", "line_position": 1,
                                              "section": ""}]})  # fmt: skip
    assert res.status_code == 200, res.json()
    rows = res.json()["tds"]["rows"]
    assert rows[0]["by_hand"] and rows[0]["section"] == "" and res.json()["tds_total"] == "0.00"
    # Saving the bill again keeps the choice.
    again = call(buyer, "patch", f"direct-bills/{bill['id']}/", _amc(office, "40000")).json()
    assert again["tds"]["rows"][0]["section"] == ""
    bad = call(buyer, "put", link, {"rows": [{"line_kind": "expense", "line_position": 1,
                                              "section": "999Z"}]})  # fmt: skip
    assert bad.status_code == 400 and "not in the TDS sections list" in str(bad.json())
    # Back to 194C, for a supplier with no PAN: 20%.
    with use_tenant(alpha):
        Party.objects.filter(ledgers__pk=office["local"]).update(pan="", gstin="")
    res = call(buyer, "put", link, {"rows": [{"line_kind": "expense", "line_position": 1,
                                              "section": "194C"}]})  # fmt: skip
    row = res.json()["tds"]["rows"][0]
    assert not row["by_hand"] and row["rate"] == "20" and row["amount"] == "8000.00"


def test_masters_take_only_listed_sections(owner, office):
    res = call(owner, "patch", f"items/{office['amc']}/", {"tds_section": "194Z"})
    assert res.status_code == 400 and "not in the TDS sections list" in str(res.json())
    res = call(owner, "patch", f"ledgers/{office['courier']}/", {"tds_section": "194Z"})
    assert res.status_code == 400 and "not in the TDS sections list" in str(res.json())
    res = call(owner, "patch", f"ledgers/{office['courier']}/", {"tds_section": "194J(b)"})
    assert res.status_code == 200 and res.json()["tds_section"] == "194J(b)", res.json()
    listed = call(owner, "get", "tds-sections/").json()
    assert {"194C", "194Q", "194J(b)"} <= {s["code"] for s in listed}


def test_a_debit_note_takes_tds_back_in_proportion(buyer, received, alpha):
    g = received
    with use_tenant(alpha):
        Item.objects.filter(pk=g["tea"]).update(tds_section="194C")
    inv = _bill(buyer, g)
    tea = next(r for r in inv["tds"]["rows"] if r["section"] == "194C")
    assert D(tea["amount"]) == (D(tea["taxable"]) * 2 / 100).quantize(D("1"))
    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?invoice={inv['id']}&reason=rate").json()
    line = next(ln for ln in made["lines"] if ln["item_name"] != "Tea Box")
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(), "reason": "rate",
            "lines": [{"invoice_line": line["invoice_line"], "qty": line["qty"],
                       "new_rate": str(D(line["rate"]) - 10)}]}  # fmt: skip
    note = call(buyer, "post", _dn_url(g), body).json()
    # 6,000 less at 2%: 120 of TDS comes back.
    assert _entries(note)["TDS Payable 194C"] == (D("120"), 0)
    done = call(buyer, "patch", f"debit-notes/{note['id']}/", {**body, "submit": True}).json()
    with use_tenant(alpha):
        supplier = Ledger.objects.get(pk=g["local"])
        owed = D(inv["total"]) - D(inv["tds_total"]) - (D(done["total"]) - 120)
        assert gl_balance(supplier) == -owed
