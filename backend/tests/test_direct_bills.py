# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Purchase bills without goods receipt (Sidharth, 2026-11-16, preview 82):
services and goods not kept in stock, booked to the item's Expense Account or
to an expense ledger. No stock moves."""

from decimal import Decimal as D

import pytest

from core.models import (
    Item,
    ItemGroup,
    ItemGroupAccount,
    ItemGstRate,
    Ledger,
    LedgerGroup,
    Unit,
)
from posting.models import StockMove
from posting.service import gl_balance
from tenancy.context import use_tenant
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401

pytestmark = pytest.mark.django_db(databases="__all__")


@pytest.fixture
def office(alpha, world):
    """An AMC service, copier paper not kept in stock, and expense ledgers."""
    with use_tenant(alpha):
        company = world["company"]
        expenses = LedgerGroup.objects.get(company_id=company, code="indirect_expenses")
        repairs = Ledger.objects.create(company_id=company, group=expenses, name="Repairs")
        office_exp = Ledger.objects.create(company_id=company, group=expenses, name="Office")
        courier = Ledger.objects.create(company_id=company, group=expenses, name="Courier")
        assets = LedgerGroup.objects.filter(company_id=company, nature="asset").first()
        printer = Ledger.objects.create(company_id=company, group=assets, name="Office Equipment")
        group = ItemGroup.objects.create(name="Office supplies")
        ItemGroupAccount.objects.create(group=group, company_id=company, cogs_ledger=office_exp)
        nos = (
            Unit.objects.get(name="Numbers")
            if Unit.objects.filter(name="Numbers").exists()
            else Unit.objects.first()
        )
        more = {"item_group": group, "stock_unit": nos, "maintain_stock": False}
        amc = Item.objects.create(item_number="ITEM-91", name="Printer AMC", hsn="998713",
                                  item_type=Item.SERVICE, **more)  # fmt: skip
        paper = Item.objects.create(item_number="ITEM-92", name="Copier Paper", hsn="4802", **more)
        for item, rate in ((amc, "18"), (paper, "12")):
            ItemGstRate.objects.create(item=item, valid_from=TODAY.replace(day=1), rate=rate)
        tea_in_stock = world["tea"]
    return {**world, "amc": amc.pk, "paper": paper.pk, "repairs": repairs.pk,
            "office": office_exp.pk, "courier": courier.pk, "printer": printer.pk,
            "stocked": tea_in_stock}  # fmt: skip


def _url(o):
    return f"companies/{o['company']}/direct-bills/"


def _body(o, **more):
    return {
        "supplier": o["local"],
        "branch": o["branch"],
        "bill_no": "SOS/0418",
        "bill_date": TODAY.isoformat(),
        "lines": [
            {
                "item": o["amc"],
                "description": "Nov–Oct",
                "qty": "1",
                "rate": "12000",
                "gst_rate": "18",
            },
            {"item": o["paper"], "qty": "40", "rate": "250", "gst_rate": "12"},
            {
                "ledger": o["courier"],
                "hsn": "996812",
                "description": "October",
                "qty": "1",
                "rate": "1500",
                "gst_rate": "18",
            },
        ],  # fmt: skip
        **more,
    }


def test_item_expense_account_wins_over_the_group(owner, office, alpha):
    rows = call(owner, "get", f"items/{office['amc']}/accounts/").json()
    row = next(r for r in rows if r["company"] == office["company"])
    assert row["expense_ledger"] is None and row["group_ledger_name"] == "Office"
    put = [{"company": office["company"], "expense_ledger": office["repairs"]}]
    saved = call(owner, "put", f"items/{office['amc']}/accounts/", put)
    assert saved.status_code == 200, saved.json()
    assert (
        next(r for r in saved.json() if r["company"] == office["company"])["expense_ledger_name"]
        == "Repairs"
    )
    # Not an expense ledger: refused.
    bad = [{"company": office["company"], "expense_ledger": office["printer"]}]
    refused = call(owner, "put", f"items/{office['amc']}/accounts/", bad)
    assert refused.status_code == 400 and "expense ledger" in str(refused.json())


def test_a_bill_without_goods_receipt_books_to_expenses(owner, buyer, office, alpha):
    call(owner, "put", f"items/{office['amc']}/accounts/",
         [{"company": office["company"], "expense_ledger": office["repairs"]}])  # fmt: skip
    made = call(buyer, "post", _url(office), _body(office))
    assert made.status_code == 201, made.json()
    bill = made.json()
    assert bill["kind"] == "direct" and bill["kind_label"] == "Without goods receipt"
    assert [ln["booked_to_name"] for ln in bill["expense_lines"]] == [
        "Repairs",
        "Office",
        "Courier",
    ]
    # 12,000 + 10,000 + 1,500; GST 2,160 + 1,200 + 270.
    assert (bill["taxable_total"], bill["total"]) == ("23500.00", "27130.00")
    assert (bill["cgst_total"], bill["sgst_total"]) == ("1815.00", "1815.00")
    preview = {e["ledger"]: e for e in bill["entries"]}
    assert D(preview["Repairs"]["debit"]) == D("12000")

    done = call(buyer, "patch", f"direct-bills/{bill['id']}/",
                {**_body(office), "bill_total": "27130", "submit": True})  # fmt: skip
    assert done.status_code == 200, done.json()
    bill = done.json()
    assert bill["status"] == "submitted" and bill["number"]
    with use_tenant(alpha):
        assert gl_balance(Ledger.objects.get(pk=office["local"])) == -D("27130")
        assert gl_balance(Ledger.objects.get(pk=office["office"])) == D("10000")
        assert not StockMove.objects.filter(voucher_type="purchase_invoice").exists()
    listed = call(buyer, "get", f"companies/{office['company']}/purchase-invoices/").json()
    assert listed[0]["kind"] == "direct"

    # The same bill number again is refused; cancelling reverses the entries.
    again = call(buyer, "post", _url(office), {**_body(office), "bill_total": "27130",
                                               "submit": True})  # fmt: skip
    assert again.status_code == 400 and "already entered" in str(again.json())
    gone = call(owner, "post", f"purchase-invoices/{bill['id']}/cancel/", {"reason": "Wrong"})
    assert gone.status_code == 200, gone.json()
    with use_tenant(alpha):
        assert gl_balance(Ledger.objects.get(pk=office["local"])) == 0


def test_stock_items_and_asset_ledgers_are_refused(buyer, office):
    stocked = {"item": office["stocked"], "qty": "1", "rate": "10", "gst_rate": "5"}
    res = call(buyer, "post", _url(office), _body(office, lines=[stocked]))
    assert res.status_code == 400 and "goods receipt" in str(res.json())
    asset = {"ledger": office["printer"], "qty": "1", "rate": "13500", "gst_rate": "18"}
    res = call(buyer, "post", _url(office), _body(office, lines=[asset]))
    assert res.status_code == 400 and "expense ledger" in str(res.json())
