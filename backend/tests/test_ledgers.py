"""Ledgers: accounts under the ledger groups that will take postings."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


@pytest.fixture
def as_user(alpha):
    def make(*role_codes: str, companies=()):
        with use_tenant(alpha):
            user = User.objects.create_user(f"{'-'.join(role_codes) or 'none'}@x.in")
            user.roles.set(Role.objects.filter(code__in=role_codes))
            user.companies.set(companies)
            client = Client()
            client.force_login(user)
        return client

    return make


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def groups(client, company):
    detail = call(client, "get", f"companies/{company}/").json()
    return {g["name"]: g for g in detail["ledger_groups"]}


def test_new_company_has_a_cash_ledger(as_user, company):
    accountant = as_user("accountant")
    ledgers = call(accountant, "get", f"companies/{company}/ledgers/").json()
    # Cash, and the six fixed system ledgers (test_posting.py).
    assert [(x["name"], x["group_name"], x["nature"]) for x in ledgers if not x["system"]] == [
        ("Cash", "Cash-in-Hand", "asset")
    ]
    assert len([x for x in ledgers if x["system"] == "fixed"]) == 6
    assert groups(accountant, company)["Cash-in-Hand"]["ledger_count"] == 1


def test_bank_ledger_keeps_bank_details(as_user, company):
    accountant = as_user("accountant")
    g = groups(accountant, company)
    assert g["Bank Accounts"]["is_bank"] and not g["Sundry Debtors"]["is_bank"]
    path = f"companies/{company}/ledgers/"
    bank = {
        "name": "HDFC Current A/c",
        "group": g["Bank Accounts"]["id"],
        "bank_name": "HDFC Bank",
        "account_number": " 50200012345678 ",
        "ifsc": "hdfc0001234",
    }
    response = call(accountant, "post", path, bank)
    assert response.status_code == 201, response.json()
    assert response.json()["ifsc"] == "HDFC0001234"
    assert response.json()["account_number"] == "50200012345678"

    assert "IFSC" in str(
        call(
            accountant,
            "post",
            path,
            {**bank, "name": "X", "account_number": "1", "ifsc": "HDFC1234"},
        ).json()
    )

    # Not a bank ledger: bank details are dropped.
    freight = {"name": "Freight Inward", "group": g["Direct Expenses"]["id"], "bank_name": "HDFC"}
    response = call(accountant, "post", path, freight)
    assert response.json()["bank_name"] == "" and response.json()["nature"] == "expense"

    found = call(accountant, "get", f"{path}?q=5020001").json()
    assert [x["name"] for x in found] == ["HDFC Current A/c"]


def test_names_are_unique_across_ledgers_and_groups(as_user, company):
    accountant = as_user("accountant")
    g = groups(accountant, company)
    path = f"companies/{company}/ledgers/"
    debtors = g["Sundry Debtors"]["id"]
    assert call(accountant, "post", path, {"name": "cash", "group": debtors}).status_code == 400
    response = call(accountant, "post", path, {"name": "Sundry Debtors", "group": debtors})
    assert "already has a group named" in str(response.json())
    group_path = f"companies/{company}/ledger-groups/"
    response = call(accountant, "post", group_path, {"name": "CASH", "parent": debtors})
    assert "already has a ledger named" in str(response.json())


def test_filter_by_group_includes_sub_groups(as_user, company):
    accountant = as_user("accountant")
    g = groups(accountant, company)
    export = call(
        accountant,
        "post",
        f"companies/{company}/ledger-groups/",
        {"name": "Export debtors", "parent": g["Sundry Debtors"]["id"]},
    ).json()
    path = f"companies/{company}/ledgers/"
    call(accountant, "post", path, {"name": "Acme GmbH", "group": export["id"]})
    call(accountant, "post", path, {"name": "Local Traders", "group": g["Sundry Debtors"]["id"]})
    names = [
        x["name"]
        for x in call(accountant, "get", f"{path}?group={g['Sundry Debtors']['id']}").json()
    ]
    assert names == ["Acme GmbH", "Local Traders"]

    # A group is never deleted, and one with active ledgers cannot be disabled.
    assert call(accountant, "delete", f"ledger-groups/{export['id']}/").status_code == 405
    response = call(accountant, "patch", f"ledger-groups/{export['id']}/", {"is_active": False})
    assert "ledgers" in str(response.json())


def test_edit_move_deactivate_never_delete(as_user, company):
    accountant = as_user("accountant")
    g = groups(accountant, company)
    path = f"companies/{company}/ledgers/"
    ledger = call(
        accountant, "post", path, {"name": "Rent", "group": g["Indirect Expenses"]["id"]}
    ).json()
    response = call(
        accountant,
        "patch",
        f"ledgers/{ledger['id']}/",
        {"name": "Factory rent", "group": g["Direct Expenses"]["id"], "is_active": False},
    )
    assert response.status_code == 200
    assert (
        response.json()["name"],
        response.json()["group_name"],
        response.json()["is_active"],
    ) == (
        "Factory rent",
        "Direct Expenses",
        False,
    )
    assert (
        call(accountant, "patch", f"ledgers/{ledger['id']}/", {"name": "Cash"}).status_code == 400
    )
    # Ledgers are never deleted, even by an Owner; deactivate them instead.
    owner = as_user("owner")
    assert call(owner, "delete", f"ledgers/{ledger['id']}/").status_code == 405


def test_who_may_see_and_change_ledgers(as_user, company, alpha):
    path = f"companies/{company}/ledgers/"
    viewer = as_user("viewer")
    assert call(viewer, "get", path).status_code == 200
    cash = call(viewer, "get", path).json()[0]["id"]
    assert call(viewer, "patch", f"ledgers/{cash}/", {"notes": "x"}).status_code == 403
    assert call(as_user(), "get", path).status_code == 403

    # Someone limited to another company cannot see or touch these ledgers.
    with use_tenant(alpha):
        other = create_company(name="Apurva Organics Ltd", state_code="19").pk
    limited = as_user("accountant", companies=[other])
    assert call(limited, "get", path).status_code == 404
    assert call(limited, "patch", f"ledgers/{cash}/", {"notes": "x"}).status_code == 404


def test_group_from_another_company_is_refused(as_user, company, alpha):
    with use_tenant(alpha):
        other = create_company(name="Apurva Organics Ltd", state_code="19").pk
    owner = as_user("owner")
    other_group = groups(owner, other)["Sundry Debtors"]["id"]
    response = call(
        owner, "post", f"companies/{company}/ledgers/", {"name": "X", "group": other_group}
    )
    assert response.status_code == 400


def test_the_ledgers_list_comes_a_page_at_a_time(as_user, company, alpha):
    """Preview 13 (Sidharth 2026-11-25): 25 ledgers per group a page, counts and
    opening totals per group, column search on the server, disabled ones hidden
    unless asked for and then last."""
    from core.models import Ledger, LedgerGroup

    with use_tenant(alpha):
        expenses = LedgerGroup.objects.get(company_id=company, name="Indirect Expenses")
        Ledger.objects.bulk_create(
            Ledger(
                company_id=company,
                group=expenses,
                name=f"Expense {n:02d}",
                opening_amount=10,
                opening_side="dr" if n % 2 else "cr",
            )
            for n in range(1, 31)
        )
        Ledger.objects.filter(name="Expense 01").update(is_active=False)
    accountant = as_user("accountant")
    path = f"companies/{company}/ledgers/?paged=1"
    g = call(accountant, "get", path).json()["groups"][str(expenses.pk)]
    assert (g["count"], g["pages"], g["page"], len(g["results"])) == (29, 2, 1, 25)
    assert g["net"] == "-10.00"  # 14 Dr and 15 Cr of 10 each
    assert g["results"][0]["name"] == "Expense 02"

    second = call(accountant, "get", f"{path}&pages={expenses.pk}:2").json()
    assert [x["name"] for x in second["groups"][str(expenses.pk)]["results"]] == [
        f"Expense {n}" for n in range(27, 31)
    ]
    with_off = call(accountant, "get", f"{path}&inactive=1&pages={expenses.pk}:9").json()
    last = with_off["groups"][str(expenses.pk)]
    assert last["page"] == 2 and last["results"][-1]["name"] == "Expense 01"

    found = call(accountant, "get", f"{path}&name=expense%201").json()
    assert found["count"] == 11  # Expense 10 to 19 and 21 (01 is disabled)


@pytest.fixture
def many(alpha, company):
    """Sixty expense ledgers, a disabled one, a customer and a supplier."""
    from core.models import Ledger, LedgerGroup, Party

    with use_tenant(alpha):
        expenses = LedgerGroup.objects.get(company_id=company, name="Indirect Expenses")
        Ledger.objects.bulk_create(
            Ledger(company_id=company, group=expenses, name=f"Expense {n:02d}")
            for n in range(1, 61)
        )
        Ledger.objects.filter(name="Expense 01").update(is_active=False)
        for side, code in (("customer", "sundry_debtors"), ("supplier", "sundry_creditors")):
            party = Party.objects.create(name=f"A {side}", state_code="27")
            group = LedgerGroup.objects.get(company_id=company, code=code)
            Ledger.objects.create(
                company_id=company, group=group, name=party.name, party=party, party_side=side
            )


def test_dashboard_counts_ledgers_without_reading_them(as_user, company, many):
    accountant = as_user("accountant")
    every = call(accountant, "get", f"companies/{company}/ledgers/").json()
    counts = call(accountant, "get", f"companies/{company}/ledgers/?counts=1").json()
    assert counts == {"total": len(every), "customers": 1, "suppliers": 1}


def test_a_ledger_picker_reads_lean_rows_and_searches_on_the_server(as_user, company, many):
    accountant = as_user("accountant")
    path = f"companies/{company}/ledgers/?lean=1"
    expense = call(accountant, "get", f"{path}&nature=expense&party=0").json()
    assert len(expense) == 60 and set(expense[0]) == {
        "id",
        "name",
        "is_active",
        "group_name",
        "nature",
        "party",
    }
    assert {x["nature"] for x in expense} == {"expense"}

    first = call(accountant, "get", f"{path}&search=1&q=&ids=").json()
    assert len(first) == 50 and first[0]["name"] != "Expense 01"  # disabled go last
    picked = expense[0]["id"]  # Expense 01, disabled: still sent while it is the pick
    found = call(accountant, "get", f"{path}&search=1&q=expense%2042&ids={picked}").json()
    assert [x["name"] for x in found] == ["Expense 01", "Expense 42"]
    only = call(accountant, "get", f"{path}&search=1&ids={picked}").json()
    assert [x["name"] for x in only] == ["Expense 01"]
    party = call(accountant, "get", f"{path}&search=1&q=customer").json()
    assert [x["name"] for x in party] == ["A customer"] and party[0]["party"]
