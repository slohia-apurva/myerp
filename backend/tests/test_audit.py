"""The audit log: every change to a master, with who, when, old and new."""

import pytest
from django.test import Client

from accounts.models import Role, User
from audit.models import AuditEntry
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


@pytest.fixture
def as_user(alpha):
    def make(*role_codes: str, name: str = "", companies=()):
        with use_tenant(alpha):
            user = User.objects.create_user(
                f"{'-'.join(role_codes) or 'none'}{len(companies)}@x.in", full_name=name
            )
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


def log(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    response = call(client, "get", f"audit/?{query}")
    assert response.status_code == 200, response.json()
    return response.json()["entries"]


def changed(entry) -> dict:
    return {c["label"]: (c["old"], c["new"]) for c in entry["changes"]}


def group_id(client, company, name):
    detail = call(client, "get", f"companies/{company}/").json()
    return next(g["id"] for g in detail["ledger_groups"] if g["name"] == name)


def test_a_new_company_logs_one_entry_not_its_setup(as_user):
    owner = as_user("owner", name="Sidharth")
    data = {"name": "Apurva Organics Ltd", "state_code": "27"}
    response = call(owner, "post", "companies/", data)
    company = response.json()["id"]
    entries = log(owner, company=company)
    # The head office, standard groups and Cash ledger are MyERP's setup.
    assert [(e["type"], e["action"]) for e in entries] == [("company", "create")]
    entry = entries[0]
    assert entry["user_name"] == "Sidharth"
    assert entry["record_name"] == "Apurva Organics Ltd"
    assert changed(entry)["State"] == (None, "Maharashtra")
    assert changed(entry)["Financial year starts in"] == (None, "April")


def test_ledger_changes_show_old_and_new(as_user, company):
    accountant = as_user("accountant", name="Asha")
    debtors = group_id(accountant, company, "Sundry Debtors")
    path = f"companies/{company}/ledgers/"
    created = call(accountant, "post", path, {"name": "Fresh Mart", "group": debtors}).json()
    url = f"ledgers/{created['id']}/"

    call(accountant, "patch", url, {"name": "Fresh Mart Pvt Ltd", "notes": "Pune"})
    bill = {"ref": "B1", "bill_date": "2025-03-10", "amount": "500", "side": "dr"}
    response = call(
        accountant,
        "patch",
        url,
        {"bill_wise": True, "opening_amount": "500", "opening_bills": [bill]},
    )
    assert response.status_code == 200, response.json()
    # Saving with nothing changed adds nothing.
    call(accountant, "patch", url, {"notes": "Pune"})

    entries = log(accountant, company=company, type="ledger", id=created["id"])
    assert [e["action_label"] for e in entries] == ["Changed", "Changed", "Added"]
    bills, rename, added = entries
    assert changed(rename) == {
        "Name": ("Fresh Mart", "Fresh Mart Pvt Ltd"),
        "Notes": (None, "Pune"),
    }
    # One Save is one entry, opening bills included, though the ledger is
    # saved more than once behind the scenes.
    assert changed(bills) == {
        "Opening balance (₹)": ("0.00", "500.00"),
        "Opening bills": (None, "B1 of 10-03-2025, Dr 500.00"),
    }
    assert changed(added)["Under group"] == (None, "Sundry Debtors")
    assert all(e["user_name"] == "Asha" for e in entries)

    # A failed save leaves no entry.
    call(accountant, "patch", url, {"opening_amount": "900"})
    assert len(log(accountant, company=company, type="ledger", id=created["id"])) == 3


def test_moving_a_default_logs_both_branches(as_user, company):
    owner = as_user("owner")
    path = f"companies/{company}/branches/"
    depot = call(owner, "post", path, {"name": "Depot", "state_code": "27"}).json()
    call(owner, "patch", f"branches/{depot['id']}/", {"default_ship_from": True})
    entries = log(owner, company=company, type="branch")
    assert sorted((e["record_name"], e["action"]) for e in entries) == [
        ("Depot", "create"),
        ("Depot", "update"),
        ("Head office", "update"),
    ]
    by_name = {e["record_name"]: e for e in entries if e["action"] == "update"}
    assert changed(by_name["Head office"]) == {"Default ship from": ("Yes", "No")}
    assert changed(by_name["Depot"]) == {"Default ship from": ("No", "Yes")}


def test_deleting_a_group_is_logged(as_user, company):
    owner = as_user("owner")
    debtors = group_id(owner, company, "Sundry Debtors")
    path = f"companies/{company}/ledger-groups/"
    group = call(owner, "post", path, {"name": "Export debtors", "parent": debtors}).json()
    assert call(owner, "delete", f"ledger-groups/{group['id']}/").status_code == 204
    entries = log(owner, company=company, type="ledger_group", id=group["id"])
    assert [e["action_label"] for e in entries] == ["Deleted", "Added"]
    assert changed(entries[0])["Name"] == ("Export debtors", None)


def test_user_roles_and_companies_are_logged(as_user, alpha, company):
    owner = as_user("owner")
    with use_tenant(alpha):
        sales = Role.objects.get(code="sales").pk
    data = {"email": "ravi@x.in", "full_name": "Ravi", "roles": []}
    response = call(owner, "post", "users/", data)
    user = response.json()["id"]
    call(owner, "patch", f"users/{user}/", {"roles": [sales], "companies": [company]})
    entries = log(owner, type="user", id=user)
    assert [e["action"] for e in entries] == ["update", "create"]
    assert changed(entries[0]) == {
        "Roles": (None, "Sales"),
        "Companies": ("All", "Apurvam Organics LLP"),
    }


def test_who_may_read_the_log(as_user, alpha, company):
    with use_tenant(alpha):
        other = create_company(name="Other Co", state_code="29").pk
    owner = as_user("owner")
    call(owner, "patch", f"companies/{other}/", {"phone": "9876543210"})

    only_first = as_user("accountant", companies=[company])
    assert call(only_first, "get", f"audit/?company={other}").status_code == 404
    assert call(only_first, "get", f"audit/?company={company}").status_code == 200
    # Changes to users and roles need the users permission.
    assert call(only_first, "get", "audit/").status_code == 403
    assert call(owner, "get", "audit/").status_code == 200
    assert call(as_user(), "get", f"audit/?company={company}").status_code == 403


def test_entries_cannot_be_changed(alpha, company):
    with use_tenant(alpha):
        entry = AuditEntry.objects.create(
            record_type="company", record_id=company, record_name="X", action="update"
        )
        entry.record_name = "Y"
        with pytest.raises(RuntimeError):
            entry.save()
        with pytest.raises(RuntimeError):
            entry.delete()
