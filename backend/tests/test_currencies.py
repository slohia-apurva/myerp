"""Foreign currency ledgers and their opening balances."""

from datetime import date

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
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
            name="Apurva Organics Ltd", state_code="19", books_start=date(2026, 4, 1)
        ).pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def group_id(client, company, name):
    detail = call(client, "get", f"companies/{company}/").json()
    return next(g["id"] for g in detail["ledger_groups"] if g["name"] == name)


def test_currency_list(accountant):
    codes = [c["code"] for c in call(accountant, "get", "currencies/").json()]
    assert {"INR", "USD", "EUR", "GBP", "AED"} <= set(codes)


def test_foreign_ledgers_need_the_company_switch(accountant, company):
    path = f"companies/{company}/ledgers/"
    bank = {"name": "HDFC EEFC USD", "group": group_id(accountant, company, "Bank Accounts")}
    response = call(accountant, "post", path, {**bank, "currency": "USD"})
    assert "Turn on multiple currencies" in str(response.json())
    # INR is the base currency, so it is stored as "no foreign currency".
    response = call(accountant, "post", path, {**bank, "currency": "INR"})
    assert response.status_code == 201 and response.json()["currency"] is None

    assert call(accountant, "patch", f"companies/{company}/", {"multi_currency": True}).json()[
        "multi_currency"
    ]
    response = call(
        accountant,
        "post",
        path,
        {
            **bank,
            "name": "HDFC EEFC",
            "currency": "USD",
            "opening_fc_amount": "1000.00",
            "opening_rate": "83.456789",
            "opening_side": "dr",
        },
    )
    assert response.status_code == 201, response.json()
    assert response.json()["opening_amount"] == "83456.79"
    assert response.json()["currency"] == "USD"

    missing_rate = {**bank, "name": "X", "currency": "USD", "opening_fc_amount": "10"}
    assert "exchange rate" in str(call(accountant, "post", path, missing_rate).json())

    # The switch cannot go off while foreign ledgers exist.
    response = call(accountant, "patch", f"companies/{company}/", {"multi_currency": False})
    assert response.status_code == 400


def test_export_debtor_bills_in_usd(accountant, company):
    call(accountant, "patch", f"companies/{company}/", {"multi_currency": True})
    customer = {
        "name": "Acme GmbH",
        "group": group_id(accountant, company, "Sundry Debtors"),
        "currency": "EUR",
        "opening_bills": [
            {
                "ref": "E/101",
                "bill_date": "2026-02-10",
                "side": "dr",
                "fc_amount": "5000",
                "rate": "90.10",
            },
            {
                "ref": "E/102",
                "bill_date": "2026-03-15",
                "side": "dr",
                "fc_amount": "2000",
                "rate": "91.25",
            },
            {
                "ref": "Adv",
                "bill_date": "2026-03-20",
                "side": "cr",
                "fc_amount": "500",
                "rate": "91.00",
            },
        ],
    }
    response = call(accountant, "post", f"companies/{company}/ledgers/", customer)
    assert response.status_code == 201, response.json()
    ledger = response.json()
    assert ledger["bill_wise"] is True
    assert [b["amount"] for b in ledger["opening_bills"]] == ["450500.00", "182500.00", "45500.00"]
    # 450500 + 182500 - 45500
    assert (ledger["opening_amount"], ledger["opening_side"]) == ("587500.00", "dr")
    assert ledger["opening_fc_amount"] == "6500.00"

    no_rate = {
        **customer,
        "name": "B",
        "opening_bills": [{**customer["opening_bills"][0], "rate": None}],
    }
    assert "exchange rate" in str(
        call(accountant, "post", f"companies/{company}/ledgers/", no_rate).json()
    )

    totals = call(accountant, "get", f"companies/{company}/").json()["opening"]
    assert totals["dr"] == "587500.00"
