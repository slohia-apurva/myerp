# ruff: noqa: F811  (pytest fixtures are imported and then named as arguments)
"""Purchase returns and debit notes (Sidharth, 2026-11-15, previews 74/75):
goods sent back from a receipt, then settled against the supplier's bill."""

from decimal import Decimal as D

import pytest

from core.models import Ledger
from posting import accounts
from posting.service import gl_balance, stock_value
from tenancy.context import use_tenant
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import _body, _inv_url, g_company, received  # noqa: F401
from tests.test_purchase_orders import TODAY, buyer, call, owner, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _ret_url(g):
    return f"companies/{g['company']}/purchase-returns/"


def _dn_url(g):
    return f"companies/{g['company']}/debit-notes/"


def _send_back(client, g, boxes="3", submit=True):
    """Return `boxes` Tea Boxes from the receipt; submitted unless told not to."""
    draft = call(client, "get", f"{_ret_url(g)}draft-from/?receipt={g['receipt']}").json()
    lines = [
        {"receipt_line": ln["receipt_line"], "location": ln["location"], "batch": ln["batch"],
         "qty": boxes if ln["item_name"] == "Tea Box" else "0"}
        for ln in draft["lines"]
    ]  # fmt: skip
    body = {"receipt": g["receipt"], "return_date": TODAY.isoformat(), "reason": "damaged",
            "lines": lines, "submit": submit}  # fmt: skip
    done = call(client, "post", _ret_url(g), body)
    assert done.status_code == 201, done.json()
    return done.json()


def _bill(client, g, box_qty=None):
    draft = call(client, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    if box_qty is not None:
        draft["lines"][1]["qty"] = box_qty
    inv = call(client, "post", _inv_url(g), _body(g, draft)).json()
    done = call(client, "patch", f"purchase-invoices/{inv['id']}/",
                _body(g, draft, bill_total=inv["total"], submit=True))  # fmt: skip
    assert done.status_code == 200, done.json()
    return done.json()


def _grni(g):
    return gl_balance(accounts.system_ledger(g_company(g), accounts.GRNI))


def test_return_then_full_bill_then_debit_note_settles_everything(
    store, buyer, owner, received, alpha
):  # noqa: F811,E501
    g = received
    with use_tenant(alpha):
        before = stock_value(g_company(g))
    ret = _send_back(store, g)
    assert ret["status"] == "submitted" and ret["number"]
    names = {e["ledger"]: (e["debit"], e["credit"]) for e in ret["entries"]}
    # 3 of 30 boxes whose receipt value (with freight) was 900.00.
    assert names["Goods Received but Bills not Received"] == ("90.00", "0.00")
    with use_tenant(alpha):
        assert stock_value(g_company(g)) == before - D("90.00")

    # The supplier bills all 30 boxes, as received: the new bill offers all 30, and a
    # debit note settles the 3 sent back (Sidharth, 2026-11-26).
    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    assert draft["lines"][1]["qty"] == "30"
    inv = _bill(buyer, g)
    with use_tenant(alpha):
        assert _grni(g) == D("90.00")  # the returned boxes wait for the debit note

    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}").json()
    assert made["invoice"] == inv["id"]
    assert [(ln["item_name"], ln["qty"], ln["rate"]) for ln in made["lines"]] == [
        ("Tea Box", "3", "20")
    ]
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(),
            "lines": [{k: ln[k] for k in ("invoice_line", "return_line", "qty")}
                      for ln in made["lines"]],
            "submit": True}  # fmt: skip
    done = call(buyer, "post", _dn_url(g), body)
    assert done.status_code == 201, done.json()
    note = done.json()
    assert note["number"] and note["taxable_total"] == "60.00"
    entries = {e["ledger"]: (e["debit"], e["credit"]) for e in note["entries"]}
    assert entries["Goods Received but Bills not Received"] == ("0.00", "90.00")
    assert entries["Purchase Price Difference"] == ("30.00", "0.00")  # freight on what went back
    assert sum(D(d) for d, _ in entries.values()) == sum(D(c) for _, c in entries.values())
    assert note["dues_after"][-1]["less"] == note["total"]
    with use_tenant(alpha):
        assert _grni(g) == 0
        supplier = Ledger.objects.get(pk=g["local"])
        assert gl_balance(supplier) == -D(inv["total"]) + D(note["total"])

    # Nothing more to debit; the bill and the return are held by the note.
    again = call(buyer, "get", f"{_dn_url(g)}draft-from/?invoice={inv['id']}")
    assert again.status_code == 400
    held = call(owner, "post", f"purchase-invoices/{inv['id']}/cancel/", {"reason": "x"})
    assert held.status_code == 400 and note["number"] in str(held.json())
    held = call(owner, "post", f"purchase-returns/{ret['id']}/cancel/", {"reason": "x"})
    assert held.status_code == 400 and note["number"] in str(held.json())

    gone = call(owner, "post", f"debit-notes/{note['id']}/cancel/", {"reason": "Wrong"})
    assert gone.status_code == 200, gone.json()
    with use_tenant(alpha):
        assert _grni(g) == D("90.00")


