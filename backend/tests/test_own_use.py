"""Own Use (Sidharth, 2026-11-22, preview 9c in mockups/planning): our own
stock used inside the company leaves its bins at FIFO cost: Dr the line's
Expense Ledger (the item's own Expense Account to start with), Cr Stock. A
draft counts as Reserved in the Stock Check."""

from decimal import Decimal

import pytest

from buying import planning
from core.models import Branch, Item, Ledger, LedgerGroup
from posting.models import GLEntry, StockMove
from tenancy.context import use_tenant
from tests.test_delivery_notes import books  # noqa: F401  (fixture)
from tests.test_pick_lists import receive
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    owner,
    world,
)
from tests.test_stock_transfers import stores  # noqa: F401  (fixture)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def url(w):
    return f"companies/{w['company']}/own-use/"


def body(w, qty="24", **more):
    return {
        "branch": w["branch"],
        "area": w["fg"],
        "entry_date": TODAY.isoformat(),
        "reason": "Office pantry, November",
        "lines": [{"item": w["tea"], "unit": w["pcs"], "qty": qty}],
        **more,
    }


def gl(w, pk):
    with use_tenant(w["tenant"]):
        rows = GLEntry.objects.filter(voucher_type="own_use", voucher_id=pk)
        return {(e.ledger.name, e.debit, e.credit, e.is_reversal) for e in rows}


def test_own_use_posts_at_fifo_cost(stores, owner, books):  # noqa: F811
    w = books
    receive(w, w["bin"], "300")  # at 10 a packet
    with use_tenant(w["tenant"]):
        group = LedgerGroup.objects.get(company_id=w["company"], code="indirect_expenses")
        welfare = Ledger.objects.create(company_id=w["company"], group=group, name="Staff Welfare")
    made = call(stores, "post", url(w), body(w))
    assert made.status_code == 201, made.json()
    e = made.json()
    [line] = e["lines"]
    assert line["ledger_name"] == "Cost of Tea"  # the item group's, as it has no own account
    assert [(b["location_name"], b["qty"]) for b in line["bins"]] == [("FG-R1-B1", "24")]
    with use_tenant(w["tenant"]):
        head = Branch.objects.get(pk=w["branch"])
        assert planning.reserved(head, [w["tea"]])[w["tea"]] == 24  # a draft is Reserved
    preview = call(stores, "get", f"own-use/{e['id']}/ledger-posting/").json()
    assert not preview["posted"]
    assert {(r["ledger_name"], r["debit"], r["credit"]) for r in preview["rows"]} == {
        ("Cost of Tea", "240.00", "0.00"),
        ("Stock", "0.00", "240.00"),
    }
    # Charged to Staff Welfare instead, and submitted.
    lines = [{"item": w["tea"], "unit": w["pcs"], "qty": "24", "expense_ledger": welfare.pk}]
    done = call(stores, "patch", f"own-use/{e['id']}/", body(w, lines=lines, submit=True))
    assert done.status_code == 200, done.json()
    e = done.json()
    assert e["status"] == "submitted" and "/OU/" in e["number"] and e["value"] == "240.00"
    assert gl(w, e["id"]) == {
        ("Staff Welfare", Decimal("240.00"), Decimal("0.00"), False),
        ("Stock", Decimal("0.00"), Decimal("240.00"), False),
    }
    with use_tenant(w["tenant"]):
        assert planning.reserved(head, [w["tea"]]).get(w["tea"], 0) == 0
        moves = StockMove.objects.filter(voucher_type="own_use", voucher_id=e["id"])
        assert [(m.qty, m.value) for m in moves] == [(Decimal("-24"), Decimal("-240.00"))]
    slip = call(stores, "get", f"own-use/{e['id']}/pdf/")
    assert slip.status_code == 200 and slip["Content-Type"] == "application/pdf"
    gone = call(owner, "post", f"own-use/{e['id']}/cancel/", {"reason": "Not used"})
    assert gone.status_code == 200, gone.json()
    assert ("Staff Welfare", Decimal("0.00"), Decimal("240.00"), True) in gl(w, e["id"])
    with use_tenant(w["tenant"]):
        assert sum(m.qty for m in StockMove.objects.filter(item=w["tea"])) == 300


def test_short_stock_and_missing_ledgers(stores, world):  # noqa: F811
    w = world
    receive(w, w["bin"], "10")
    short = call(stores, "post", url(w), body(w, submit=True))
    assert short.status_code == 400
    texts = [p["text"] for p in short.json()["problems"]]
    assert any("only 10 " in t and "is free" in t for t in texts), texts
    assert any("pick the Expense Ledger" in t for t in texts)
    # Enough stock and a ledger to charge, but no Stock Ledger on the item group.
    with use_tenant(w["tenant"]):
        group = LedgerGroup.objects.get(company_id=w["company"], code="indirect_expenses")
        office = Ledger.objects.create(company_id=w["company"], group=group, name="Office")
    lines = [{"item": w["tea"], "unit": w["pcs"], "qty": "5", "expense_ledger": office.pk}]
    refused = call(stores, "post", url(w), body(w, lines=lines, submit=True))
    assert refused.status_code == 400 and refused.json()["missing_accounts"]
    assert refused.json()["id"]  # the draft is kept


def test_customer_goods_are_not_ours_to_use(stores, world):  # noqa: F811
    w = world
    with use_tenant(w["tenant"]):
        Item.objects.filter(pk=w["tea"]).update(default_request_type=Item.CUSTOMER_PROVIDED)
    refused = call(stores, "post", url(w), body(w))
    assert refused.status_code == 400 and "customer's own goods" in str(refused.json())
