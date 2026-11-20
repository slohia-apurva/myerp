"""Sales invoices (Sidharth, 2026-11-20, previews 14a/14b in mockups/sales): made
from one or more submitted delivery notes of a customer, at the orders' rates
and credit term (fixed on the invoice). Submit books the sale (Dr customer, Cr each item
group's Sales Ledger and Output GST) and moves the note's cost from "Goods
Delivered but Bills not Made" to Cost of Goods Sold. The e-invoice JSON goes to
the portal; the IRN and e-way bill numbers are typed in after Submit."""

import json
from decimal import Decimal

import pytest

from core.models import Item, ItemGroupAccount, Ledger, LedgerGroup
from posting import accounts
from posting.models import GLEntry
from tenancy.context import use_tenant
from tests.test_delivery_notes import LATER, books, new_note, picked_list  # noqa: F401
from tests.test_delivery_notes import body as note_body
from tests.test_pick_lists import receive
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    owner,
    seller,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

FREIGHT = "freight"


def sent_note(client, w, **order):
    """10 cartons sent on a submitted delivery note (cost 240 packets at 10)."""
    receive(w, w["bin"], "300", "A-LATE", LATER)
    _so, pl = picked_list(client, w, cases="10", **order)
    note = new_note(client, pl)
    done = call(client, "patch", f"delivery-notes/{note['id']}/", note_body(note, submit=True))
    assert done.status_code == 200, done.json()
    return done.json()


def sales_ledger(w):
    with use_tenant(w["tenant"]):
        tea = Item.objects.get(pk=w["tea"])
        group = LedgerGroup.objects.get(company_id=w["company"], code="sales_accounts")
        led = Ledger.objects.create(company_id=w["company"], group=group, name="Sales Tea")
        ItemGroupAccount.objects.filter(group=tea.item_group).update(sales_ledger=led)


def body(inv, **more):
    return {
        "invoice_date": TODAY.isoformat(),
        "transporter": inv["transporter"],
        "mode": inv["mode"],
        "vehicle_no": inv["vehicle_no"],
        "distance_km": inv["distance_km"],
        "lr_no": inv["lr_no"],
        **more,
    }


def entries(w, pk):
    with use_tenant(w["tenant"]):
        rows = GLEntry.objects.filter(voucher_type="sales_invoice", voucher_id=pk)
        return {(e.ledger.name, e.debit, e.credit) for e in rows.filter(is_reversal=False)}


