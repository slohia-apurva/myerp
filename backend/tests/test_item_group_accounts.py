"""Accounting defaults on the main item group: one row per company, inherited below."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core import locks
from core.companies import create_company
from core.models import ItemGroup, Ledger, LedgerGroup
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HOST = "alpha.localhost"


@pytest.fixture
def accountant(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("accounts@x.in", full_name="Asha")
        user.roles.set(Role.objects.filter(code="accountant"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def books(alpha):
    """A company with a stock ledger, a COGS ledger and an expense ledger."""
    with use_tenant(alpha):
        company = create_company(name="Apurvam Organics LLP", state_code="27")
        other = create_company(name="Other Foods LLP", state_code="27")

        def ledger(co, name, code):
            group = LedgerGroup.objects.filter(company=co, code=code).first()
            return Ledger.objects.create(company=co, group=group, name=name)

        stock_group = LedgerGroup.objects.get(company=company, code="stock_in_hand")
        expense_group = LedgerGroup.objects.filter(company=company, nature="expense").first()
        return {
            "company": company.pk,
            "other": other.pk,
            "stock": Ledger.objects.create(company=company, group=stock_group, name="Raw Stock").pk,
            "cogs": Ledger.objects.create(company=company, group=expense_group, name="Raw COGS").pk,
            "other_stock": ledger(other, "Other Stock", "stock_in_hand").pk,
            "cash": Ledger.objects.get(company=company, name="Cash").pk,
        }


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def row(books, **extra):
    base = {
        "company": books["company"],
        "stock_ledger": books["stock"],
        "cogs_ledger": books["cogs"],
    }
    return {**base, **extra}


def test_main_group_keeps_accounts_and_sub_group_inherits(accountant, books):
    main = call(
        accountant, "post", "item-groups/", {"name": "Raw material", "accounts_in": [row(books)]}
    )
    assert main.status_code == 201, main.json()
    assert main.json()["accounts"][0]["stock_ledger_name"] == "Raw Stock"
    sub = call(accountant, "post", "item-groups/", {"name": "Spices", "parent": main.json()["id"]})
    body = sub.json()
    assert body["accounts"][0]["cogs_ledger_name"] == "Raw COGS"
    assert body["accounts_from"]["name"] == "Raw material"


def test_sub_group_cannot_hold_its_own_accounts(accountant, books):
    main = call(accountant, "post", "item-groups/", {"name": "Raw material"}).json()
    sub = call(
        accountant,
        "post",
        "item-groups/",
        {"name": "Spices", "parent": main["id"], "accounts_in": [row(books)]},
    )
    assert sub.status_code == 400
    assert "main group" in str(sub.json())


def test_ledgers_must_fit_their_account(accountant, books):
    def post(name, **extra):
        return call(
            accountant, "post", "item-groups/", {"name": name, "accounts_in": [row(books, **extra)]}
        )

    assert "Stock-in-Hand" in str(post("A", stock_ledger=books["cash"]).json())
    assert "expense ledger" in str(post("B", cogs_ledger=books["stock"]).json())
    assert "not a ledger of" in str(post("C", stock_ledger=books["other_stock"]).json())


def test_a_company_listed_twice_is_refused(accountant, books):
    res = call(
        accountant, "post", "item-groups/", {"name": "A", "accounts_in": [row(books), row(books)]}
    )
    assert res.status_code == 400
    assert "listed twice" in str(res.json())


def test_locked_row_cannot_change_but_other_company_can_be_added(accountant, books, monkeypatch):
    main = call(
        accountant, "post", "item-groups/", {"name": "Raw material", "accounts_in": [row(books)]}
    ).json()
    monkeypatch.setattr(
        locks,
        "_ACCOUNT_USES",
        [lambda g, c: "36 stock entries" if c.pk == books["company"] else ""],
    )
    got = call(accountant, "get", "item-groups/").json()
    assert got[0]["accounts"][0]["locked"] == ["36 stock entries"]
    changed = call(
        accountant,
        "patch",
        f"item-groups/{main['id']}/",
        {"accounts_in": [row(books, cogs_ledger=None)]},
    )
    assert changed.status_code == 400
    assert "in use" in str(changed.json())
    removed = call(accountant, "patch", f"item-groups/{main['id']}/", {"accounts_in": []})
    assert removed.status_code == 400
    same = call(accountant, "patch", f"item-groups/{main['id']}/", {"accounts_in": [row(books)]})
    assert same.status_code == 200


def test_accounts_can_change_while_unused(accountant, books, alpha):
    main = call(
        accountant, "post", "item-groups/", {"name": "Raw material", "accounts_in": [row(books)]}
    ).json()
    res = call(
        accountant,
        "patch",
        f"item-groups/{main['id']}/",
        {"accounts_in": [row(books, cogs_ledger=None)]},
    )
    assert res.status_code == 200
    assert res.json()["accounts"][0]["cogs_ledger"] is None
    with use_tenant(alpha):
        assert ItemGroup.objects.get(pk=main["id"]).accounts.count() == 1


def test_sales_ledger_is_an_income_ledger_and_can_be_added_once_in_use(
    accountant, books, monkeypatch, alpha
):
    with use_tenant(alpha):
        income = LedgerGroup.objects.get(company_id=books["company"], code="sales_accounts")
        sales = Ledger.objects.create(company_id=books["company"], group=income, name="Sales Tea")
    bad = call(
        accountant,
        "post",
        "item-groups/",
        {"name": "A", "accounts_in": [row(books, sales_ledger=books["cogs"])]},
    )
    assert "income ledger" in str(bad.json())
    main = call(
        accountant, "post", "item-groups/", {"name": "Tea", "accounts_in": [row(books)]}
    ).json()
    monkeypatch.setattr(locks, "_ACCOUNT_USES", [lambda g, c: "3 stock entries"])
    # A Sales Ledger still blank may be set on a row in use (preview 14a) ...
    added = call(
        accountant,
        "patch",
        f"item-groups/{main['id']}/",
        {"accounts_in": [row(books, sales_ledger=sales.pk)]},
    )
    assert added.status_code == 200, added.json()
    assert added.json()["accounts"][0]["sales_ledger_name"] == "Sales Tea"
    # ... but once set, it is locked like the others.
    cleared = call(accountant, "patch", f"item-groups/{main['id']}/", {"accounts_in": [row(books)]})
    assert cleared.status_code == 400
