"""Trial Balance and Ledger Statement: read from the general ledger after a goods receipt."""

from datetime import timedelta

import pytest

from core.models import Ledger
from posting import accounts
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
    owner,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def report(client, g, name, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return call(client, "get", f"companies/{g['company']}/{name}/?{query}")


@pytest.fixture
def received(store, grn):  # noqa: F811
    made = call(store, "post", url(grn), receipt(grn, [tea_line(grn), box_line(grn)], submit=True))
    assert made.status_code == 201, made.json()
    return made.json()


@pytest.fixture
def grni(alpha, grn):  # noqa: F811
    with use_tenant(alpha):
        company = Ledger.objects.get(pk=grn["stock"]).company
        return accounts.system_ledger(company, accounts.GRNI)


def test_trial_balance_shows_the_receipt_under_its_groups(owner, grn, grni, received):  # noqa: F811
    res = report(owner, grn, "trial-balance")
    assert res.status_code == 200, res.json()
    body = res.json()
    ledgers = {r["id"]: r for r in body["rows"] if r["kind"] == "ledger"}
    stock = ledgers[grn["stock"]]
    assert (stock["debit"], stock["credit"], stock["closing"]) == ("156900.00", "0", "156900.00")
    owed = ledgers[grni.pk]
    assert (owed["credit"], owed["closing"]) == ("156900.00", "-156900.00")
    # Each ledger sits under its group, which carries the totals of what is under it.
    groups = {r["id"]: r for r in body["rows"] if r["kind"] == "group"}
    assert groups[stock["parent"]]["debit"] == "156900.00"
    assert groups[stock["parent"]]["depth"] == stock["depth"] - 1
    assert body["total"]["debit"] == body["total"]["credit"] == "156900.00"


def test_entries_before_the_period_come_in_as_opening(owner, grn, received):  # noqa: F811
    later = (TODAY + timedelta(days=1)).isoformat()
    body = report(owner, grn, "trial-balance", **{"from": later, "to": later}).json()
    stock = next(r for r in body["rows"] if r["kind"] == "ledger" and r["id"] == grn["stock"])
    assert (stock["opening"], stock["debit"], stock["closing"]) == ("156900.00", "0", "156900.00")


def test_ledger_statement_lists_entries_with_the_other_side(owner, grn, grni, received):  # noqa: F811
    res = report(owner, grn, "ledger-statement", ledger=grn["stock"])
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["opening"] == "0.00" or body["opening"] == "0"
    [row] = body["rows"]
    assert row["entry"]["number"] == received["number"]
    assert row["entry"]["page"] == "goods-receipts"
    assert row["particulars"] == grni.name
    assert (row["debit"], row["balance"]) == ("156900.00", "156900.00")
    assert body["closing"] == "156900.00"
    other = report(owner, grn, "ledger-statement", ledger=grni.pk).json()
    assert other["rows"][0]["particulars"] == "Stock"
    assert other["closing"] == "-156900.00"


def test_a_cancelled_receipt_nets_to_nothing(owner, grn, received):  # noqa: F811
    res = call(owner, "post", f"goods-receipts/{received['id']}/cancel/", {"reason": "Wrong"})
    assert res.status_code == 200, res.json()
    body = report(owner, grn, "ledger-statement", ledger=grn["stock"]).json()
    assert [r["cancel"] for r in body["rows"]] == [False, True]
    assert body["closing"] == "0.00"


def test_books_need_the_right_to_see_accounts(store, grn):  # noqa: F811
    assert report(store, grn, "trial-balance").status_code == 403
    assert report(store, grn, "ledger-statement", ledger=grn["stock"]).status_code == 403


def test_the_statement_needs_a_ledger_of_the_company(owner, grn):  # noqa: F811
    assert report(owner, grn, "ledger-statement").status_code == 400
    assert report(owner, grn, "ledger-statement", ledger=999999).status_code == 404
