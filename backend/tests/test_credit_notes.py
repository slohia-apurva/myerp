"""Credit notes against a sales invoice (Sidharth, 2026-11-21, previews 18a/18b/18c
in mockups/sales): one entry with three types, all with GST.

* goods come back: Dr Sales Ledger + Output GST, Cr customer; the goods go back
  into their batch in a bin at the cost they left at: Dr Stock, Cr COGS;
* goods not coming back: the same credit with no stock or cost;
* rate difference: the billed quantity (less returns) at a lower rate."""

import json
from decimal import Decimal

import pytest

from core.models import Company, Item, WarehouseLocation
from posting import accounts
from posting.models import GLEntry, StockMove
from tenancy.context import use_tenant
from tests.test_delivery_notes import books  # noqa: F401
from tests.test_sales_invoices import sales_ledger, sent_note
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    owner,
    seller,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def billed(client, w):
    """10 cartons sent and billed at 2,280 + 5% GST (same state)."""
    sales_ledger(w)
    note = sent_note(client, w)
    inv = call(client, "post", f"delivery-notes/{note['id']}/invoice/", {}).json()
    done = call(client, "post", f"sales-invoices/{inv['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    return done.json()


def body(note, **more):
    return {
        "kind": note["kind"],
        "reason": note["reason"],
        "note_date": TODAY.isoformat(),
        **more,
    }


def entries(w, pk):
    with use_tenant(w["tenant"]):
        rows = GLEntry.objects.filter(voucher_type="credit_note", voucher_id=pk)
        return {(e.ledger.name, e.debit, e.credit) for e in rows.filter(is_reversal=False)}


def stock_name(w):
    with use_tenant(w["tenant"]):
        company = Company.objects.get(pk=w["company"])
        return accounts.stock_ledger(company, Item.objects.get(pk=w["tea"])).name


def bin_stock(w):
    with use_tenant(w["tenant"]):
        tea = Item.objects.get(pk=w["tea"])
        rows = StockMove.objects.filter(item=tea, location_id=w["bin"])
        return sum((m.qty for m in rows), Decimal("0"))


def test_goods_come_back_with_gst_and_stock(seller, owner, books):  # noqa: F811
    w = books
    inv = billed(seller, w)
    start = bin_stock(w)
    made = call(seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "goods_back"})
    assert made.status_code == 201, made.json()
    note = made.json()
    assert note["status"] == "draft" and note["kind_label"] == "Sales Return – goods come back"
    # One line per batch that went out, from the bin it left, nothing credited yet.
    [line] = note["lines"]
    assert (line["batch_number"], line["sent"], line["most"], line["qty"]) == (
        "A-LATE",
        "10",
        "10",
        "0",
    )
    assert line["location"] == w["bin"] and line["cost_rate"] == "240"
    # The same invoice gives the same draft while it is open.
    again = call(seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "rate"})
    assert again.json()["id"] == note["id"]
    url = f"credit-notes/{note['id']}/"
    too_many = call(seller, "patch", url, body(note, lines=[{"id": line["id"], "qty": "11"}]))
    assert too_many.status_code == 400 and "at most 10" in str(too_many.json())
    saved = call(seller, "patch", url, body(note, lines=[{"id": line["id"], "qty": "2"}]))
    assert saved.status_code == 200, saved.json()
    got = saved.json()
    # 2 ctn at the invoice's 2,280 + 5% GST in the same state.
    assert (got["taxable_total"], got["cgst_total"], got["sgst_total"]) == (
        "4560.00",
        "114.00",
        "114.00",
    )
    assert got["total"] == "4788.00"
    stock = stock_name(w)
    preview = call(seller, "get", f"{url}ledger-posting/").json()
    assert [(r["ledger_name"], r["debit"], r["credit"]) for r in preview["rows"]] == [
        ("Sales Tea", "4560.00", "0.00"),
        ("Output CGST", "114.00", "0.00"),
        ("Output SGST", "114.00", "0.00"),
        ("Organic Harvest Foods", "0.00", "4788.00"),
        (stock, "480.00", "0.00"),
        ("Cost of Tea", "0.00", "480.00"),
    ]
    done = call(seller, "post", f"{url}submit/", {})
    assert done.status_code == 200, done.json()
    cn = done.json()
    assert cn["status"] == "submitted" and "/CN/" in cn["number"]
    assert entries(w, cn["id"]) == {
        ("Sales Tea", Decimal("4560.00"), Decimal("0.00")),
        ("Output CGST", Decimal("114.00"), Decimal("0.00")),
        ("Output SGST", Decimal("114.00"), Decimal("0.00")),
        ("Organic Harvest Foods", Decimal("0.00"), Decimal("4788.00")),
        (stock, Decimal("480.00"), Decimal("0.00")),
        ("Cost of Tea", Decimal("0.00"), Decimal("480.00")),
    }
    # 2 cartons of 24 packets back in the bin, in their batch.
    assert bin_stock(w) == start + 48
    assert cn["cost_total"] == "480.00"
    assert cn["dues_after"][0]["less"] == "4788.00"
    shown = call(seller, "get", f"sales-invoices/{inv['id']}/").json()
    assert [c["number"] for c in shown["credit_notes"]] == [cn["number"]]

    # The e-invoice JSON is a CRN naming the invoice.
    got = seller.get(f"/api/v1/credit-notes/{cn['id']}/json/", HTTP_HOST="alpha.localhost")
    doc = json.loads(got.content)[0]
    assert doc["DocDtls"]["Typ"] == "CRN" and doc["DocDtls"]["No"] == cn["number"]
    assert doc["RefDtls"]["PrecDocDtls"][0]["InvNo"] == inv["number"]
    assert doc["ValDtls"]["TotInvVal"] == 4788.0 and doc["ItemList"][0]["Qty"] == 2.0
    irn = "b5c12dca80e743ba2c7a5d2b1f7e49d3" * 2
    typed = call(seller, "post", f"{url}e-invoice/", {"irn": irn, "ack_no": "1826"})
    assert typed.status_code == 200 and typed.json()["irn"] == irn
    pdf = seller.get(f"/api/v1/credit-notes/{cn['id']}/pdf/", HTTP_HOST="alpha.localhost")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"

    # 8 left to return; the invoice cannot be cancelled while the note stands.
    second = call(
        seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "goods_kept"}
    )
    assert second.status_code == 201
    assert second.json()["lines"][0]["most"] == "8"
    stuck = call(owner, "post", f"sales-invoices/{inv['id']}/cancel/", {"reason": "x"})
    assert stuck.status_code == 400 and cn["number"] in str(stuck.json())

    # Cancel: entries and stock reversed.
    gone = call(owner, "post", f"{url}cancel/", {"reason": "Wrong qty"})
    assert gone.status_code == 200 and gone.json()["status"] == "cancelled"
    assert bin_stock(w) == start
    listed = call(seller, "get", f"companies/{w['company']}/credit-notes/?view=cancelled").json()
    assert [n["number"] for n in listed] == [cn["number"]]