def test_from_delivery_note_to_posting(seller, owner, books):  # noqa: F811
    w = books
    charges = [{"item": w[FREIGHT], "basis": "fixed", "rate": "500"}]
    note = sent_note(seller, w, charges=charges)
    assert note["billed"] is False and note["invoice"] is None
    early = call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {})
    assert early.status_code == 201, early.json()
    inv = early.json()
    assert inv["status"] == "draft" and inv["delivery_note_number"] == note["number"]
    # The note's quantities at the order's rates, and the order's freight.
    line = inv["lines"][0]
    assert (line["qty"], line["unit_name"], line["rate"], line["taxable"]) == (
        "10",
        "ctn",
        "2280",
        "22800.00",
    )
    assert [(c["item_name"], c["amount"]) for c in inv["charges"]] == [("Freight", "500.00")]
    # Same state: CGST + SGST. 22,800 at 5% and 500 at 18%.
    assert (inv["cgst_total"], inv["sgst_total"], inv["igst_total"]) == ("615.00", "615.00", "0.00")
    assert inv["total"] == "24530.00" and inv["place_of_supply"] == "27"
    assert inv["vehicle_no"] == "WB11D2290"  # from the note
    # The same note gives the same draft.
    again = call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {})
    assert again.json()["id"] == inv["id"]
    # The rate and the credit term are the order's: what is sent is ignored.
    rated = body(inv, rates=[{"line": line["id"], "rate": "2300"}], credit_term=None)
    saved = call(seller, "patch", f"sales-invoices/{inv['id']}/", rated)
    assert saved.status_code == 200, saved.json()
    assert saved.json()["lines"][0]["taxable"] == "22800.00"
    assert saved.json()["credit_term"] == inv["credit_term"]
    # No Sales Ledger yet: the popup's refusal, naming the line and the charge.
    path = f"sales-invoices/{inv['id']}/submit/"
    res = call(seller, "post", path, {})
    assert res.status_code == 400
    missing = res.json()["missing_accounts"]
    assert missing[0]["missing"] == ["Sales Ledger"]
    assert missing[0]["lines"] == ["Line 1 Green Tea 100 g", "Charge Freight"]
    sales_ledger(w)
    preview = call(seller, "get", f"sales-invoices/{inv['id']}/ledger-posting/").json()
    assert preview["posted"] is False
    assert [(r["ledger_name"], r["debit"], r["credit"]) for r in preview["rows"]] == [
        ("Organic Harvest Foods", "24530.00", "0.00"),
        ("Sales Tea", "0.00", "23300.00"),
        ("Output CGST", "0.00", "615.00"),
        ("Output SGST", "0.00", "615.00"),
        ("Cost of Tea", "2400.00", "0.00"),
        ("Goods Delivered but Bills not Made", "0.00", "2400.00"),
    ]
    done = call(seller, "post", path, {})
    assert done.status_code == 200, done.json()
    billed = done.json()
    assert billed["status"] == "submitted" and "/SI/" in billed["number"]
    assert billed["dues"] == [{"due_date": TODAY.isoformat(), "amount": "24530.00"}]
    assert entries(w, billed["id"]) == {
        ("Organic Harvest Foods", Decimal("24530.00"), Decimal("0.00")),
        ("Sales Tea", Decimal("0.00"), Decimal("23300.00")),
        ("Output CGST", Decimal("0.00"), Decimal("615.00")),
        ("Output SGST", Decimal("0.00"), Decimal("615.00")),
        ("Cost of Tea", Decimal("2400.00"), Decimal("0.00")),
        ("Goods Delivered but Bills not Made", Decimal("0.00"), Decimal("2400.00")),
    }
    with use_tenant(w["tenant"]):
        from core.models import Company

        gdnb = accounts.system_ledger(
            Company.objects.get(pk=w["company"]), accounts.GOODS_DELIVERED_NOT_BILLED
        )
        rows = GLEntry.objects.filter(ledger=gdnb)
        assert sum(e.debit - e.credit for e in rows) == 0  # the note's cost is cleared
    shown = call(seller, "get", f"delivery-notes/{note['id']}/").json()
    assert shown["billed"] is True and shown["invoice"]["number"] == billed["number"]
    # Billed: no second invoice, and the note cannot be cancelled first.
    assert "billed on" in str(
        call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {}).json()
    )
    stuck = call(owner, "post", f"delivery-notes/{note['id']}/cancel/", {"reason": "x"})
    assert "Cancel sales invoice" in str(stuck.json())
    assert "cannot be changed" in str(
        call(seller, "patch", f"sales-invoices/{inv['id']}/", body(inv)).json()
    )

    # Update Transport after Submit: no entries change.
    moved = call(
        seller,
        "post",
        f"sales-invoices/{inv['id']}/transport/",
        {"mode": "road", "vehicle_no": "mh 12 ab 1234", "distance_km": 150, "lr_no": "L-9"},
    )
    assert moved.status_code == 200, moved.json()
    assert moved.json()["vehicle_no"] == "MH12AB1234"
    assert moved.json()["transporter_name"] == "By Customer"

    # The portal's JSON, then its numbers typed in.
    got = seller.get(f"/api/v1/sales-invoices/{inv['id']}/json/", HTTP_HOST="alpha.localhost")
    assert got.status_code == 200
    doc = json.loads(got.content)[0]
    assert doc["DocDtls"] == {
        "Typ": "INV",
        "No": billed["number"],
        "Dt": TODAY.strftime("%d/%m/%Y"),
    }
    assert doc["TranDtls"]["SupTyp"] == "B2B" and doc["BuyerDtls"]["Pos"] == "27"
    assert [i["HsnCd"] for i in doc["ItemList"]] == ["0902", "9965"]
    assert doc["ItemList"][0]["Unit"] in ("CTN", "OTH")
    assert doc["ValDtls"]["TotInvVal"] == 24530.0 and doc["ValDtls"]["CgstVal"] == 615.0
    assert doc["EwbDtls"]["VehNo"] == "MH12AB1234" and doc["EwbDtls"]["Distance"] == 150
    eurl = f"sales-invoices/{inv['id']}/e-invoice/"
    bad = call(seller, "post", eurl, {"irn": "abc", "eway_bill_no": "12"}).json()
    assert "64 letters" in str(bad["irn"]) and "12 digits" in str(bad["eway_bill_no"])
    irn = "a5c12dca80e743ba2c7a5d2b1f7e49d3" * 2
    typed = call(
        seller,
        "post",
        eurl,
        {"irn": irn.upper(), "ack_no": "182621700012345", "eway_bill_no": "3410 1234 5678"},
    )
    assert typed.status_code == 200, typed.json()
    assert (typed.json()["irn"], typed.json()["eway_bill_no"]) == (irn, "341012345678")

    for layout in ("invoice", "copies", "eway"):
        pdf = seller.get(
            f"/api/v1/sales-invoices/{inv['id']}/pdf/?layout={layout}", HTTP_HOST="alpha.localhost"
        )
        assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    listed = call(seller, "get", f"companies/{w['company']}/sales-invoices/?view=submitted").json()
    assert [i["number"] for i in listed] == [billed["number"]]

    # Cancel: the entries are reversed and the note can be billed again.
    path = f"sales-invoices/{inv['id']}/cancel/"
    assert "Say why" in str(call(owner, "post", path, {}).json())
    gone = call(owner, "post", path, {"reason": "Wrong rate"}).json()
    assert gone["status"] == "cancelled"
    with use_tenant(w["tenant"]):
        rows = GLEntry.objects.filter(voucher_type="sales_invoice", voucher_id=inv["id"])
        assert sum(e.debit - e.credit for e in rows if e.ledger.name == "Sales Tea") == 0
    fresh = call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {})
    assert fresh.status_code == 201 and fresh.json()["id"] != inv["id"]
    assert len(fresh.json()["charges"]) == 1  # the cancelled one no longer counts


