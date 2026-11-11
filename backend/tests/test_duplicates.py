"""No duplicate masters (core/duplicates.py): names ignore capitals and extra
spaces, registration numbers are unique, and a refusal names the record
already there so the screen can link to it."""

import pytest
from django.db import IntegrityError
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from core.models import Party, Unit
from tenancy.context import tenant_atomic, use_tenant
from tests.test_parties import add_ledger, gstin

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def _client(alpha, email, role):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=email.split("@")[0])
        user.roles.set(Role.objects.filter(code=role))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def owner(alpha):
    return _client(alpha, "owner@x.in", "owner")


@pytest.fixture
def accountant(alpha):
    return _client(alpha, "accounts@x.in", "accountant")


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def test_names_ignore_capitals_and_spaces_and_link_to_the_one_there(accountant, alpha):
    first = call(
        accountant,
        "post",
        "units/",
        {"name": "  Big   Drum ", "short_name": "bdr", "gst_code": "DRM"},
    )
    assert first.status_code == 201, first.json()
    assert first.json()["name"] == "Big Drum"  # tidied
    again = call(
        accountant, "post", "units/", {"name": "big drum", "short_name": "bd2", "gst_code": "DRM"}
    )
    assert again.status_code == 400
    body = again.json()
    assert body["name"] == ['There is already a unit with the name "Big Drum".']
    assert body["existing"] == {"kind": "unit", "id": str(first.json()["id"]), "name": "Big Drum"}


def test_names_are_tidied_on_every_save(alpha):
    with use_tenant(alpha):
        unit = Unit.objects.create(name=" Tin   can ", short_name=" tc ", gst_code="CAN")
        unit.refresh_from_db()
        assert (unit.name, unit.short_name) == ("Tin can", "tc")
        # The database refuses what slips past the screens.
        with pytest.raises(IntegrityError), tenant_atomic():
            Unit.objects.create(name="TIN  CAN", short_name="tc2", gst_code="CAN")


def test_one_party_per_gstin(accountant, company):
    number = gstin("29")
    first = add_ledger(
        accountant, company, "Sundry Debtors", party={"gst_type": "regular", "gstin": number}
    )
    assert first.status_code == 201, first.json()
    again = add_ledger(
        accountant,
        company,
        "Sundry Debtors",
        name="Fresh Mart Bengaluru",
        party={"gst_type": "regular", "gstin": number.lower()},
    )
    assert again.status_code == 400
    body = again.json()
    assert "already on the customer or supplier" in body["party"]["gstin"][0]
    assert body["existing"]["kind"] == "ledger"
    assert body["existing"]["id"] == str(first.json()["id"])
    assert body["existing"]["company"] == str(company)


def test_party_name_clash_links_to_its_ledger(accountant, company, alpha):
    with use_tenant(alpha):
        other = create_company(name="Apurva Organics Ltd", state_code="27").pk
    first = add_ledger(accountant, company, "Sundry Debtors")
    assert first.status_code == 201
    again = add_ledger(accountant, other, "Sundry Creditors", name="FRESH  mart")
    assert again.status_code == 400
    assert again.json()["existing"]["id"] == str(first.json()["id"])
    with use_tenant(alpha):
        assert Party.objects.count() == 1


def test_companies_differ_in_name_gstin_and_pan(owner, alpha):
    with use_tenant(alpha):
        create_company(name="Alpha Exports", state_code="27", gstin=gstin("27"))
    clash = call(owner, "post", "companies/", {"name": "ALPHA  exports", "state_code": "27"})
    assert clash.status_code == 400
    assert clash.json()["name"] == ['There is already a company named "Alpha Exports".']
    clash = call(
        owner, "post", "companies/", {"name": "New Co", "state_code": "27", "gstin": gstin("27")}
    )
    assert "already has this GSTIN" in clash.json()["gstin"][0]
    clash = call(
        owner, "post", "companies/", {"name": "New Co", "state_code": "27", "pan": "aapfu0939f"}
    )
    assert "already has this PAN" in clash.json()["pan"][0]
    assert clash.json()["existing"]["kind"] == "company"


def test_one_bank_ledger_per_account(accountant, company):
    detail = call(accountant, "get", f"companies/{company}/").json()
    bank = next(g["id"] for g in detail["ledger_groups"] if g["name"] == "Bank Accounts")
    path = f"companies/{company}/ledgers/"
    first = call(
        accountant, "post", path, {"name": "HDFC", "group": bank, "account_number": "5020"}
    )
    assert first.status_code == 201
    again = call(
        accountant, "post", path, {"name": "HDFC 2", "group": bank, "account_number": " 5020 "}
    )
    assert again.status_code == 400
    assert again.json()["account_number"] == [
        'The ledger "HDFC" already has this bank account number.'
    ]


def test_role_names_ignore_capitals(owner):
    clash = call(owner, "post", "roles/", {"name": " ACCOUNTANT ", "permissions": []})
    assert clash.status_code == 400
    assert clash.json()["existing"]["kind"] == "role"


def test_branch_and_credit_term_names(accountant, company):
    clash = call(
        accountant,
        "post",
        f"companies/{company}/branches/",
        {"name": "head  OFFICE", "state_code": "27"},
    )
    assert clash.status_code == 400 and clash.json()["existing"]["kind"] == "branch"
    clash = call(
        accountant,
        "post",
        "credit-terms/",
        {"name": "30  DAYS", "parts": [{"percent": "100", "event": "bill", "days": 30}]},
    )
    assert clash.status_code == 400 and clash.json()["existing"]["kind"] == "credit_term"


def test_migration_checks_run_on_real_data(accountant, company, alpha):
    """The data checks in migration 0027 run cleanly on data without
    duplicates (they stop a deploy, with a list, when there are some)."""
    from importlib import import_module

    from django.apps import apps

    migration = import_module("core.migrations.0027_no_duplicates")
    add_ledger(
        accountant, company, "Sundry Debtors", party={"gst_type": "regular", "gstin": gstin("29")}
    )
    with use_tenant(alpha):
        migration.tidy_names(apps, None)
        migration.check_duplicates(apps, None)
        assert migration._repeats(Party.objects.all(), "country", what="Country") == []
        Party.objects.create(name="Second", state_code="27")
        assert migration._repeats(Party.objects.all(), "country", what="Country") == [
            "Country: India"
        ]