def test_goods_not_coming_back_and_rate_difference(seller, books):  # noqa: F811
    w = books
    inv = billed(seller, w)
    start = bin_stock(w)
    note = call(
        seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "goods_kept"}
    ).json()
    [line] = note["lines"]
    assert line["batch"] is None and line["location"] is None and line["most"] == "10"
    url = f"credit-notes/{note['id']}/"
    kept = body(note, reason="destroyed", lines=[{"id": line["id"], "qty": "1"}], submit=True)
    done = call(seller, "patch", url, kept)
    assert done.status_code == 200, done.json()
    cn = done.json()
    assert cn["status"] == "submitted" and cn["total"] == "2394.00"
    # No stock and no cost move.
    assert bin_stock(w) == start
    assert {e[0] for e in entries(w, cn["id"])} == {
        "Sales Tea",
        "Output CGST",
        "Output SGST",
        "Organic Harvest Foods",
    }

    # Rate difference: the 9 left at 2,200 instead of 2,280.
    rate = call(seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "rate"}).json()
    [line] = rate["lines"]
    assert (line["qty"], line["new_rate"], line["rate_left"]) == ("9", "2280", "2280")
    url = f"credit-notes/{rate['id']}/"
    higher = call(seller, "patch", url, body(rate, lines=[{"id": line["id"], "new_rate": "2300"}]))
    assert higher.status_code == 400 and "supplementary" in str(higher.json())
    nothing = call(seller, "post", f"{url}submit/", {})
    assert nothing.status_code == 400 and "lower rate" in str(nothing.json())
    lower = body(rate, reason="rate_lower", lines=[{"id": line["id"], "new_rate": "2200"}])
    done = call(seller, "patch", url, {**lower, "submit": True})
    assert done.status_code == 200, done.json()
    rn = done.json()
    # 9 × 80 = 720 + 5% = 756.
    assert (rn["lines"][0]["rate"], rn["taxable_total"], rn["total"]) == ("80", "720.00", "756.00")
    assert entries(w, rn["id"]) == {
        ("Sales Tea", Decimal("720.00"), Decimal("0.00")),
        ("Output CGST", Decimal("18.00"), Decimal("0.00")),
        ("Output SGST", Decimal("18.00"), Decimal("0.00")),
        ("Organic Harvest Foods", Decimal("0.00"), Decimal("756.00")),
    }
    # Both notes come off the invoice's due.
    assert rn["dues_after"][0]["less"] == str(Decimal("2394.00") + Decimal("756.00"))
    # A further rate difference starts from 2,200.
    more = call(seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "rate"}).json()
    assert more["lines"][0]["rate_left"] == "2200"


def test_type_change_refills_and_bin_must_be_of_the_branch(seller, books):  # noqa: F811
    w = books
    inv = billed(seller, w)
    note = call(
        seller, "post", f"sales-invoices/{inv['id']}/credit-note/", {"kind": "goods_kept"}
    ).json()
    url = f"credit-notes/{note['id']}/"
    changed = call(seller, "patch", url, body(note, kind="goods_back")).json()
    assert changed["kind"] == "goods_back" and changed["lines"][0]["batch_number"] == "A-LATE"
    line = changed["lines"][0]
    with use_tenant(w["tenant"]):
        other = WarehouseLocation.objects.exclude(branch_id=changed["branch"]).first()
    if other is not None:
        bad = call(
            seller,
            "patch",
            url,
            body(changed, lines=[{"id": line["id"], "qty": "1", "location": other.pk}]),
        )
        assert bad.status_code == 400 and "pick a bin" in str(bad.json())
    early = call(seller, "patch", url, body(changed, note_date="2020-01-01"))
    assert early.status_code == 400 and "on or after" in str(early.json())
