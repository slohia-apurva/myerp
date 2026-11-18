"""Stock Summary and Stock Ledger: read from the stock ledger after a goods receipt."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from accounts.models import Role
from posting.reports import short_bin, short_branch
from tenancy.context import use_tenant
from tests.test_goods_receipts import (  # noqa: F401  (fixtures)
    box_line,
    grn,
    receipt,
    store,
    tea_line,
    url,
)
from tests.test_purchase_orders import (  # noqa: F401  (fixtures)
    TODAY,
    buyer,
    call,
    client_for,
    owner,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def summary(client, g, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return call(client, "get", f"companies/{g['company']}/stock-summary/?{query}")


def ledger(client, g, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return call(client, "get", f"companies/{g['company']}/stock-ledger/?{query}")


@pytest.fixture
def received(store, grn):  # noqa: F811
    made = call(store, "post", url(grn), receipt(grn, [tea_line(grn), box_line(grn)], submit=True))
    assert made.status_code == 201, made.json()
    return made.json()


def test_summary_shows_items_batches_and_bins_with_values(store, grn, received):  # noqa: F811
    res = summary(store, grn)
    assert res.status_code == 200, res.json()
    body = res.json()
    # Tea 600 x 250 + 6,000 freight; box 30 x 20 + 300 freight (see the goods receipt test).
    assert body["total_value"] == "156900.00"
    got = [(r["item_name"], r["batch"], r["bin"], r["unit"], r["qty"], r["rate"], r["value"])
           for r in body["lines"]]  # fmt: skip
    assert got == [
        ("CTC Tea", "DTT-26-118", "F01 / A-02", "kg", "300.000000", "260.00", "78000.00"),
        ("CTC Tea", "DTT-26-118", "F01 / A-06", "kg", "300.000000", "260.00", "78000.00"),
        ("Tea Box", "", "Store", "pkt", "30.000000", "30.00", "900.00"),
    ]
    assert all(r["warehouse"] for r in body["lines"])


def test_names_do_not_repeat_the_company_or_branch():
    company = SimpleNamespace(name="Apurvam Organics LLP")
    branch = SimpleNamespace(name="Apurvam Organics LLP (Sankrail-2)", company=company)
    assert short_branch(branch) == "Sankrail-2"

    class Place(SimpleNamespace):
        def __str__(self):
            return self.name

    assert (
        short_bin(Place(name="Apurvam Organics LLP (Sankrail-2) Store", branch=branch)) == "Store"
    )
    assert short_bin(Place(name="F01 / A-02", branch=branch)) == "F01 / A-02"
    other = SimpleNamespace(name="Head Office", company=company)
    assert short_branch(other) == "Head Office"


def test_summary_on_a_day_before_the_receipt_is_empty(store, grn, received):  # noqa: F811
    body = summary(store, grn, as_on=(TODAY - timedelta(days=1)).isoformat()).json()
    assert body["lines"] == [] and body["total_value"] == "0"


def test_summary_filters_by_item(store, grn, received):  # noqa: F811
    body = summary(store, grn, item=grn["box"]).json()
    assert [r["item_name"] for r in body["lines"]] == ["Tea Box"]


def test_stock_ledger_lists_each_move_with_a_running_balance(store, grn, received):  # noqa: F811
    res = ledger(store, grn, item=grn["tea"])
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["opening_qty"] == "0" and body["unit"] == "kg"
    rows = body["rows"]
    assert [(r["qty_in"], r["balance_qty"], r["balance_value"]) for r in rows] == [
        ("300.000000", "300.000000", "78000.00"),
        ("300.000000", "600.000000", "156000.00"),
    ]
    first = rows[0]["entry"]
    assert first["page"] == "goods-receipts" and first["id"] == received["id"]
    assert first["number"] == received["number"]
    assert body["closing_value"] == "156000.00"
    assert [b["number"] for b in body["batches"]] == ["DTT-26-118"]
    # One bin only.
    one = ledger(store, grn, item=grn["tea"], location=grn["bin2"]).json()
    assert [r["balance_qty"] for r in one["rows"]] == ["300.000000"]


def test_stock_ledger_after_the_period_starts_from_the_opening(store, grn, received):  # noqa: F811
    later = (TODAY + timedelta(days=1)).isoformat()
    body = ledger(store, grn, item=grn["tea"], **{"from": later, "to": later}).json()
    assert body["rows"] == []
    assert (body["opening_qty"], body["opening_value"]) == ("600.000000", "156000.00")


def test_a_cancelled_receipt_shows_its_reversal_and_leaves_nothing(owner, store, grn, received):  # noqa: F811
    res = call(owner, "post", f"goods-receipts/{received['id']}/cancel/", {"reason": "Wrong"})
    assert res.status_code == 200, res.json()
    body = ledger(store, grn, item=grn["tea"]).json()
    assert [r["cancel"] for r in body["rows"]] == [False, False, True, True]
    assert body["closing_qty"] == "0.000000" and body["closing_value"] == "0.00"
    assert summary(store, grn).json()["lines"] == []


def test_stock_reports_need_the_right_to_see_stock(alpha, grn):  # noqa: F811
    with use_tenant(alpha):
        Role.objects.create(code="hr", name="HR", permissions=["masters.view"])
    hr = client_for(alpha, "hr@x.in", "hr")
    assert summary(hr, grn).status_code == 403
    assert ledger(hr, grn, item=grn["tea"]).status_code == 403


def test_the_stock_ledger_needs_an_item(store, grn):  # noqa: F811
    assert ledger(store, grn).status_code == 400


def test_items_show_their_stock_in_the_company(store, grn, received):  # noqa: F811
    path = f"companies/{grn['company']}/item-stock/"
    every = call(store, "get", path).json()["items"]
    assert every[str(grn["tea"])] == "600.000000"
    one = call(store, "get", f"{path}?item={grn['tea']}").json()
    assert (one["qty"], one["value"], one["unit"]) == ("600.000000", "156000.00", "kg")
    assert [b["qty"] for b in one["branches"]] == ["600.000000"]
    assert [(b["number"], b["qty"]) for b in one["batches"]] == [("DTT-26-118", "600.000000")]
    last = one["last_received"]
    assert last["number"] == received["number"] and last["page"] == "goods-receipts"