def test_a_bill_without_the_returned_goods_needs_no_debit_note(
    store, buyer, owner, received, alpha
):  # noqa: F811,E501
    g = received
    ret = _send_back(store, g)
    _bill(buyer, g, box_qty="27")  # the supplier left the 3 out
    with use_tenant(alpha):
        assert _grni(g) == 0
    refused = call(buyer, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}")
    assert refused.status_code == 400 and "no Debit Note is needed" in str(refused.json())
    assert call(buyer, "get", f"{_inv_url(g)}unbilled/").json() == []


def test_a_return_holds_its_receipt_and_cancelling_brings_the_goods_back(
    store, owner, received, alpha
):  # noqa: F811,E501
    g = received
    with use_tenant(alpha):
        before = stock_value(g_company(g))
    ret = _send_back(store, g, boxes="30")
    over = call(store, "post", _ret_url(g), {
        "receipt": g["receipt"], "return_date": TODAY.isoformat(),
        "lines": [{"receipt_line": ret["lines"][0]["receipt_line"],
                   "location": ret["lines"][0]["location"], "qty": "1"}]})  # fmt: skip
    assert over.status_code == 400 and "can still go back" in str(over.json())
    held = call(owner, "post", f"goods-receipts/{g['receipt']}/cancel/", {"reason": "x"})
    assert held.status_code == 400 and ret["number"] in str(held.json())
    gone = call(owner, "post", f"purchase-returns/{ret['id']}/cancel/", {"reason": "Kept them"})
    assert gone.status_code == 200, gone.json()
    with use_tenant(alpha):
        assert stock_value(g_company(g)) == before
        assert _grni(g) == -D("156900.00")


def test_goods_sent_back_after_a_dearer_bill(store, buyer, received, alpha):
    """The bill (Rs 25 a box against 20) revalued the boxes on hand; sending 3
    back takes their new value out, and the debit note at the bill's rate
    settles "Goods Received but Bills not Received" exactly."""
    g = received
    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    draft["lines"][1]["rate"] = "25"
    inv = call(buyer, "post", _inv_url(g), _body(g, draft)).json()
    inv = call(buyer, "patch", f"purchase-invoices/{inv['id']}/",
               _body(g, draft, bill_total=inv["total"], submit=True)).json()  # fmt: skip
    ret = _send_back(store, g)
    entries = {e["ledger"]: (e["debit"], e["credit"]) for e in ret["entries"]}
    assert entries["Goods Received but Bills not Received"] == ("90.00", "0.00")
    # The bill revalued the boxes; the change in their value is a price difference.
    assert sum(D(x) for x in entries["Purchase Price Difference"]) > 0
    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?invoice={inv['id']}").json()
    assert [(ln["qty"], ln["rate"]) for ln in made["lines"]] == [("3", "25")]
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(), "submit": True,
            "lines": [{k: ln[k] for k in ("invoice_line", "return_line", "qty")}
                      for ln in made["lines"]]}  # fmt: skip
    note = call(buyer, "post", _dn_url(g), body)
    assert note.status_code == 201, note.json()
    with use_tenant(alpha):
        assert _grni(g) == 0