def test_interstate_bills_igst_and_a_draft_note_has_no_invoice(seller, books):  # noqa: F811
    w = books
    sales_ledger(w)
    note = sent_note(seller, w, customer="far")
    inv = call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {}).json()
    assert inv["interstate"] is True and inv["place_of_supply"] == "19"
    assert (inv["igst_total"], inv["cgst_total"]) == ("1140.00", "0.00")
    done = call(seller, "post", f"sales-invoices/{inv['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    assert ("Output IGST", Decimal("0.00"), Decimal("1140.00")) in entries(w, inv["id"])
    later = call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {})
    assert "billed on" in str(later.json())


def test_draft_note_cannot_be_billed(seller, books):  # noqa: F811
    w = books
    receive(w, w["bin"], "300", "A-LATE", LATER)
    _so, pl = picked_list(seller, w, cases="10")
    note = new_note(seller, pl)
    res = call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {})
    assert "Submit the delivery note first" in str(res.json())


def test_several_notes_on_one_invoice(seller, books):  # noqa: F811
    """Two orders' notes for one customer go on one invoice (one e-invoice)."""
    w = books
    sales_ledger(w)
    charges = [{"item": w[FREIGHT], "basis": "fixed", "rate": "500"}]
    first = sent_note(seller, w, charges=charges)
    second = sent_note(seller, w)
    elsewhere = sent_note(seller, w, customer="far")
    inv = call(seller, "post", f"delivery-notes/{first['id']}/invoice/", {}).json()
    more = call(seller, "get", f"sales-invoices/{inv['id']}/more-notes/").json()
    assert [n["number"] for n in more] == [second["number"]]  # not the other customer's
    url = f"sales-invoices/{inv['id']}/"
    wrong = call(seller, "patch", url, body(inv, delivery_notes=[first["id"], elsewhere["id"]]))
    assert wrong.status_code == 400 and "not billed yet" in str(wrong.json())
    both = call(seller, "patch", url, body(inv, delivery_notes=[first["id"], second["id"]]))
    assert both.status_code == 200, both.json()
    got = both.json()
    assert [n["number"] for n in got["delivery_notes"]] == [first["number"], second["number"]]
    assert [(ln["position"], ln["qty"], ln["note_number"]) for ln in got["lines"]] == [
        (1, "10", first["number"]),
        (2, "10", second["number"]),
    ]
    assert len(got["charges"]) == 1 and got["cost_total"] == "4800.00"
    # 45,600 at 5% + 500 at 18%.
    assert got["total"] == "48470.00"
    # The second note is on this draft now, so it makes no invoice of its own.
    own = call(seller, "post", f"delivery-notes/{second['id']}/invoice/", {})
    assert own.json()["id"] == inv["id"]
    done = call(seller, "post", f"sales-invoices/{inv['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    assert ("Goods Delivered but Bills not Made", Decimal("0.00"), Decimal("4800.00")) in entries(
        w, inv["id"]
    )
    for n in (first, second):
        shown = call(seller, "get", f"delivery-notes/{n['id']}/").json()
        assert shown["billed"] is True and shown["invoice"]["id"] == inv["id"]
    # Submitted: its notes cannot change.
    assert "cannot be changed" in str(call(seller, "patch", url, body(inv)).json())


def test_job_work_service_takes_its_delivery_hsn_on_the_eway_bill(seller, books):  # noqa: F811
    """A service item billed under its SAC (job work) carries its Delivery HSN on
    the e-way bill; the portal makes no e-way bill from a services-only e-invoice."""
    w = books
    sales_ledger(w)
    note = sent_note(seller, w)
    with use_tenant(w["tenant"]):
        Item.objects.filter(pk=w["tea"]).update(
            item_type=Item.SERVICE, hsn="998818", delivery_hsn="09024040"
        )
    inv = call(seller, "post", f"delivery-notes/{note['id']}/invoice/", {}).json()
    line = inv["lines"][0]
    assert (line["hsn"], line["goods_hsn"]) == ("998818", "09024040")
    assert inv["eway_with_einvoice"] is False
    done = call(seller, "post", f"sales-invoices/{inv['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    got = seller.get(f"/api/v1/sales-invoices/{inv['id']}/json/", HTTP_HOST="alpha.localhost")
    doc = json.loads(got.content)[0]
    assert doc["ItemList"][0]["HsnCd"] == "998818" and "EwbDtls" not in doc
    pdf = seller.get(
        f"/api/v1/sales-invoices/{inv['id']}/pdf/?layout=eway", HTTP_HOST="alpha.localhost"
    )
    assert pdf.status_code == 200
