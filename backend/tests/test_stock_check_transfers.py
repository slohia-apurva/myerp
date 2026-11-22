"""Stock Check "To Transfer" (Sidharth, 2026-11-22, preview 9b): items a branch
gets from another branch are suggested in the sales unit with what the source
has free; "Create Stock Transfers" makes one DRAFT transfer per source branch.
Sales order Submit and the daily run make the same drafts. A draft counts as
Incoming here and Reserved at the source, so nothing is sent twice."""

from decimal import Decimal

import pytest
from django.core.management import call_command

from buying import planning
from core.models import Branch, Company, ItemPlan, Notification
from stock.models import StockTransfer
from tenancy.context import use_tenant
from tests.test_delivery_notes import books  # noqa: F401  (fixture)
from tests.test_pick_lists import receive
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    order,
    owner,
    seller,
    world,
)
from tests.test_stock_transfers import depot, stores  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture
def fed(depot):  # noqa: F811
    """The depot gets tea from the head office: safety 48 packets, up to 96."""
    w = depot
    with use_tenant(w["tenant"]):
        ItemPlan.objects.create(
            item_id=w["tea"], branch_id=w["depot"], fulfilment=ItemPlan.TRANSFER,
            transfer_from_id=w["branch"], transfer_days=2, safety_qty=48, order_up_to=96,
        )  # fmt: skip
    return w


def check(client, w, show="short"):
    path = f"companies/{w['company']}/stock-check/?branch={w['depot']}&show={show}"
    got = call(client, "get", path)
    assert got.status_code == 200, got.json()
    return got.json()


def test_to_transfer_rows_and_drafts(owner, stores, fed):  # noqa: F811
    w = fed
    receive(w, w["bin"], "300")  # at the head office
    data = check(owner, w)
    assert data["rows"] == []  # nothing to buy
    [row] = data["transfers"]
    assert (row["item_name"], row["expected"], row["suggested"], row["unit_name"]) == (
        "Green Tea 100 g",
        "0",
        "4",  # 96 packets = 4 cartons
        "ctn",
    )
    assert row["from_branch"] == w["branch"]
    assert row["free_at_source"] == "12.5" and not row["source_short"]
    assert row["transfer_days"] == 2 and not row["other_gstin"]
    line = {"item": w["tea"], "unit": row["unit"], "qty": "4", "from_branch": w["branch"]}
    body = {"branch": w["depot"], "lines": [line]}
    made = call(stores, "post", f"companies/{w['company']}/stock-check/transfers/", body)
    assert made.status_code == 201, made.json()
    [t] = made.json()
    assert t["lines"] == 1
    with use_tenant(w["tenant"]):
        st = StockTransfer.objects.get(pk=t["id"])
        assert st.status == "draft" and st.to_branch_id == w["depot"]
        assert st.reason == "Made by Stock Check." and st.stock_check_run_id
        assert (st.expected_date - st.transfer_date).days == 2
        head = Branch.objects.get(pk=w["branch"])
        source = st.from_branch.name
        assert planning.reserved(head, [w["tea"]])[w["tea"]] == 96
    # Counted as Incoming now: no longer short, and listed as a draft.
    again = check(owner, w)
    assert again["transfers"] == []
    assert [d["from_branch_name"] for d in again["transfer_drafts"]] == [source]


def test_a_source_short_is_only_warned(owner, fed):  # noqa: F811
    w = fed
    receive(w, w["bin"], "24")
    [row] = check(owner, w)["transfers"]
    assert row["free_at_source"] == "1" and row["source_short"]


def test_sales_order_submit_makes_a_draft_transfer(seller, fed):  # noqa: F811
    w = fed
    receive(w, w["bin"], "300")
    lines = [{"item": w["tea"], "unit": w["case"], "qty": "2", "rate": "2280"}]
    body = order(w, lines=lines, branch=w["depot"], submit=True)
    made = call(seller, "post", f"companies/{w['company']}/sales-orders/", body)
    assert made.status_code == 201, made.json()
    so = made.json()
    [note] = so["shortages"]
    assert note["action"] == "st" and note["qty"] == "6"  # 48 out, refill to 96: 144 = 6 ctn
    [st] = so["stock_transfers"]
    assert st["status"] == "draft" and st["id"] == note["transfer"]
    assert so["lines"][0]["cover"]["kind"] == "st"
    assert so["lines"][0]["cover"]["text"] == "Draft ST"
    with use_tenant(w["tenant"]):
        t = StockTransfer.objects.get(pk=st["id"])
        assert t.sales_order_id == so["id"] and t.lines.get().qty == Decimal("6")
    # Planning again sends nothing twice.
    again = call(seller, "post", f"sales-orders/{so['id']}/plan/", {}).json()
    assert len(again["stock_transfers"]) == 1


def test_daily_run_makes_draft_transfers(owner, fed):  # noqa: F811
    w = fed
    receive(w, w["bin"], "300")
    with use_tenant(w["tenant"]):
        Company.objects.filter(pk=w["company"]).update(
            daily_stock_check=True, daily_stock_check_hour=0
        )
    call_command("run_scheduled")
    with use_tenant(w["tenant"]):
        [t] = StockTransfer.objects.filter(to_branch_id=w["depot"])
        assert t.reason == "Made by the daily Stock Check." and t.stock_check_run.daily
        notice = Notification.objects.filter(title__contains="Kolkata Depot").first()
        assert notice is not None and "Draft Stock Transfers made:\n• From" in notice.body
