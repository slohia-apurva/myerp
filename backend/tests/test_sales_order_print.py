"""The sales order print (Sidharth, 2026-11-25, preview mockups/sales/22c):
quantities in the stock unit with the next unit up under them, rates per stock
unit, Ship To falling back to the billing address, and the company's bank
account and UPI QR under "Payment Details"."""

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from core.models import Company, Item, Ledger, LedgerGroup
from core.print_units import in_stock_unit
from selling.customer_mail import print_data
from selling.models import SalesOrder
from tenancy.context import use_tenant
from tests.test_pick_lists import submit
from tests.test_sales_orders import call, owner, seller, world  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def bank(w, company=None, group="bank_accounts"):
    with use_tenant(w["tenant"]):
        return Ledger.objects.create(
            company_id=company or w["company"],
            group=LedgerGroup.objects.get(company_id=company or w["company"], code=group),
            name=f"HDFC Current {group}",
            bank_name="HDFC Bank",
            bank_branch="Park Street",
            account_number="50200012345678" if group == "bank_accounts" else "",
            ifsc="HDFC0000123",
        ).pk


def test_payment_details_are_checked(owner, world):  # noqa: F811
    w = world
    path = f"companies/{w['company']}/"
    other = bank(w, group="sundry_debtors")
    refused = call(owner, "patch", path, {"payment_ledger": other})
    assert refused.status_code == 400 and "bank ledgers" in str(refused.json())
    assert call(owner, "patch", path, {"upi_id": "not a upi"}).status_code == 400
    ok = call(owner, "patch", path, {"payment_ledger": bank(w), "upi_id": " apurvam@hdfcbank "})
    assert ok.status_code == 200, ok.json()
    assert ok.json()["upi_id"] == "apurvam@hdfcbank"


def test_print_in_stock_units_with_payment(owner, seller, world):  # noqa: F811
    w = world
    call(
        owner,
        "patch",
        f"companies/{w['company']}/",
        {"payment_ledger": bank(w), "upi_id": "apurvam@hdfcbank"},
    )
    so = submit(seller, w, cases="10")
    with use_tenant(w["tenant"]):
        data = print_data(SalesOrder.objects.get(pk=so["id"]))
        company = Company.objects.get(pk=w["company"])
    line = data["lines"][0]
    # 10 cartons of 24 packets at 2,280 a carton: 240 packets at 95.
    assert (line["qty"], line["unit_name"]) == ("240", "pkt")
    assert (line["qty_alt"], line["unit_alt"]) == ("10", "ctn")
    assert Decimal(line["rate"]) == Decimal("95")
    assert data["addresses"]["ship_to"]["name"] == "Organic Harvest Foods"
    rows = dict(data["payment"]["rows"])
    assert rows["Account No"] == "50200012345678" and rows["IFSC"] == "HDFC0000123"
    upi = parse_qs(urlparse(data["payment"]["upi_url"]).query)
    assert upi["pa"] == ["apurvam@hdfcbank"] and upi["pn"] == [company.name]
    assert upi["am"] == [data["total"]] and upi["tn"] == [so["number"]]
    pdf = seller.get(f"/api/v1/sales-orders/{so['id']}/pdf/", HTTP_HOST="alpha.localhost")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"


def test_no_payment_box_until_set(seller, world):  # noqa: F811
    so = submit(seller, world, cases="1")
    with use_tenant(world["tenant"]):
        data = print_data(SalesOrder.objects.get(pk=so["id"]))
    assert data["payment"] is None
    # Loose leaf has no unit above the kilogram: one line only.
    with use_tenant(world["tenant"]):
        loose = Item.objects.get(pk=world["loose"])
        line = in_stock_unit({"unit": world["kg"], "qty": "12.5", "rate": "410"}, loose)
    assert line["qty"] == "12.5" and "qty_alt" not in line


def test_bank_ledgers_listed_for_the_picker(owner, world):  # noqa: F811
    hdfc = bank(world)
    bank(world, group="sundry_debtors")
    got = call(owner, "get", f"companies/{world['company']}/ledgers/?bank=1").json()
    assert [x["id"] for x in got] == [hdfc]
    call(owner, "patch", f"companies/{world['company']}/", {"payment_ledger": hdfc})
    shown = call(owner, "get", f"companies/{world['company']}/").json()
    assert shown["company"]["payment_ledger_name"] == "HDFC Current bank_accounts"
