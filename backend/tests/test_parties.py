"""Customers and suppliers: party details on debtor and creditor ledgers."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from core.india import gstin_check_char
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def gstin(state: str, pan: str = "AAPFU0939F", entity: str = "1") -> str:
    first14 = f"{state}{pan}{entity}Z"
    return first14 + gstin_check_char(first14)


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


def group_id(client, company, name):
    detail = call(client, "get", f"companies/{company}/").json()
    return next(g["id"] for g in detail["ledger_groups"] if g["name"] == name)


def term_id(client, company, name):
    terms = call(client, "get", "credit-terms/").json()
    return next(t["id"] for t in terms if t["name"] == name)


def add_ledger(client, company, group, **extra):
    data = {"name": "Fresh Mart", "group": group_id(client, company, group), **extra}
    return call(client, "post", f"companies/{company}/ledgers/", data)


def test_a_customer_gets_party_details(accountant, company, alpha):
    with use_tenant(alpha):
        salesman = User.objects.create_user("ravi@x.in", full_name="Ravi").pk
    party = {
        "gst_type": "regular",
        "gstin": gstin("29").lower(),
        "contacts": [
            {"name": "Mr Rao", "designation": "Owner", "phone": "9876543210", "is_primary": True},
            {"name": "Meena", "designation": "Accounts", "email": "accounts@freshmart.in"},
        ],
        "credit_limit": "500000",
        "credit_term": term_id(accountant, company, "30 days"),
        "salesman": salesman,
        "addresses": [
            {
                "label": "Bengaluru office",
                "address": "12 MG Road",
                "pincode": "560001",
                "state_code": "29",
                "is_billing": True,
            },
            {
                "label": "Pune godown",
                "address": "Hadapsar",
                "state_code": "27",
                "gstin": gstin("27"),
                "is_shipping": True,
            },
        ],
    }
    response = add_ledger(accountant, company, "Sundry Debtors", party=party)
    assert response.status_code == 201, response.json()
    saved = response.json()["party"]
    # The PAN and state come from the GSTIN.
    assert saved["pan"] == "AAPFU0939F"
    assert saved["state_code"] == "29"
    assert saved["salesman_name"] == "Ravi"
    assert [a["label"] for a in saved["addresses"]] == ["Bengaluru office", "Pune godown"]
    assert [(c["name"], c["is_primary"]) for c in saved["contacts"]] == [
        ("Mr Rao", True),
        ("Meena", False),
    ]

    # Not sending party leaves it as it is.
    url = f"ledgers/{response.json()['id']}/"
    again = call(accountant, "patch", url, {"notes": "Key account"}).json()
    assert again["party"]["credit_term_name"] == "30 days"
    assert len(again["party"]["contacts"]) == 2


def test_party_checks(accountant, company):
    def error(**party):
        response = add_ledger(accountant, company, "Sundry Creditors", party=party)
        assert response.status_code == 400
        return str(response.json())

    assert "needs its GSTIN" in error(gst_type="regular")
    assert "different state" in error(gst_type="regular", gstin=gstin("29"), state_code="27")
    assert "must match" in error(gst_type="regular", gstin=gstin("29"), pan="ABCPE1234F")
    assert "registered GST type" in error(gst_type="unregistered", gstin=gstin("27"))
    assert "country" in error(gst_type="overseas")
    assert "Overseas" in error(gst_type="unregistered", country="Germany")
    two_billing = [
        {"label": "A", "address": "x", "state_code": "27", "is_billing": True},
        {"label": "B", "address": "y", "state_code": "27", "is_billing": True},
    ]
    assert "only one default billing" in error(state_code="27", addresses=two_billing)
    two_main = [{"name": "A", "is_primary": True}, {"name": "B", "is_primary": True}]
    assert "only one main contact" in error(state_code="27", contacts=two_main)
    bad_email = [{"name": "A", "email": "not-an-email"}]
    assert "email" in error(state_code="27", contacts=bad_email)
    other_pan = [{"label": "A", "address": "x", "gstin": gstin("29", pan="ABCPE1234F")}]
    assert "another PAN" in error(gst_type="regular", gstin=gstin("27"), addresses=other_pan)


def test_overseas_supplier(accountant, company):
    party = {"gst_type": "overseas", "country": "Germany", "state_code": "27"}
    response = add_ledger(accountant, company, "Sundry Creditors", party=party)
    assert response.status_code == 201, response.json()
    assert response.json()["party"]["state_code"] == ""
    assert response.json()["party"]["country"] == "Germany"


def test_a_party_without_details_starts_unregistered_in_the_company_state(accountant, company):
    response = add_ledger(accountant, company, "Sundry Debtors")
    assert response.status_code == 201
    party = response.json()["party"]
    assert (party["gst_type"], party["state_code"]) == ("unregistered", "27")


def test_only_debtors_and_creditors_are_parties(accountant, company):
    response = add_ledger(accountant, company, "Indirect Expenses", party={"gst_type": "consumer"})
    assert "Sundry Debtors or Sundry Creditors" in str(response.json())
    response = add_ledger(accountant, company, "Indirect Expenses")
    assert response.status_code == 201
    assert response.json()["party"] is None


def test_party_changes_are_in_the_ledger_activity(accountant, company):
    created = add_ledger(accountant, company, "Sundry Debtors").json()
    url = f"ledgers/{created['id']}/"
    party = {
        "gst_type": "regular",
        "gstin": gstin("27"),
        "credit_term": term_id(accountant, company, "45 days"),
        "contacts": [{"name": "Mr Rao", "phone": "9876543210", "is_primary": True}],
    }
    assert call(accountant, "patch", url, {"party": party}).status_code == 200
    entries = call(
        accountant, "get", f"audit/?company={company}&type=ledger&id={created['id']}"
    ).json()["entries"]
    assert [e["action"] for e in entries] == ["update", "create"]
    changes = {c["label"]: (c["old"], c["new"]) for c in entries[0]["changes"]}
    assert changes == {
        "GST type": ("Unregistered business", "Registered (regular)"),
        "GSTIN": (None, gstin("27")),
        "PAN": (None, "AAPFU0939F"),
        "Credit terms": (None, "45 days"),
        "Contacts": (None, "Mr Rao, 9876543210 (main)"),
    }
    # The party made with the ledger is part of the ledger's "Added" entry.
    added = {c["label"] for c in entries[1]["changes"]}
    assert {"GST type", "State"} <= added


def test_people_list_for_the_salesman_picker(accountant, alpha):
    people = call(accountant, "get", "people/").json()
    assert {"id", "name"} <= set(people[0])
    with use_tenant(alpha):
        nobody = User.objects.create_user("x@x.in")
        client = Client()
        client.force_login(nobody)
    assert call(client, "get", "people/").status_code == 403


@pytest.fixture
def second(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurva Organics Ltd", state_code="27").pk


def test_a_party_is_shared_by_the_group(accountant, company, second):
    """One party, a ledger in each company: details shared, balances and
    credit limit per company (decision 0020)."""
    party = {"gst_type": "regular", "gstin": gstin("29"), "credit_limit": "100000"}
    first = add_ledger(accountant, company, "Sundry Debtors", party=party, also_in=[second])
    assert first.status_code == 201, first.json()
    shared = first.json()["party"]
    assert [c["name"] for c in shared["companies"]] == [
        "Apurva Organics Ltd",
        "Apurvam Organics LLP",
    ]
    other_id = next(c["ledger"] for c in shared["companies"] if c["id"] == second)
    other = call(accountant, "get", f"companies/{second}/ledgers/").json()
    other = next(x for x in other if x["id"] == other_id)
    assert other["group_name"] == "Sundry Debtors"
    assert other["party"]["gstin"] == gstin("29")
    assert other["party"]["credit_limit"] == "0.00"  # per company

    # A change made in one company shows in the other.
    change = {"party": {"contacts": [{"name": "Mr Rao", "is_primary": True}]}}
    assert call(accountant, "patch", f"ledgers/{other_id}/", change).status_code == 200
    again = call(accountant, "get", f"companies/{company}/ledgers/").json()
    again = next(x for x in again if x["id"] == first.json()["id"])
    assert again["party"]["contacts"][0]["name"] == "Mr Rao"
    assert again["party"]["credit_limit"] == "100000.00"


def test_pick_an_existing_party(accountant, company, second):
    made = add_ledger(accountant, company, "Sundry Debtors", party={"gst_type": "consumer"})
    party_id = made.json()["party"]["id"]
    choices = call(accountant, "get", f"parties/?not_in={second}").json()
    assert [p["id"] for p in choices] == [party_id]
    assert call(accountant, "get", f"parties/?not_in={company}").json() == []

    # The same name without picking it is refused.
    again = add_ledger(accountant, second, "Sundry Debtors")
    assert "Existing customer or supplier" in str(again.json())
    linked = add_ledger(accountant, second, "Sundry Debtors", party_id=party_id)
    assert linked.status_code == 201, linked.json()
    assert linked.json()["party"]["id"] == party_id
    assert linked.json()["party"]["gst_type"] == "consumer"
    # Only once per company.
    twice = add_ledger(accountant, second, "Sundry Debtors", name="Fresh Mart 2", party_id=party_id)
    assert "already has a ledger" in str(twice.json())
