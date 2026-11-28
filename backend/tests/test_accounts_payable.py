# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Reports › Purchase › Accounts Payable (Sidharth, 2026-11-28, previews
mockups/accounts-payable/1 to 4): open supplier bills, aged."""

import datetime
from decimal import Decimal as D

import pytest

from buying.payables import Bill, due_bucket
from core.models import Ledger, LedgerOpeningBill
from posting.service import gl_balance
from tenancy.context import use_tenant
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import _body, _inv_url, g_company, received  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401
from tests.test_purchase_returns import _bill, _dn_url, _send_back

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _report(client, g, **params):
    params.setdefault("as_on", TODAY.isoformat())
    q = "&".join(f"{k}={v}" for k, v in params.items())
    got = call(client, "get", f"companies/{g['company']}/accounts-payable/?{q}")
    assert got.status_code == 200, got.json()
    return got.json()


def _debit_note(client, g, ret, inv):
    made = call(client, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}").json()
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(),
            "lines": [{k: ln[k] for k in ("invoice_line", "return_line", "qty")}
                      for ln in made["lines"]],
            "submit": True}  # fmt: skip
    done = call(client, "post", _dn_url(g), body)
    assert done.status_code == 201, done.json()
    return done.json()


def test_a_bill_less_its_debit_note_is_what_the_supplier_ledger_owes(store, buyer, received, alpha):
    g = received
    ret = _send_back(store, g)
    inv = _bill(buyer, g)
    note = _debit_note(buyer, g, ret, inv)

    bills = _report(buyer, g, view="bills")
    assert bills["count"] == 1 and bills["labels"][0] == "Not Due"
    row = bills["results"][0]
    assert row["our_no"] == inv["number"] and row["bill_no"] == "DTT/1201"
    assert row["amount"] == inv["total"]
    assert row["dn"] == note["total"] and row["dn_note"] == note["number"]
    with use_tenant(alpha):
        owed = -gl_balance(Ledger.objects.get(pk=g["local"]))
    # Total less TDS less the debit note (net of the TDS it took back) = the ledger.
    assert D(row["balance"]) == owed
    assert D(row["amount"]) - D(row["tds"]) - D(row["dn"]) == owed
    assert row["late"] == 0 and row["age"] == "Not Due"
    assert bills["groups"][str(row["supplier_id"])]["balance"] == row["balance"]

    sup = _report(buyer, g)["results"]
    assert len(sup) == 1 and D(sup[0]["due"]) == owed and sup[0]["bills"] == 1

    # A cancelled note no longer counts.
    gone = call(buyer, "post", f"debit-notes/{note['id']}/cancel/", {"reason": "Wrong"})
    if gone.status_code == 200:
        again = _report(buyer, g, view="bills")["results"][0]
        assert again["dn"] == "0.00"

    # As on the day before the bill, nothing was owed.
    before = (TODAY - datetime.timedelta(days=1)).isoformat()
    assert _report(buyer, g, as_on=before)["results"] == []


def test_prints_and_the_statement_are_pdfs(buyer, received, alpha):
    g = received
    _bill(buyer, g)
    base = f"companies/{g['company']}/accounts-payable/"
    for layout in ("summary", "bills"):
        got = call(buyer, "get", f"{base}pdf/?as_on={TODAY.isoformat()}&layout={layout}")
        assert got.status_code == 200
        assert got.content.startswith(b"%PDF")
    got = call(buyer, "get", f"{base}suppliers/{g['local']}/pdf/?as_on={TODAY.isoformat()}")
    assert got.status_code == 200 and got.content.startswith(b"%PDF")
    assert "outstanding-bills-" in got["Content-Disposition"]
    draft = call(buyer, "get", f"{base}suppliers/{g['local']}/mail/")
    assert draft.status_code == 200, draft.json()
    assert draft.json()["attachment"].endswith(".pdf")
    assert call(buyer, "get", f"{base}suppliers/999999/pdf/").status_code == 404


def test_opening_bills_age_by_due_date_and_overdue_only(buyer, received, alpha):
    g = received
    _bill(buyer, g)
    with use_tenant(alpha):
        supplier = Ledger.objects.get(pk=g["local"])
        LedgerOpeningBill.objects.create(
            ledger=supplier, ref="OLD/118", bill_date=TODAY - datetime.timedelta(days=100),
            due_date=TODAY - datetime.timedelta(days=70), amount=D("21600"), side="cr",
        )  # fmt: skip
    got = _report(buyer, g, view="bills")
    old = next(r for r in got["results"] if r["bill_no"] == "OLD/118")
    assert old["our_no"] == "Opening" and old["late"] == 70 and old["age"] == "61-90"
    assert old["buckets"][3] == "21600.00"

    sup = _report(buyer, g)["results"][0]
    assert sup["bills"] == 2 and sup["b"][3] == "21600.00" and sup["oldest"] == 70

    overdue = _report(buyer, g, view="bills", overdue="1")
    assert [r["bill_no"] for r in overdue["results"]] == ["OLD/118"]
    # The supplier panel's list: one supplier's overdue bills, every row, latest first.
    panel = _report(buyer, g, view="bills", overdue="1", ledger=g["local"], all="1", sort="-late")
    assert [r["bill_no"] for r in panel["results"]] == ["OLD/118"]

    by_bill = _report(buyer, g, view="bills", age_by="bill")
    assert by_bill["labels"][0] == "0-30"
    assert next(r for r in by_bill["results"] if r["bill_no"] == "OLD/118")["age"] == "91-180"

    # Opening bills have no branch: a branch picked leaves them out.
    one = _report(buyer, g, view="bills", branch=g["branch"])
    assert [r["our_no"] for r in one["results"]] != ["Opening"]
    assert all(r["our_no"] != "Opening" for r in one["results"])

    # Column search and sort.
    found = _report(buyer, g, view="bills", bill_no="old")
    assert [r["bill_no"] for r in found["results"]] == ["OLD/118"]
    first = _report(buyer, g, view="bills", sort="-late")["results"][0]
    assert first["bill_no"] == "OLD/118"

    bad = call(buyer, "get", f"companies/{g['company']}/accounts-payable/?age_by=x")
    assert bad.status_code == 400


def test_parts_of_a_bill_age_on_their_own_and_notes_come_off_the_latest():
    as_on = datetime.date(2026, 11, 28)
    b = Bill(
        key="x", supplier=None, invoice_id=1, bill_no="B1", our_no="PI1",
        bill_date=datetime.date(2026, 9, 1), amount=D("1000"), dn=D("300"),
        parts=[[datetime.date(2026, 9, 1), D("500")], [datetime.date(2026, 12, 1), D("500")]],
    )  # fmt: skip
    b.settle(as_on, by_bill=False)
    assert b.balance == D("700")
    # The note took 300 off the later half: 500 overdue 88 days, 200 not due.
    assert b.buckets == [D("200"), 0, 0, D("500"), 0]
    assert b.due_date == datetime.date(2026, 9, 1) and b.late == 88
    assert [due_bucket(n) for n in (0, 1, 30, 31, 60, 61, 90, 91)] == [0, 1, 1, 2, 2, 3, 3, 4]
