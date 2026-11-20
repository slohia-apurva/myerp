# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""TDS Check and TDS Adjustment (Sidharth, 2026-11-19, previews 95a-c): a
supplier's year worked out again with today's masters, a gap put right by an
adjustment (never by changing the bill), and a quarter whose TDS return is
filed locked against both."""

import datetime
from decimal import Decimal as D

import pytest

from buying import tds_check
from buying.models import PurchaseInvoice
from core.models import Item, Ledger
from posting.service import gl_balance
from tenancy.context import use_tenant
from tests.test_direct_bills import _body, _url, office  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, client_for, owner, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture
def accounts(alpha):
    return client_for(alpha, "accounts@x.in", "accountant")


def _submitted_bill(buyer, o, rate="40000"):
    body = _body(o)
    body["lines"][0]["rate"] = rate
    bill = call(buyer, "post", _url(o), body).json()
    done = call(buyer, "patch", f"direct-bills/{bill['id']}/",
                {**body, "bill_total": bill["total"], "submit": True})  # fmt: skip
    assert done.status_code == 200, done.json()
    return done.json()


def _check(client, o):
    res = call(client, "get", f"companies/{o['company']}/tds-check/")
    assert res.status_code == 200, res.json()
    return res.json()


def _row(check, o, section="194C"):
    return next(r for r in check["rows"] if r["supplier"] == o["local"] and r["section"] == section)


def _adjust(client, o, invoices, submit=False):
    body = {"supplier": o["local"], "section": "194C", "adj_date": TODAY.isoformat(),
            "remarks": "AMC had no section", "invoices": invoices, "submit": submit}  # fmt: skip
    return call(client, "post", f"companies/{o['company']}/tds-adjustments/", body)


def test_quarters_and_months_late():
    q = tds_check.quarter_start
    assert q(datetime.date(2026, 5, 20)) == datetime.date(2026, 4, 1)
    assert q(datetime.date(2027, 2, 1)) == datetime.date(2027, 1, 1)
    assert tds_check.quarter_label(datetime.date(2026, 10, 1)) == "Oct-Dec 2026"
    late = tds_check.months_late
    assert late(datetime.date(2026, 9, 4), datetime.date(2026, 11, 19)) == 3
    assert late(datetime.date(2026, 11, 8), datetime.date(2026, 11, 19)) == 1


def test_a_bill_billed_before_its_item_had_a_section_is_short_and_put_right(
    buyer, accounts, owner, office, alpha
):
    o = office
    bill = _submitted_bill(buyer, o)
    assert bill["tds_total"] == "0.00"
    # The AMC gets its section after the bill: the check works the year out with today's masters.
    with use_tenant(alpha):
        Item.objects.filter(pk=o["amc"]).update(tds_section="194C")
    row = _row(_check(accounts, o), o)
    # 40,000 is over the one-bill limit of 30,000: 2% for a firm.
    assert (row["result"], row["due"], row["deducted"], row["gap"]) == (
        "short", "800.00", "0.00", "800.00",
    )  # fmt: skip
    detail = call(accounts, "get", f"companies/{o['company']}/tds-check/supplier/"
                  f"?ledger={o['local']}&section=194C").json()  # fmt: skip
    line = detail["bills"][0]
    assert line["number"] == bill["number"] and line["on_bill_section"] == "None"
    assert line["why"].startswith("Not under 194C on the bill when billed: Printer AMC.")

    # The fix: a TDS Adjustment naming the bill, its amount from the check.
    made = call(accounts, "get", f"companies/{o['company']}/tds-adjustments/draft-from/"
                f"?ledger={o['local']}&section=194C").json()  # fmt: skip
    assert made["invoices"] == [bill["id"]]
    res = _adjust(accounts, o, made["invoices"])
    assert res.status_code == 201, res.json()
    adj = res.json()
    assert adj["total"] == "800.00" and adj["kind_label"] == "Deduct short TDS"
    assert adj["lines"][0]["months"] == 1 and adj["lines"][0]["interest"] == "8.00"
    posting = call(accounts, "get", f"tds-adjustments/{adj['id']}/ledger-posting/").json()
    rows = {r["ledger_name"]: (r["debit"], r["credit"]) for r in posting["rows"]}
    assert rows == {
        "Darjeeling Tea Traders": ("800.00", "0.00"),
        "TDS Payable 194C (made on Submit)": ("0.00", "800.00"),
    }
    done = call(accounts, "patch", f"tds-adjustments/{adj['id']}/",
                {"supplier": o["local"], "section": "194C", "adj_date": TODAY.isoformat(),
                 "invoices": [bill["id"]], "submit": True})  # fmt: skip
    assert done.status_code == 200, done.json()
    assert done.json()["number"] and done.json()["status"] == "submitted"
    with use_tenant(alpha):
        payable = Ledger.objects.get(company_id=o["company"], system_code="tds_194c")
        assert gl_balance(payable) == -D("800")
        assert gl_balance(Ledger.objects.get(pk=o["local"])) == -(D(bill["total"]) - 800)
    row = _row(_check(accounts, o), o)
    assert (row["result"], row["deducted"], row["gap"]) == ("matches", "800.00", "0.00")

    # Nothing is left to put right, and the bill cannot be cancelled under the adjustment.
    again = _adjust(accounts, o, [bill["id"]])
    assert again.status_code == 400 and "has no 194C to put right" in str(again.json())
    cancel = call(owner, "post", f"purchase-invoices/{bill['id']}/cancel/", {"reason": "x"})
    assert cancel.status_code == 400 and "names this bill" in str(cancel.json())


def test_a_filed_quarter_cannot_be_adjusted_or_cancelled(buyer, accounts, owner, office, alpha):
    o = office
    with use_tenant(alpha):
        Item.objects.filter(pk=o["amc"]).update(tds_section="194C")
    bill = _submitted_bill(buyer, o)  # deducts 800 on the bill itself
    # The AMC's section is taken off: the bill now shows 800 deducted in excess.
    with use_tenant(alpha):
        Item.objects.filter(pk=o["amc"]).update(tds_section="")
    row = _row(_check(accounts, o), o)
    assert (row["result"], row["gap"]) == ("excess", "-800.00")
    quarter = tds_check.quarter_start(TODAY).isoformat()
    filed = {"quarter_start": quarter, "filed_on": TODAY.isoformat(), "ack_no": "ACK1"}
    marked = call(accounts, "post", f"companies/{o['company']}/tds-returns/", filed)
    assert marked.status_code == 201, marked.json()
    check = _check(accounts, o)
    assert any(q["id"] == marked.json()["id"] for q in check["quarters"])
    assert _row(check, o)["fixable"] == "0.00"
    refused = _adjust(accounts, o, [bill["id"]])
    assert refused.status_code == 400 and "is filed" in str(refused.json())
    cancel = call(owner, "post", f"purchase-invoices/{bill['id']}/cancel/", {"reason": "x"})
    assert cancel.status_code == 400 and "is filed" in str(cancel.json())
    # Only an Owner takes the mark off; then the excess can be given back.
    assert call(accounts, "delete", f"tds-returns/{marked.json()['id']}/").status_code == 403
    assert call(owner, "delete", f"tds-returns/{marked.json()['id']}/").status_code == 204
    back = _adjust(accounts, o, [bill["id"]], submit=True)
    assert back.status_code == 201, back.json()
    assert back.json()["total"] == "-800.00" and back.json()["kind_label"] == "Give back excess TDS"
    with use_tenant(alpha):
        payable = Ledger.objects.get(company_id=o["company"], system_code="tds_194c")
        assert gl_balance(payable) == 0
    assert _row(_check(accounts, o), o)["result"] == "below"
    # Cancelling the adjustment reverses it.
    adj = back.json()["id"]
    res = call(accounts, "post", f"tds-adjustments/{adj}/cancel/", {"reason": "Wrong"})
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert _row(_check(accounts, o), o)["result"] == "excess"


def test_the_check_needs_accounts_rights_and_skips_cancelled_bills(buyer, accounts, office, alpha):
    o = office
    assert call(buyer, "get", f"companies/{o['company']}/tds-check/").status_code == 403
    bill = _submitted_bill(buyer, o)
    with use_tenant(alpha):
        Item.objects.filter(pk=o["amc"]).update(tds_section="194C")
        PurchaseInvoice.objects.filter(pk=bill["id"]).update(status=PurchaseInvoice.CANCELLED)
    assert _check(accounts, o)["rows"] == []


def test_the_bill_shows_tds_adjusted_later(buyer, accounts, office, alpha):
    o = office
    bill = _submitted_bill(buyer, o)
    with use_tenant(alpha):
        Item.objects.filter(pk=o["amc"]).update(tds_section="194C")
    adj = _adjust(accounts, o, [bill["id"]], submit=True).json()
    tds = call(buyer, "get", f"purchase-invoices/{bill['id']}/tds/").json()
    assert [(a["number"], a["amount"]) for a in tds["adjusted"]] == [(adj["number"], "800.00")]
    assert tds["total"] == "0.00" and tds["with_adjusted"] == "800.00"
    with use_tenant(alpha):
        from buying import tds as tds_rules

        assert tds_rules.deducted_on(PurchaseInvoice.objects.get(pk=bill["id"])) == D("800")


def test_a_bill_billed_before_its_item_had_194q_counts_towards_the_year(buyer, office, alpha):
    # Sidharth, 2026-11-20: a goods bill entered before the item had 194Q. It owes no
    # TDS (below ₹50 lakh) but must count towards the supplier's year for later bills.
    o = office
    body = _body(o)
    body["lines"] = [{"item": o["paper"], "qty": "40", "rate": "100000", "gst_rate": "12"}]
    first = call(buyer, "post", _url(o), body).json()
    done = call(buyer, "patch", f"direct-bills/{first['id']}/",
                {**body, "bill_total": first["total"], "submit": True})  # fmt: skip
    assert done.status_code == 200 and done.json()["tds_total"] == "0.00"
    with use_tenant(alpha):
        Item.objects.filter(pk=o["paper"]).update(tds_section="194Q")
    # 40,00,000 so far; the next 20,00,000 takes the year to 60 lakh: 0.1% on 10 lakh.
    body["bill_no"] = "SOS/0500"
    body["lines"][0]["rate"] = "50000"
    second = call(buyer, "post", _url(o), body).json()
    row = second["tds"]["rows"][0]
    assert (row["section"], row["base"], row["amount"]) == ("194Q", "1000000.00", "1000.00")
    assert second["tds"]["year_so_far"][0]["amount"] == "4000000.00"


def test_a_missing_section_is_set_by_an_adjustment_with_nothing_posted(
    buyer, accounts, office, alpha
):
    # Sidharth, 2026-11-20 (previews 98a-c): a goods bill entered before its item had
    # 194Q owes nothing, but should carry the section. A ₹0 adjustment records it.
    o = office
    body = _body(o)
    body["lines"] = [{"item": o["paper"], "qty": "10", "rate": "26000", "gst_rate": "12"}]
    first = call(buyer, "post", _url(o), body).json()
    bill = call(buyer, "patch", f"direct-bills/{first['id']}/",
                {**body, "bill_total": first["total"], "submit": True}).json()  # fmt: skip
    with use_tenant(alpha):
        Item.objects.filter(pk=o["paper"]).update(tds_section="194Q")
    row = _row(_check(accounts, o), o, "194Q")
    assert (row["result"], row["result_label"], row["gap"]) == (
        "missing", "Section missing", "0.00",
    )  # fmt: skip
    assert (row["no_section"], row["to_set"]) == (1, 1)
    q = f"?ledger={o['local']}&section=194Q"
    line = call(accounts, "get", f"companies/{o['company']}/tds-check/supplier/{q}").json()
    assert (
        line["bills"][0]["needs_section"]
        and "194Q missing on the bill" in (line["bills"][0]["why"])
    )
    made = call(accounts, "get", f"companies/{o['company']}/tds-adjustments/draft-from/{q}")
    assert made.json()["invoices"] == [bill["id"]]
    res = call(accounts, "post", f"companies/{o['company']}/tds-adjustments/",
               {"supplier": o["local"], "section": "194Q", "adj_date": TODAY.isoformat(),
                "invoices": [bill["id"]], "submit": True})  # fmt: skip
    assert res.status_code == 201, res.json()
    adj = res.json()
    assert (adj["total"], adj["kind_label"], adj["status"]) == (
        "0.00", "Set section only", "submitted",
    )  # fmt: skip
    posting = call(accounts, "get", f"tds-adjustments/{adj['id']}/ledger-posting/").json()
    assert posting["rows"] == [] and "only sets the TDS section" in posting["note"]
    row = _row(_check(accounts, o), o, "194Q")
    assert (row["result"], row["no_section"]) == ("below", 0)
    tds = call(buyer, "get", f"purchase-invoices/{bill['id']}/tds/").json()
    assert [(a["number"], a["section"], a["amount"]) for a in tds["adjusted"]] == [
        (adj["number"], "194Q", "0.00")
    ]
    # Nothing more to set; cancelling the adjustment takes the section off again.
    again = call(accounts, "post", f"companies/{o['company']}/tds-adjustments/",
                 {"supplier": o["local"], "section": "194Q", "adj_date": TODAY.isoformat(),
                  "invoices": [bill["id"]]})  # fmt: skip
    assert again.status_code == 400 and "has no 194Q to put right" in str(again.json())
    res = call(accounts, "post", f"tds-adjustments/{adj['id']}/cancel/", {"reason": "Wrong"})
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert _row(_check(accounts, o), o, "194Q")["result"] == "missing"
