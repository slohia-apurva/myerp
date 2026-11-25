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


def _dress(alpha, g):
    """Real-looking company, branch, supplier and order details, so the print
    shows every box filled (as the approved PO print does)."""
    from buying.models import PurchaseOrderLine
    from core.models import Branch, Certificate, Company, Ledger, PartyAddress

    with use_tenant(alpha):
        company = Company.objects.get(pk=g["company"])
        Company.objects.filter(pk=company.pk).update(
            address="10/D/2, Ho Chi Minh Sarani\n2nd Floor, Kemwell Manor",
            city="Kolkata", pincode="700071", phone="9133400702",
            email="accounts@apurvam.in", cin="AAN-2511", print_ganesha=True,
        )  # fmt: skip
        Certificate.objects.create(company=company, kind="fssai", number="10019031002962")
        Branch.objects.filter(pk=g["branch"]).update(
            address="10/D/2, Ho Chi Minh Sarani\nKemwell Manor, 2nd Floor", city="Kolkata",
            pincode="700071", contact_person="Accounts Desk", phone="9830012345",
            email="accounts@apurvam.in",
        )  # fmt: skip
        party = Ledger.objects.get(pk=g["local"]).party
        PartyAddress.objects.create(
            party=party, label="Head office", address="4 Hill Cart Road", city="Siliguri",
            pincode="734001", state_code=party.state_code or "19", is_billing=True,
        )  # fmt: skip
        party.contacts.create(name="Ramesh Agarwal", phone="9830012345",
                              email="ramesh@dtt.in", is_primary=True)  # fmt: skip
        # A carton of 10 packets of Tea Box, and our bank account and UPI ID.
        from core.models import Item, ItemUnit, LedgerGroup, Unit

        box = Item.objects.get(pk=g["box"]) if "box" in g else Item.objects.get(name="Tea Box")
        ctn = Unit.objects.filter(name__iexact="Carton").first() or Unit.objects.create(
            name="Carton", short_name="ctn"
        )
        ItemUnit.objects.create(item=box, unit=ctn, contains_qty=10,
                                contains_unit=box.stock_unit, factor=10)  # fmt: skip
        hdfc = Ledger.objects.create(
            company=company, name="HDFC Current",
            group=LedgerGroup.objects.get(company=company, code="bank_accounts"),
            bank_name="HDFC Bank", bank_branch="Park Street",
            account_number="50200012345678", ifsc="HDFC0000123",
        )  # fmt: skip
        Company.objects.filter(pk=company.pk).update(payment_ledger=hdfc, upi_id="apurvam@hdfcbank")
        PurchaseOrderLine.objects.filter(order__receipts=g["receipt"]).update(
            description="Assam CTC BOP, 2026 second flush\nMoisture below 6%, packed in 50 kg sacks"
        )


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
    _dress(alpha, received)
    bill = _bill(buyer, received)
    got = _pdf(buyer, bill, "purchase-invoice")
    assert "attachment" not in got["Content-Disposition"]
    with use_tenant(alpha):
        data = invoice_pdf.print_data(PurchaseInvoice.objects.get(pk=bill["id"]))
    meta = dict(data["print_meta"])
    assert meta["Supplier Bill No"] == "DTT/1201"
    assert meta["Goods Receipt"] == received["receipt_number"]
    assert meta["Purchase Order"]
    assert f"GRN {received['receipt_number']}" in data["lines"][0]["description"]
    assert data["lines"][0]["description"].startswith("Assam CTC BOP")
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


def _get(client, path, name):
    got = client.get(f"/api/v1/{path}", HTTP_HOST="alpha.localhost")
    assert got.status_code == 200 and got["Content-Type"] == "application/pdf"
    if keep := os.environ.get("KEEP_PRINTS"):
        with open(os.path.join(keep, f"{name}.pdf"), "wb") as f:
            f.write(got.content)


def test_the_return_challan_and_debit_note_print(store, buyer, received, alpha):
    from buying import purchase_prints
    from buying.models import DebitNote, PurchaseReturn
    from tests.test_purchase_returns import _dn_url, _send_back

    g = received
    _dress(alpha, g)
    ret = _send_back(store, g)
    _get(store, f"purchase-returns/{ret['id']}/pdf/", "return-challan")
    inv = _bill(buyer, g, box_qty="30")
    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}").json()
    body = {"invoice": inv["id"], "note_date": inv["bill_date"],
            "lines": [{k: ln[k] for k in ("invoice_line", "return_line", "qty")}
                      for ln in made["lines"]],
            "submit": True}  # fmt: skip
    note = call(buyer, "post", _dn_url(g), body).json()
    _get(buyer, f"debit-notes/{note['id']}/pdf/", "debit-note")
    with use_tenant(alpha):
        challan = purchase_prints.return_data(PurchaseReturn.objects.get(pk=ret["id"]))
        dn = purchase_prints.debit_note_data(DebitNote.objects.get(pk=note["id"]))
    assert challan["doc_title"] == "RETURN CHALLAN" and D(challan["total"]) == D(ret["value"])
    assert dict(challan["print_meta"])["Against GRN"].startswith(g["receipt_number"])
    assert dn["doc_title"] == "DEBIT NOTE"
    assert dict(dn["print_meta"])["Against Your Bill"].startswith("DTT/1201")
    # 3 packets returned: "0.3 ctn" under the quantity; our bank and QR to pay us back.
    assert (dn["lines"][0]["qty_alt"], dn["lines"][0]["unit_alt"]) == ("0.3", "ctn")
    assert dict(dn["payment"]["rows"])["Account No"] == "50200012345678"
    assert challan["lines"][0]["unit_alt"] == "ctn"
    assert dn["lines"][0]["description"].endswith(f"Returned on {ret['number']}")


def test_the_tds_adjustment_prints(buyer, office, alpha):
    from core.models import Item
    from tests.test_purchase_orders import client_for
    from tests.test_tds_check import _adjust, _submitted_bill

    accounts = client_for(alpha, "accounts@x.in", "accountant")
    bill = _submitted_bill(buyer, office)
    with use_tenant(alpha):
        Item.objects.filter(pk=office["amc"]).update(tds_section="194C")
    adj = _adjust(accounts, office, [bill["id"]], submit=True).json()
    _get(accounts, f"tds-adjustments/{adj['id']}/pdf/", "tds-adjustment")
    assert buyer.get(
        f"/api/v1/tds-adjustments/{adj['id']}/pdf/", HTTP_HOST="alpha.localhost"
    ).status_code in (403, 404)
