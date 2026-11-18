"""Stock Summary and Stock Ledger: read from the stock ledger after a goods receipt."""

from datetime import timedelta

import pytest

from accounts.models import Role
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
    tea, box = sorted(body["items"], key=lambda i: i["item_name"])
    assert (tea["item_name"], tea["unit"], tea["qty"], tea["value"], tea["rate"]) == (
        "CTC Tea",
        "kg",
        "600.000000",
        "156000.00",
        "260.00",
    )
    [batch] = tea["batches"]
    assert (batch["number"], batch["qty"], batch["value"]) == (
        "DTT-26-118",
        "600.000000",
        "156000.00",
    )
    assert [(b["place"].split(" / ")[-1], b["qty"], b["value"]) for b in batch["bins"]] == [
        ("A-02", "300.000000", "78000.00"),
        ("A-06", "300.000000", "78000.00"),
    ]
    assert box["qty"] == "30.000000" and box["batches"][0]["number"] == ""


def test_summary_on_a_day_before_the_receipt_is_empty(store, grn, received):  # noqa: F811
    body = summary(store, grn, as_on=(TODAY - timedelta(days=1)).isoformat()).json()
    assert body["items"] == [] and body["total_value"] == "0"


def test_summary_filters_by_item(store, grn, received):  # noqa: F811
    body = summary(store, grn, item=grn["box"]).json()
    assert [i["item_name"] for i in body["items"]] == ["Tea Box"]


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
    assert summary(store, grn).json()["items"] == []


def test_stock_reports_need_the_right_to_see_stock(alpha, grn):  # noqa: F811
    with use_tenant(alpha):
        Role.objects.create(code="hr", name="HR", permissions=["masters.view"])
    hr = client_for(alpha, "hr@x.in", "hr")
    assert summary(hr, grn).status_code == 403
    assert ledger(hr, grn, item=grn["tea"]).status_code == 403


def test_the_stock_ledger_needs_an_item(store, grn):  # noqa: F811
    assert ledger(store, grn).status_code == 400