def test_a_draft_return_shows_its_entries_at_receipt_cost(store, buyer, received, alpha):
    g = received
    draft = _send_back(store, g, submit=False)
    assert draft["status"] == "draft" and not draft["number"]
    entries = draft["entries"]
    grni = next(e for e in entries if e["debit"] != "0.00")
    assert grni["ledger"] == "Goods Received but Bills not Received"
    assert D(grni["debit"]) == D(draft["value"]) > 0
    assert sum(D(e["credit"]) for e in entries) == D(draft["value"])


def _listed(client, g, view="submitted"):
    rows = call(client, "get", f"{_ret_url(g)}?view={view}").json()
    return {r["id"]: (r["debit_state"], r["debit_label"], r["debit_notes"]) for r in rows}


def test_the_list_shows_which_returns_still_need_a_debit_note(store, buyer, received, alpha):  # noqa: F811,E501
    """Sidharth, 2026-11-26 (preview 107): the "Debit Note" column and the
    "Debit Note Pending" view on the Purchase Return list."""
    g = received
    ret = _send_back(store, g)
    draft = _send_back(store, g, boxes="1", submit=False)
    assert _listed(buyer, g)[ret["id"]][0] == "waiting"
    assert _listed(buyer, g, "draft")[draft["id"]][0] == ""
    assert _listed(buyer, g, "debit_pending") == {}

    # Billed for all 30 boxes: the 3 sent back now need a debit note.
    inv = _bill(buyer, g, box_qty="30")
    assert _listed(buyer, g, "debit_pending") == {ret["id"]: ("pending", "Pending", "")}
    view = call(buyer, "get", f"purchase-returns/{ret['id']}/").json()
    assert view["debit_state"] == "pending" and view["to_debit"]

    made = call(buyer, "get", f"{_dn_url(g)}draft-from/?return={ret['id']}").json()
    body = {"invoice": inv["id"], "note_date": TODAY.isoformat(),
            "lines": [{"invoice_line": ln["invoice_line"], "return_line": ln["return_line"],
                       "qty": "2"} for ln in made["lines"]],
            "submit": True}  # fmt: skip
    note = call(buyer, "post", _dn_url(g), body).json()
    assert _listed(buyer, g, "debit_pending") == {ret["id"]: ("part", "Part Done", note["number"])}

    body["lines"][0]["qty"] = "1"
    last = call(buyer, "post", _dn_url(g), body).json()
    assert _listed(buyer, g, "debit_pending") == {}
    state, label, notes = _listed(buyer, g)[ret["id"]]
    assert (state, label) == ("done", "Done")
    assert notes == ", ".join(sorted([note["number"], last["number"]]))


def test_a_return_the_bill_left_out_needs_no_debit_note_in_the_list(store, buyer, received, alpha):  # noqa: F811,E501
    g = received
    ret = _send_back(store, g)
    _bill(buyer, g, box_qty="20")  # 7 boxes still to be billed: they may yet include these 3
    assert _listed(buyer, g)[ret["id"]][0] == "waiting"
    rest = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    assert [ln["qty"] for ln in rest["lines"]] == ["10"]  # the boxes, returns included
    rest["lines"][0]["qty"] = "7"
    inv = call(buyer, "post", _inv_url(g), _body(g, rest, bill_no="DTT/1202")).json()
    body = _body(g, rest, bill_no="DTT/1202", bill_total=inv["total"], submit=True)
    done = call(buyer, "patch", f"purchase-invoices/{inv['id']}/", body)
    assert done.status_code == 200, done.json()  # 27 billed in all: the 3 were left out
    assert _listed(buyer, g)[ret["id"]][:2] == (
        "not_needed",
        "Not Needed (Billed for Actual Qty Recd.)",
    )


def test_goods_sent_back_still_wait_for_their_bill_in_bills_pending(store, buyer, received):
    """The supplier bills the full received quantity; a debit note settles the
    return, so a return does not take a receipt off "Bills Pending"."""
    g = received
    _send_back(store, g, boxes="3")
    pending = call(buyer, "get", f"{url(g)}?view=unbilled").json()
    box = next(ln for ln in pending[0]["bill_lines"] if ln["item_name"] == "Tea Box")
    assert D(box["pending_qty"]) == D("30")
    _bill(buyer, g)
    assert call(buyer, "get", f"{url(g)}?view=unbilled").json() == []
