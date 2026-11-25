# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""The purchase invoice print (Sidharth, 2026-11-25): every kind of bill as a
PDF in the purchase order's layout, with TDS, net payable, due dates and the
ledger posting."""

import os
from decimal import Decimal as D

import pytest

from buying import invoice_pdf
from buying.models import PurchaseInvoice
from tenancy.context import use_tenant
from tests.test_direct_bills import _body, _url, office  # noqa: F401
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import received  # noqa: F401
from tests.test_purchase_orders import buyer, call, owner, world  # noqa: F401
from tests.test_purchase_returns import _bill
from tests.test_tds import _amc, _sections

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _pdf(client, bill, name):
    got = client.get(f"/api/v1/purchase-invoices/{bill['id']}/pdf/", HTTP_HOST="alpha.localhost")
    assert got.status_code == 200 and got["Content-Type"] == "application/pdf"
    assert got.content.startswith(b"%PDF")
    if keep := os.environ.get("KEEP_PRINTS"):
        with open(os.path.join(keep, f"{name}.pdf"), "wb") as f:
            f.write(got.content)
    return got


def test_a_bill_against_a_goods_receipt_prints_its_receipt_order_and_posting(
    buyer, received, alpha
):
    bill = _bill(buyer, received)
    got = _pdf(buyer, bill, "purchase-invoice")
    assert "attachment" not in got["Content-Disposition"]
    with use_tenant(alpha):
        data = invoice_pdf.print_data(PurchaseInvoice.objects.get(pk=bill["id"]))
    meta = dict(data["print_meta"])
    assert meta["Supplier Bill No"] == "DTT/1201"
    assert meta["Goods Receipt"] == received["receipt_number"]
    assert meta["Purchase Order"]
    assert data["lines"][0]["description"].startswith(f"GRN {received['receipt_number']}")
    assert {e["ledger"] for e in data["posting"]} >= {"Goods Received but Bills not Received"}
    assert data["dues"] and data["doc_title"] == "PURCHASE INVOICE"
    down = buyer.get(
        f"/api/v1/purchase-invoices/{bill['id']}/pdf/?download=1", HTTP_HOST="alpha.localhost"
    )
    assert "attachment" in down["Content-Disposition"]


def test_a_bill_without_goods_receipt_prints_tds_and_net_payable(buyer, office, alpha):
    _sections(alpha, office)
    bill = call(buyer, "post", _url(office), _amc(office, "40000")).json()
    _pdf(buyer, bill, "bill-without-grn-draft")
    with use_tenant(alpha):
        data = invoice_pdf.print_data(PurchaseInvoice.objects.get(pk=bill["id"]))
    after = [k for k, _, _ in data["after_total"]]
    assert after[-1] == "Net Payable" and any("194C" in k for k in after)
    assert data["lines"][0]["item_name"] == "Printer AMC"


def test_a_supplementary_bill_prints_the_rate_raised_against_its_bill(buyer, received, alpha):
    from tests.test_rate_notes import _sup_url, _tea

    inv = _bill(buyer, received)
    made = call(buyer, "get", f"{_sup_url(received)}draft-from/?invoice={inv['id']}").json()
    tea = _tea(made["lines"])
    body = {"original": inv["id"], "bill_no": "DTT/1322", "bill_date": inv["bill_date"],
            "lines": [{"invoice_line": tea["invoice_line"], "qty": tea["qty"],
                       "new_rate": str(D(tea["rate"]) + 5)}]}  # fmt: skip
    bill = call(buyer, "post", _sup_url(received), body).json()
    _pdf(buyer, bill, "supplementary-bill")
    with use_tenant(alpha):
        data = invoice_pdf.print_data(PurchaseInvoice.objects.get(pk=bill["id"]))
    assert data["doc_title"] == "SUPPLEMENTARY BILL"
    assert dict(data["print_meta"])["Against Bill"].startswith(inv["number"])
    assert [(x["rate"], x["description"]) for x in data["lines"]] == [
        ("5", "Rate 250 → 255 on 600 kg")
    ]
