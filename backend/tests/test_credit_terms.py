"""Credit terms: the company's list of how bills are paid (decision 0019)."""

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
        user = User.objects.create_user("accounts@x.in", full_name="Asha")
        user.roles.set(Role.objects.filter(code="accountant"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def terms(client, company):
    return {t["name"]: t for t in call(client, "get", f"companies/{company}/credit-terms/").json()}


def test_a_new_company_starts_with_the_usual_terms(accountant, company):
    have = terms(accountant, company)
    assert {"Full advance", "50% advance, 50% on delivery", "30 days"} <= set(have)
    assert have["50% advance, 50% on delivery"]["summary"] == (
        "50% advance with the order, 50% on delivery"
    )
    assert have["30 days"]["summary"] == "100% 30 days after the bill"


def test_add_and_change_a_term(accountant, company):
    url = f"companies/{company}/credit-terms/"
    data = {
        "name": "30% advance, 70% in 15 days",
        "parts": [
            {"percent": "30", "event": "order"},
            {"percent": "70", "event": "bill", "days": 15},
        ],
    }
    created = call(accountant, "post", url, data)
    assert created.status_code == 201, created.json()
    term = created.json()
    assert term["summary"] == "30% advance with the order, 70% 15 days after the bill"

    changed = call(accountant, "patch", f"credit-terms/{term['id']}/", {"is_active": False})
    assert changed.status_code == 200
    assert changed.json()["is_active"] is False
    assert len(changed.json()["parts"]) == 2  # parts not sent: kept

    entries = call(
        accountant, "get", f"audit/?company={company}&type=credit_term&id={term['id']}"
    ).json()["entries"]
    assert [e["action"] for e in entries] == ["update", "create"]
    added = {c["label"]: c["new"] for c in entries[1]["changes"]}
    assert added["Parts"] == "30% advance with the order; 70% 15 days after the bill"


def test_term_checks(accountant, company):
    url = f"companies/{company}/credit-terms/"

    def error(**data):
        response = call(accountant, "post", url, {"name": "X", "parts": [], **data})
        assert response.status_code == 400
        return str(response.json())

    assert "at least one part" in error()
    assert "add up to 90%" in error(parts=[{"percent": "90", "event": "bill", "days": 30}])
    assert "already" in error(name="30 DAYS", parts=[{"percent": "100", "event": "bill"}])


def test_a_party_takes_terms_of_its_own_company(accountant, company, alpha):
    with use_tenant(alpha):
        other = create_company(name="Apurva Organics Ltd", state_code="27").pk
    detail = call(accountant, "get", f"companies/{company}/").json()
    debtors = next(g["id"] for g in detail["ledger_groups"] if g["name"] == "Sundry Debtors")
    data = {
        "name": "Fresh Mart",
        "group": debtors,
        "party": {"credit_term": terms(accountant, other)["30 days"]["id"]},
    }
    response = call(accountant, "post", f"companies/{company}/ledgers/", data)
    assert "this company" in str(response.json())
    data["party"]["credit_term"] = terms(accountant, company)["30 days"]["id"]
    response = call(accountant, "post", f"companies/{company}/ledgers/", data)
    assert response.status_code == 201
    assert response.json()["party"]["credit_term_name"] == "30 days"
    assert terms(accountant, company)["30 days"]["party_count"] == 1
