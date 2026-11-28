"""Purchase invoices: billed against goods receipts, GST, rate differences, due dates."""

from decimal import Decimal as D

import pytest

from buying.models import GoodsReceiptLine
from core.models import Batch, CreditTerm, Item, Ledger, WarehouseLocation
from posting import accounts
from posting.models import StockLot
from posting.service import StockLine, Voucher, gl_balance, post, stock_value
from tenancy.context import use_tenant
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture
def received(grn, store, buyer, alpha):  # noqa: F811
    """All 600 Kg of tea and 30 packets received; then 150 Kg of tea used."""
    done = call(store, "post", url(grn), receipt(grn, [tea_line(grn), box_line(grn)], submit=True))
    assert done.status_code == 201, done.json()
    with use_tenant(alpha):
        from core.models import Branch, Company

        company = Company.objects.get(pk=grn["company"])
        tea = Item.objects.get(pk=grn["tea"])
        batch = Batch.objects.get(item=tea, number="DTT-26-118")
        bin1 = WarehouseLocation.objects.get(pk=grn["bin1"])
        voucher = Voucher(company, Branch.objects.get(pk=grn["branch"]), TODAY, "test_issue", 1,
                          "ISSUE-1")  # fmt: skip
        post(voucher, stock=[StockLine(tea, bin1, D("-150"), batch=batch)])
    return {**grn, "receipt": done.json()["id"], "receipt_number": done.json()["number"]}


def _inv_url(g):
    return f"companies/{g['company']}/purchase-invoices/"


def _body(g, draft, **more):
    return {
        "supplier": draft["supplier"],
        "branch": draft["branch"],
        "bill_no": "DTT/1201",
        "bill_date": TODAY.isoformat(),
        "credit_term": draft["credit_term"],
        "lines": [
            {"receipt_line": ln["receipt_line"], "qty": ln["qty"], "rate": ln["rate"],
             "gst_rate": ln["gst_rate"]}
            for ln in draft["lines"]
        ],
        "charges": [
            {"item": c["item"], "amount": c["amount"], "gst_rate": c["gst_rate"],
             "in_stock_cost": c["in_stock_cost"]}
            for c in draft["charges"]
        ],
        **more,
    }  # fmt: skip


def test_a_bill_at_a_higher_rate_revalues_stock_on_hand(buyer, owner, received, alpha):  # noqa: F811
    g = received
    unbilled = call(buyer, "get", f"{_inv_url(g)}unbilled/").json()
    assert [r["receipt_number"] for r in unbilled] == [g["receipt_number"]]
    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    assert [(ln["item_name"], ln["qty"], ln["rate"]) for ln in draft["lines"]] == [
        ("CTC Tea", "600", "250"),
        ("Tea Box", "30", "20"),
    ]
    assert [(c["amount"], c["in_stock_cost"]) for c in draft["charges"]] == [("6300.00", True)]
    with use_tenant(alpha):
        term = CreditTerm.objects.create(name="Half 30 half 60")
        term.parts.create(percent=50, event="bill", days=30)
        term.parts.create(percent=50, event="bill", days=60)
        before = stock_value(g_company(g))
    draft["credit_term"] = term.pk
    draft["lines"][0]["rate"] = "255"  # the supplier billed Rs 5 more a Kg

    made = call(buyer, "post", _inv_url(g), _body(g, draft))
    assert made.status_code == 201, made.json()
    inv = made.json()
    assert inv["status"] == "draft" and inv["taxable_total"] == "159900.00"
    names = [e["ledger"] for e in inv["entries"]]
    assert "Goods Received but Bills not Received" in names and "Input CGST" in names

    # Submit needs the supplier's bill total, and ours must match it.
    link = f"purchase-invoices/{inv['id']}/"
    refused = call(buyer, "patch", link, _body(g, draft, submit=True))
    assert refused.status_code == 400 and "bill_total" in refused.json()
    refused = call(buyer, "patch", link, _body(g, draft, bill_total="1000", submit=True))
    assert "does not match" in str(refused.json())
    done = call(buyer, "patch", link, _body(g, draft, bill_total=inv["total"], submit=True))
    assert done.status_code == 200, done.json()
    inv = done.json()
    assert inv["status"] == "submitted" and inv["number"]
    assert inv["posting_date"] == TODAY.isoformat()  # starts as the bill date

    tea, box = inv["lines"]
    # Tea: 153,000 billed + 6,263.86 of the freight, against 156,000 received.
    assert (tea["receipt_value"], tea["stock_difference"], tea["price_difference"]) == (
        "156000.00", "2447.90", "815.96",
    )  # fmt: skip
    # Packets: all still in stock, so the whole (negative) difference revalues them.
    assert (box["stock_difference"], box["price_difference"]) == ("-263.86", "0.00")
    assert [d["amount"] for d in inv["dues"]] == [
        str(D(inv["total"]) / 2),
        str(D(inv["total"]) - D(inv["total"]) / 2),
    ]
    with use_tenant(alpha):
        company = g_company(g)
        grni = accounts.system_ledger(company, accounts.GRNI)
        assert gl_balance(grni) == 0  # received and billed: nothing left waiting
        ppd = accounts.system_ledger(company, accounts.PRICE_DIFFERENCE)
        assert gl_balance(ppd) == D("815.96")
        assert stock_value(company) == before + D("2184.04")
        supplier = Ledger.objects.get(pk=g["local"])
        assert gl_balance(supplier) == -D(inv["total"])
        assert GoodsReceiptLine.objects.filter(receipt_id=g["receipt"],
                                               billed_qty=0).count() == 0  # fmt: skip
        lot = StockLot.objects.filter(item_id=g["tea"], qty_left=D("150")).first()
        assert lot.rate > D("260")  # cost now carries the freight and the new rate

    # Nothing is left to bill; the receipt cannot be cancelled while billed.
    assert call(buyer, "get", f"{_inv_url(g)}unbilled/").json() == []
    cancel_grn = call(owner, "post", f"goods-receipts/{g['receipt']}/cancel/", {"reason": "x"})
    assert cancel_grn.status_code == 400 and inv["number"] in str(cancel_grn.json())

    # Cancelling the invoice puts everything back.
    gone = call(owner, "post", f"purchase-invoices/{inv['id']}/cancel/", {"reason": "Wrong rate"})
    assert gone.status_code == 200, gone.json()
    with use_tenant(alpha):
        assert gl_balance(grni) == -D("156900.00")
        assert stock_value(company) == before
        assert not GoodsReceiptLine.objects.filter(receipt_id=g["receipt"], billed_qty__gt=0)
    assert len(call(buyer, "get", f"{_inv_url(g)}unbilled/").json()) == 1


