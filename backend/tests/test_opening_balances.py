"""Opening balances on the ledger, with open bills for bill-wise ledgers."""

from datetime import date

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from core.models import fiscal_year_start
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


@pytest.fixture
def accountant(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("accounts@x.in")
        user.roles.set(Role.objects.filter(code="accountant"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(
            name="Apurvam Organics LLP", state_code="27", books_start=date(2026, 4, 1)
        ).pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def group_id(client, company, name):
    detail = call(client, "get", f"companies/{company}/").json()
    return next(g["id"] for g in detail["ledger_groups"] if g["name"] == name)


def bill(ref, amount, side="dr", bill_date="2026-03-10", due_date=None):
    return {
        "ref": ref,
        "bill_date": bill_date,
        "due_date": due_date,
        "amount": amount,
        "side": side,
    }


def test_books_begin_at_the_start_of_the_financial_year():
    assert fiscal_year_start(date(2026, 11, 5), 4) == date(2026, 4, 1)
    assert fiscal_year_start(date(2027, 2, 1), 4) == date(2026, 4, 1)
    assert fiscal_year_start(date(2026, 11, 5), 1) == date(2026, 1, 1)


def test_plain_ledger_opening_balance_and_company_totals(accountant, company):
    path = f"companies/{company}/ledgers/"
    capital = {
        "name": "Partners Capital",
        "group": group_id(accountant, company, "Capital Account"),
        "opening_amount": "500000.00",
        "opening_side": "cr",
    }
    response = call(accountant, "post", path, capital)
    assert response.status_code == 201, response.json()
    assert response.json()["bill_wise"] is False
    bank = {
        "name": "HDFC",
        "group": group_id(accountant, company, "Bank Accounts"),
        "opening_amount": "420000.50",
        "opening_side": "dr",
    }
    call(accountant, "post", path, bank)
    opening = call(accountant, "get", f"companies/{company}/").json()["opening"]
    assert opening == {"dr": "420000.50", "cr": "500000.00", "difference": "-79999.50"}

    negative = {**bank, "name": "X", "opening_amount": "-5"}
    assert call(accountant, "post", path, negative).status_code == 400


def test_debtor_is_bill_wise_and_bills_must_add_up(accountant, company):
    path = f"companies/{company}/ledgers/"
    debtors = group_id(accountant, company, "Sundry Debtors")
    customer = {
        "name": "Fresh Mart",
        "group": debtors,
        "opening_amount": "15000.00",
        "opening_side": "dr",
        "opening_bills": [bill("AOL/SI/25-26/0101", "12000.00"), bill("AOL/SI/25-26/0102", "5000")],
    }
    response = call(accountant, "post", path, customer)
    assert "add up to 17,000.00 Dr" in str(response.json())

    customer["opening_bills"].append(bill("Advance", "2000", side="cr", bill_date="2026-03-20"))
    response = call(accountant, "post", path, customer)
    assert response.status_code == 201, response.json()
    created = response.json()
    assert created["bill_wise"] is True
    assert [b["ref"] for b in created["opening_bills"]] == [
        "AOL/SI/25-26/0101",
        "AOL/SI/25-26/0102",
        "Advance",
    ]

    # Changing the balance alone breaks the match; changing both is fine.
    url = f"ledgers/{created['id']}/"
    assert call(accountant, "patch", url, {"opening_amount": "16000"}).status_code == 400
    response = call(
        accountant,
        "patch",
        url,
        {"opening_amount": "16000", "opening_bills": [bill("B1", "16000")]},
    )
    assert response.status_code == 200
    assert [b["ref"] for b in response.json()["opening_bills"]] == ["B1"]


def test_opening_bill_checks(accountant, company):
    path = f"companies/{company}/ledgers/"
    supplier = {
        "name": "Seed Co",
        "group": group_id(accountant, company, "Sundry Creditors"),
        "opening_amount": "100",
        "opening_side": "cr",
    }
    after = {**supplier, "opening_bills": [bill("P1", "100", "cr", bill_date="2026-04-01")]}
    assert "before 01 Apr 2026" in str(call(accountant, "post", path, after).json())
    twice = {**supplier, "opening_bills": [bill("p1", "50", "cr"), bill("P1", "50", "cr")]}
    assert "only once" in str(call(accountant, "post", path, twice).json())
    early_due = {**supplier, "opening_bills": [bill("P1", "100", "cr", due_date="2026-03-01")]}
    assert "due before" in str(call(accountant, "post", path, early_due).json())


def test_turning_bill_wise_off_drops_the_bills(accountant, company):
    path = f"companies/{company}/ledgers/"
    customer = {
        "name": "Fresh Mart",
        "group": group_id(accountant, company, "Sundry Debtors"),
        "opening_amount": "100",
        "opening_side": "dr",
        "opening_bills": [bill("B1", "100")],
    }
    created = call(accountant, "post", path, customer).json()
    response = call(accountant, "patch", f"ledgers/{created['id']}/", {"bill_wise": False})
    assert response.json()["opening_bills"] == []
    assert response.json()["opening_amount"] == "100.00"


def test_books_start_cannot_move_before_an_opening_bill(accountant, company):
    customer = {
        "name": "Fresh Mart",
        "group": group_id(accountant, company, "Sundry Debtors"),
        "opening_amount": "100",
        "opening_side": "dr",
        "opening_bills": [bill("B1", "100", bill_date="2026-03-10")],
    }
    call(accountant, "post", f"companies/{company}/ledgers/", customer)
    response = call(accountant, "patch", f"companies/{company}/", {"books_start": "2026-03-01"})
    assert "opening bills" in str(response.json())
    response = call(accountant, "patch", f"companies/{company}/", {"books_start": "2026-03-11"})
    assert response.status_code == 200
