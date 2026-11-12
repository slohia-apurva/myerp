"""Import and export for the masters kept per company: ledger groups,
branches, licences and certificates, and courier accounts."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from openpyxl import load_workbook

from accounts.models import Role, User
from core.india import gstin_check_char
from core.models import Branch, Certificate, LedgerGroup
from shipping.models import CourierAccount
from tenancy.context import use_tenant
from tests.test_exchange import book

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"
TRANSPORTER_GSTIN = "07AAACD1234F1Z" + gstin_check_char("07AAACD1234F1Z")


@pytest.fixture
def owner(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("owner@x.in", full_name="Owner")
        user.roles.set(Role.objects.filter(code="owner"))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def company(alpha):
    from core.companies import create_company

    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def export(client, key, company):
    response = client.get(f"/api/v1/exchange/{key}/?as=xlsx&company={company}", HTTP_HOST=HOST)
    assert response.status_code == 200
    return [list(r) for r in load_workbook(io.BytesIO(response.content)).worksheets[0].values]


def send(client, key, company, rows, commit=False):
    return client.post(
        f"/api/v1/exchange/{key}/import/",
        {
            "file": SimpleUploadedFile("x.xlsx", book({"Sheet": rows})),
            "commit": "1" if commit else "0",
            "company": str(company),
        },
        HTTP_HOST=HOST,
    ).json()


def test_ledger_groups_add_under_a_parent_and_keep_standard_ones(owner, company, alpha):
    rows = export(owner, "ledger-groups", company)
    assert rows[0][:5] == ["ID", "Name", "Under group", "Nature", "Standard"]
    debtors = next(r for r in rows if r[1] == "Sundry Debtors")
    assert debtors[2] == "Current Assets"

    # The whole export back, unchanged, plus two new groups: the second under the first.
    rows += [
        [None, "Export debtors", "Sundry Debtors"],
        [None, "Europe debtors", "Export debtors"],
    ]
    out = send(owner, "ledger-groups", company, rows, commit=True)
    assert out["errors"] == [] and out["saved"]
    assert out["new"] == 2 and out["changed"] == 0
    with use_tenant(alpha):
        europe = LedgerGroup.objects.get(company_id=company, name="Europe debtors")
        assert europe.parent.name == "Export debtors"
        assert europe.nature == debtors_nature(company)

    renamed = [rows[0], [debtors[0], "Trade debtors", "Current Assets"]]
    out = send(owner, "ledger-groups", company, renamed)
    assert out["errors"][0]["messages"] == [
        "Standard groups come with MyERP and cannot be changed."
    ]


def debtors_nature(company):
    return LedgerGroup.objects.get(company_id=company, name="Sundry Debtors").nature


def test_branches_and_certificates(owner, company, alpha):
    head = ["ID", "Name", "State", "City", "Default billing"]
    out = send(
        owner,
        "branches",
        company,
        [head, [None, "Pune depot", "Maharashtra", "Pune", "Yes"]],
        commit=True,
    )
    assert out["errors"] == [] and out["new"] == 1
    with use_tenant(alpha):
        assert Branch.objects.get(company_id=company, default_billing=True).name == "Pune depot"

    again = send(owner, "branches", company, [head, [None, "pune  DEPOT", "Maharashtra", "", ""]])
    assert "already has a branch" in again["errors"][0]["messages"][0]

    head = ["ID", "Certificate", "Number", "Branch", "Renewal date"]
    rows = [
        head,
        [None, "FSSAI licence / registration", "11521999000123", "Pune depot", "31-03-2027"],
    ]
    out = send(owner, "certificates", company, rows, commit=True)
    assert out["errors"] == [], out
    with use_tenant(alpha):
        cert = Certificate.objects.get(company_id=company)
        assert cert.branch.name == "Pune depot" and str(cert.valid_until) == "2027-03-31"

    bad = send(
        owner,
        "certificates",
        company,
        [head, [None, "FSSAI licence / registration", "1", "Nashik", ""]],
    )
    assert "Branch" in bad["errors"][0]["messages"][0]


def test_courier_accounts_name_their_courier(owner, company, alpha):
    head = ["ID", "Courier in MyERP's list", "Name", "GSTIN", "Service"]
    rows = [head, [None, "Delhivery", "Delhivery B2C", TRANSPORTER_GSTIN, "B2C"]]
    out = send(owner, "courier-accounts", company, rows, commit=True)
    assert out["errors"] == [], out
    with use_tenant(alpha):
        assert CourierAccount.objects.get(company_id=company).name == "Delhivery B2C"
    assert export(owner, "courier-accounts", company)[1][1] == "Delhivery"
    own = [head, [None, None, "Local Roadways", TRANSPORTER_GSTIN, "B2B"]]
    assert send(owner, "courier-accounts", company, own, commit=True)["errors"] == []
    missing = [head, [None, None, "No GST Roadways", None, "B2B"]]
    out = send(owner, "courier-accounts", company, missing)
    assert "GSTIN" in str(out["errors"])

    bad = send(
        owner,
        "courier-accounts",
        company,
        [head, [None, "Pigeon Post", "X", TRANSPORTER_GSTIN, "B2C"]],
    )
    assert "no courier 'Pigeon Post'" in bad["errors"][0]["messages"][0]
