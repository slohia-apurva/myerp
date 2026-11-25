"""Salesmen and Purchasers: people with or without a sign-in, picked on
customers (Salesman) and suppliers (Purchaser)."""

import pytest

from accounts.models import User
from tenancy.context import use_tenant
from tests.test_parties import accountant, add_ledger, call, company  # noqa: F401

pytestmark = pytest.mark.django_db(databases="__all__")


def test_add_a_person_without_a_sign_in(accountant):  # noqa: F811
    made = call(
        accountant,
        "post",
        "sales-people/",
        {"name": "  Ramesh   Kumar ", "is_purchaser": True, "mobile": "98300 12345"},
    )
    assert made.status_code == 201, made.json()
    body = made.json()
    assert body["name"] == "Ramesh Kumar"
    assert body["user"] is None and body["party_count"] == 0

    # Same name, other capitals: refused, naming the existing person.
    again = call(accountant, "post", "sales-people/", {"name": "ramesh kumar", "is_salesman": True})
    assert again.status_code == 400
    assert again.json()["existing"]["id"] == str(body["id"])

    # Neither tick: refused.
    none = call(accountant, "post", "sales-people/", {"name": "Anil"})
    assert none.status_code == 400 and "is_salesman" in none.json()


def test_a_person_may_be_linked_to_one_sign_in(accountant, alpha):  # noqa: F811
    with use_tenant(alpha):
        ravi = User.objects.create_user("ravi@x.in", full_name="Ravi").pk
    one = call(
        accountant, "post", "sales-people/", {"name": "Ravi", "is_salesman": True, "user": ravi}
    )
    assert one.status_code == 201, one.json()
    assert one.json()["user_name"] == "Ravi"
    two = call(
        accountant, "post", "sales-people/", {"name": "Ravi K", "is_salesman": True, "user": ravi}
    )
    assert two.status_code == 400 and "user" in two.json()


def test_pickers_follow_the_ticks(accountant, company):  # noqa: F811
    buyer = call(accountant, "post", "sales-people/", {"name": "Ramesh", "is_purchaser": True})
    buyer = buyer.json()["id"]
    # A purchaser cannot be a customer's salesman ...
    refused = add_ledger(
        accountant, company, "Sundry Debtors", party={"gst_type": "consumer", "salesman": buyer}
    )
    assert refused.status_code == 400
    assert "Salesman" in str(refused.json())
    # ... but is a supplier's purchaser.
    made = add_ledger(
        accountant,
        company,
        "Sundry Creditors",
        name="Tea Traders",
        party={"gst_type": "consumer", "salesman": buyer},
    )
    assert made.status_code == 201, made.json()
    assert made.json()["party"]["salesman_name"] == "Ramesh"
    people = call(accountant, "get", "sales-people/").json()
    assert people[0]["party_count"] == 1

    # Picked on a supplier: the Purchaser tick stays.
    untick = call(
        accountant, "patch", f"sales-people/{buyer}/", {"is_purchaser": False, "is_salesman": True}
    )
    assert untick.status_code == 400 and "is_purchaser" in untick.json()

    # Disabled: kept where picked, not picked anew.
    off = call(accountant, "patch", f"sales-people/{buyer}/", {"is_active": False})
    assert off.status_code == 200
    another = add_ledger(
        accountant,
        company,
        "Sundry Creditors",
        name="Leaf Co",
        party={"gst_type": "consumer", "salesman": buyer},
    )
    assert another.status_code == 400 and "disabled" in str(another.json())
    ledger = made.json()["id"]
    kept = call(accountant, "patch", f"ledgers/{ledger}/", {"party": {"salesman": buyer}})
    assert kept.status_code == 200, kept.json()


def test_a_stores_person_needs_no_other_tick(accountant):  # noqa: F811
    made = call(accountant, "post", "sales-people/", {"name": "Ramesh", "is_stores": True})
    assert made.status_code == 201, made.json()
    assert made.json()["is_stores"] is True


def test_the_people_list_comes_a_page_at_a_time(accountant, alpha):  # noqa: F811
    """Large lists (Sidharth 2026-11-24): 25 a page, column searches and sorting on
    the server, disabled people only with "Show Inactive People"."""
    from core.models import SalesPerson

    with use_tenant(alpha):
        SalesPerson.objects.bulk_create(
            SalesPerson(
                name=f"Person {n:02d}",
                is_salesman=n % 2 == 0,
                is_purchaser=n % 2 == 1,
                is_stores=n % 10 == 0,
                mobile=f"98300{n:05d}",
                is_active=n != 1,
            )
            for n in range(1, 31)
        )
        thirty = SalesPerson.objects.get(name="Person 30").pk
    first = call(accountant, "get", "sales-people/?page=1").json()
    assert (first["count"], first["pages"], len(first["results"])) == (29, 2, 25)
    assert first["results"][0]["name"] == "Person 02"
    last = call(accountant, "get", "sales-people/?page=2&inactive=1").json()
    assert last["results"][-1]["name"] == "Person 01"  # disabled: last

    stores = call(accountant, "get", "sales-people/?page=1&works=store").json()
    assert [p["name"] for p in stores["results"]] == ["Person 10", "Person 20", "Person 30"]
    by_mobile = call(accountant, "get", "sales-people/?page=1&sort=-mobile").json()
    assert by_mobile["results"][0]["name"] == "Person 30"
    assert call(accountant, "get", f"sales-people/{thirty}/").json()["name"] == "Person 30"
    # The pickers still get everyone.
    assert len(call(accountant, "get", "sales-people/").json()) == 30