def test_one_bill_number_once_per_supplier_and_no_over_billing(buyer, received):  # noqa: F811
    g = received
    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    tea_only = {**draft, "lines": draft["lines"][:1], "charges": []}
    first = call(buyer, "post", _inv_url(g), _body(g, tea_only)).json()
    done = call(buyer, "patch", f"purchase-invoices/{first['id']}/",
                _body(g, tea_only, bill_total=first["total"], submit=True))  # fmt: skip
    assert done.status_code == 200, done.json()

    again = call(buyer, "post", _inv_url(g), _body(g, tea_only))
    assert again.status_code == 400 and "still to be billed" in str(again.json())

    box_only = {**draft, "lines": draft["lines"][1:], "charges": []}
    second = call(buyer, "post", _inv_url(g), _body(g, box_only)).json()
    clash = call(buyer, "patch", f"purchase-invoices/{second['id']}/",
                 _body(g, box_only, bill_total=second["total"], submit=True))  # fmt: skip
    assert clash.status_code == 400 and "already entered" in str(clash.json())
    other = call(buyer, "patch", f"purchase-invoices/{second['id']}/",
                 _body(g, box_only, bill_no="DTT/1202", bill_total=second["total"],
                       submit=True))  # fmt: skip
    assert other.status_code == 200, other.json()
    listed = call(buyer, "get", _inv_url(g)).json()
    assert {r["bill_no"] for r in listed} == {"DTT/1201", "DTT/1202"}


def test_a_storekeeper_cannot_enter_bills(store, received):  # noqa: F811
    assert call(store, "post", _inv_url(received), {}).status_code == 403


def g_company(g):
    from core.models import Company

    return Company.objects.get(pk=g["company"])


def test_a_revalued_lot_used_since_blocks_the_cancel(buyer, owner, received, alpha):  # noqa: F811
    g = received
    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    draft["lines"][0]["rate"] = "260"
    inv = call(buyer, "post", _inv_url(g), _body(g, draft)).json()
    done = call(buyer, "patch", f"purchase-invoices/{inv['id']}/",
                _body(g, draft, bill_total=inv["total"], submit=True))  # fmt: skip
    assert done.status_code == 200, done.json()
    with use_tenant(alpha):
        from core.models import Branch

        tea = Item.objects.get(pk=g["tea"])
        voucher = Voucher(g_company(g), Branch.objects.get(pk=g["branch"]), TODAY, "test_issue",
                          2, "ISSUE-2")  # fmt: skip
        post(voucher, stock=[StockLine(tea, WarehouseLocation.objects.get(pk=g["bin2"]), D("-10"),
                                       batch=Batch.objects.get(item=tea))])  # fmt: skip
    gone = call(owner, "post", f"purchase-invoices/{inv['id']}/cancel/", {"reason": "x"})
    assert gone.status_code == 400 and "has since been issued" in str(gone.json())


def test_a_bill_above_a_locked_order_rate_tells_the_purchaser(buyer, received, alpha):  # noqa: F811
    """Sidharth, 2026-11-26: the Bill Rate stays open to match the supplier's bill;
    above a locked order rate the order's purchaser gets a notice (and a mail), so a
    rate-difference debit note can be issued."""
    from accounts.models import User
    from buying.models import PurchaseOrder, PurchaseOrderLine
    from core.models import Notification, SalesPerson

    g = received
    with use_tenant(alpha):
        me = User.objects.get(email="buyer@x.in")
        anil = SalesPerson.objects.create(
            name="Anil", is_purchaser=True, user=me, email="anil@x.in"
        )
        PurchaseOrder.objects.filter(lines__receipt_lines__receipt_id=g["receipt"]).update(
            purchaser=anil
        )
        PurchaseOrderLine.objects.filter(item_id=g["tea"]).update(
            rate_source="Supplier's own price"
        )
    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    assert [(ln["item_name"], ln["rate_locked"]) for ln in draft["lines"]] == [
        ("CTC Tea", True),
        ("Tea Box", False),
    ]
    draft["lines"][0]["rate"] = "255"  # Rs 5 a Kg above the agreed 250
    draft["lines"][1]["rate"] = "25"  # the box was never locked: no notice for it
    made = call(buyer, "post", _inv_url(g), _body(g, draft)).json()
    done = call(
        buyer, "patch", f"purchase-invoices/{made['id']}/",
        _body(g, draft, bill_total=made["total"], submit=True),
    )  # fmt: skip
    assert done.status_code == 200, done.json()
    with use_tenant(alpha):
        notes = list(Notification.objects.filter(user=me, title__contains="agreed price"))
    assert len(notes) == 1
    body = notes[0].body
    assert "CTC Tea" in body and "billed 255 against 250 per kg on 600, ₹ 3,000.00 more" in body
    assert "Tea Box" not in body
    assert "rate-difference debit note" in body
    assert "Not mailed: The company's mail account is not set up" in body


def test_bills_pending_lists_receipts_until_fully_billed(buyer, received):  # noqa: F811
    g = received
    pending_url = f"{url(g)}?view=unbilled"
    rows = call(buyer, "get", pending_url).json()
    assert [r["id"] for r in rows] == [g["receipt"]]
    row = rows[0]
    assert row["billed_state"] == "none"
    assert D(row["bill_pending_value"]) == D(row["stock_value"])
    assert all(D(ln["pending_qty"]) == D(ln["accepted_qty"]) for ln in row["bill_lines"])

    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    tea_only = {**draft, "lines": draft["lines"][:1], "charges": []}
    first = call(buyer, "post", _inv_url(g), _body(g, tea_only)).json()
    done = call(buyer, "patch", f"purchase-invoices/{first['id']}/",
                _body(g, tea_only, bill_total=first["total"], submit=True))  # fmt: skip
    assert done.status_code == 200, done.json()
    row = call(buyer, "get", pending_url).json()[0]
    assert row["billed_state"] == "part"
    assert D("0") < D(row["bill_pending_value"]) < D(row["stock_value"])
    tea = next(ln for ln in row["bill_lines"] if D(ln["billed_qty"]))
    assert D(tea["pending_qty"]) == 0

    box_only = {**draft, "lines": draft["lines"][1:], "charges": []}
    second = call(buyer, "post", _inv_url(g), _body(g, box_only, bill_no="DTT/1202")).json()
    done = call(buyer, "patch", f"purchase-invoices/{second['id']}/",
                _body(g, box_only, bill_no="DTT/1202", bill_total=second["total"],
                      submit=True))  # fmt: skip
    assert done.status_code == 200, done.json()
    assert call(buyer, "get", pending_url).json() == []
    everything = call(buyer, "get", f"{url(g)}?view=all").json()
    assert everything[0]["billed_state"] == "billed"
