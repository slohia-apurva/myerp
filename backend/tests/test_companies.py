"""Companies, branches and the Tally-style ledger group tree."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.india import gstin_check_char, validate_gstin
from core.models import Company, LedgerGroup
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"
# A published example GSTIN (Maharashtra) and the same PAN registered in Karnataka.
GSTIN_MH = "27AAPFU0939F1ZV"
GSTIN_KA = "29AAPFU0939F1Z" + gstin_check_char("29AAPFU0939F1Z")


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
def owner(as_user):
    return as_user("owner")


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def add_company(client, **extra):
    data = {"name": "Apurvam Organics LLP", "state_code": "27", "gstin": GSTIN_MH, **extra}
    return call(client, "post", "companies/", data)


def groups_of(client, company_id):
    detail = call(client, "get", f"companies/{company_id}/").json()
    return {g["name"]: g for g in detail["ledger_groups"]}


def test_gstin_check_character():
    for known in ("27AAPFU0939F1ZV", "29AAGCB7383J1Z4"):
        validate_gstin(known)
    with pytest.raises(Exception, match="last character"):
        validate_gstin("27AAPFU0939F1ZW")
    with pytest.raises(Exception, match="state code"):
        validate_gstin("99AAPFU0939F1Z" + gstin_check_char("99AAPFU0939F1Z"))


def test_new_company_starts_with_head_office_and_tally_groups(owner):
    response = add_company(owner)
    assert response.status_code == 201, response.json()
    company = response.json()
    assert company["abbr"] == "AOL"
    assert company["pan"] == "AAPFU0939F"
    assert company["state"] == "Maharashtra"
    assert company["fiscal_year_start_month"] == 4

    detail = call(owner, "get", f"companies/{company['id']}/").json()
    assert [(b["name"], b["is_head_office"], b["gstin"]) for b in detail["branches"]] == [
        ("Head office", True, GSTIN_MH)
    ]
    groups = detail["ledger_groups"]
    primary = [g for g in groups if g["parent"] is None]
    assert len(primary) == 15 and len(groups) == 28
    by_name = {g["name"]: g for g in groups}
    assert by_name["Sundry Debtors"]["parent"] == by_name["Current Assets"]["id"]
    assert by_name["Sundry Debtors"]["nature"] == "asset"
    assert by_name["Duties & Taxes"]["nature"] == "liability"
    assert by_name["Sales Accounts"]["affects_gross_profit"] is True
    assert by_name["Indirect Expenses"]["affects_gross_profit"] is False
    assert all(g["is_standard"] and g["code"] for g in groups)


def test_company_checks(owner):
    assert "different state" in str(add_company(owner, state_code="29").json())
    assert "match" in str(add_company(owner, pan="ABCPE1234F").json())
    assert "last character" in str(add_company(owner, gstin="27aapfu0939f1zw").json())
    assert add_company(owner).status_code == 201
    assert "already" in str(add_company(owner, name="apurvam organics llp").json())
    # Unregistered is allowed; the short code is made unique.
    second = add_company(owner, name="Apurva Organics Ltd", gstin="")
    assert second.status_code == 201 and second.json()["abbr"] == "AOL2"


def test_only_owner_adds_companies_editors_edit(owner, as_user):
    company_id = add_company(owner).json()["id"]
    accountant = as_user("accountant")
    assert add_company(accountant, name="Other").status_code == 403
    response = call(accountant, "patch", f"companies/{company_id}/", {"address": "Pune"})
    assert response.status_code == 200 and response.json()["address"] == "Pune"
    response = call(accountant, "patch", f"companies/{company_id}/", {"abbr": "XYZ"})
    assert response.status_code == 400

    viewer = as_user("viewer")
    assert call(viewer, "get", f"companies/{company_id}/").status_code == 200
    assert call(viewer, "patch", f"companies/{company_id}/", {"address": "x"}).status_code == 403
    assert call(as_user(), "get", "companies/").status_code == 403


def test_user_limited_to_one_company_sees_only_it(owner, as_user, alpha):
    mine = add_company(owner).json()["id"]
    with use_tenant(alpha):
        other = Company.objects.get(name="Alpha Foods LLP")
    limited = as_user("viewer", companies=[mine])
    assert [c["id"] for c in call(limited, "get", "companies/").json()] == [mine]
    assert call(limited, "get", f"companies/{other.pk}/").status_code == 404
    assert limited.get("/api/whoami/", HTTP_HOST=HOST).json()["companies"] == [
        "Apurvam Organics LLP"
    ]


def test_branches(owner):
    company_id = add_company(owner).json()["id"]
    path = f"companies/{company_id}/branches/"
    karnataka = {"name": "Bengaluru depot", "state_code": "29", "gstin": GSTIN_KA}
    response = call(owner, "post", path, karnataka)
    assert response.status_code == 201, response.json()
    assert "already" in str(
        call(owner, "post", path, {**karnataka, "name": "bengaluru DEPOT"}).json()
    )

    other_pan = "29ABCPE1234F1Z" + gstin_check_char("29ABCPE1234F1Z")
    response = call(owner, "post", path, {**karnataka, "name": "X", "gstin": other_pan})
    assert "company's PAN" in str(response.json())
    response = call(owner, "post", path, {**karnataka, "name": "Y", "state_code": "27"})
    assert "different state" in str(response.json())

    head = call(owner, "get", f"companies/{company_id}/").json()["branches"][0]
    response = call(owner, "patch", f"branches/{head['id']}/", {"is_active": False})
    assert "head office" in str(response.json())

    # The PAN cannot change while branch GSTINs use it.
    response = call(owner, "patch", f"companies/{company_id}/", {"gstin": "", "pan": "ABCPE1234F"})
    assert response.status_code == 400
    assert call(owner, "get", f"companies/{company_id}/").json()["company"]["pan"] == "AAPFU0939F"


def test_custom_groups_follow_their_parent(owner):
    company_id = add_company(owner).json()["id"]
    groups = groups_of(owner, company_id)
    path = f"companies/{company_id}/ledger-groups/"

    export = call(
        owner, "post", path, {"name": "Export debtors", "parent": groups["Sundry Debtors"]["id"]}
    )
    assert export.status_code == 201 and export.json()["nature"] == "asset"
    export_id = export.json()["id"]
    europe = call(owner, "post", path, {"name": "Europe", "parent": export_id}).json()

    assert "already" in str(
        call(owner, "post", path, {"name": "sundry debtors", "parent": export_id}).json()
    )
    assert "under" in str(call(owner, "post", path, {"name": "Top"}).json())

    # Moving a group carries the groups under it to the new nature.
    response = call(
        owner, "patch", f"ledger-groups/{export_id}/", {"parent": groups["Sundry Creditors"]["id"]}
    )
    assert response.json()["nature"] == "liability"
    assert groups_of(owner, company_id)["Europe"]["nature"] == "liability"
    response = call(owner, "patch", f"ledger-groups/{export_id}/", {"parent": europe["id"]})
    assert "itself" in str(response.json())

    assert "first" in str(call(owner, "delete", f"ledger-groups/{export_id}/").json())
    assert call(owner, "delete", f"ledger-groups/{europe['id']}/").status_code == 204


def test_standard_groups_cannot_be_changed(owner, as_user):
    company_id = add_company(owner).json()["id"]
    debtors = groups_of(owner, company_id)["Sundry Debtors"]["id"]
    assert (
        call(owner, "patch", f"ledger-groups/{debtors}/", {"name": "Customers"}).status_code == 400
    )
    assert call(owner, "delete", f"ledger-groups/{debtors}/").status_code == 400
    path = f"companies/{company_id}/ledger-groups/"
    assert (
        call(as_user("viewer"), "post", path, {"name": "X", "parent": debtors}).status_code == 403
    )


def test_groups_belong_to_one_company(owner, alpha):
    a = add_company(owner).json()["id"]
    b = add_company(owner, name="Apurva Organics Ltd", gstin="").json()["id"]
    b_debtors = groups_of(owner, b)["Sundry Debtors"]["id"]
    response = call(
        owner, "post", f"companies/{a}/ledger-groups/", {"name": "X", "parent": b_debtors}
    )
    assert response.status_code == 400
    with use_tenant(alpha):
        assert LedgerGroup.objects.filter(company_id=a, code="sundry_debtors").count() == 1


def test_contact_details_on_company_and_branches(owner):
    contact = {
        "address": "Plot 12, MIDC Bhosari\nPune",
        "pincode": "411026",
        "phone": "+91 98200 12345",
        "email": "accounts@apurvam.in",
        "contact_person": "Sidharth Lohia",
    }
    company = add_company(owner, **contact).json()
    assert {k: company[k] for k in contact} == contact
    # The head office starts with the company's address and contact.
    detail = call(owner, "get", f"companies/{company['id']}/").json()
    head = detail["branches"][0]
    assert {k: head[k] for k in contact} == contact

    branch = {"name": "Nagpur depot", "state_code": "27", **contact, "pincode": "440001"}
    branch["phone"] = "0712-234 5678"
    response = call(owner, "post", f"companies/{company['id']}/branches/", branch)
    assert response.status_code == 201, response.json()
    assert response.json()["phone"] == "0712-234 5678"

    bad = call(owner, "patch", f"branches/{head['id']}/", {"phone": "call me", "pincode": "0123"})
    assert bad.status_code == 400
    assert set(bad.json()) >= {"phone"}
    bad = call(owner, "patch", f"branches/{head['id']}/", {"pincode": "0123"})
    assert "pincode" in bad.json()
    bad = call(owner, "patch", f"companies/{company['id']}/", {"email": "not-an-email"})
    assert "email" in bad.json()


def test_registration_numbers(owner):
    company = add_company(
        owner,
        entity_type="llp",
        cin="aab-1234",
        tan="pnea12345b",
        incorporation_date="2015-06-01",
    ).json()
    assert (company["cin"], company["tan"]) == ("AAB-1234", "PNEA12345B")
    path = f"companies/{company['id']}/"
    # An LLP takes an LLPIN, not a CIN.
    bad = call(owner, "patch", path, {"cin": "U01100MH2015PTC123456"})
    assert "LLPIN" in bad.json()["cin"][0]
    ok = call(
        owner, "patch", path, {"entity_type": "private_limited", "cin": "U01100MH2015PTC123456"}
    )
    assert ok.status_code == 200, ok.json()
    bad = call(owner, "patch", path, {"entity_type": "partnership"})
    assert "cin" in bad.json()
    assert "tan" in call(owner, "patch", path, {"tan": "12345"}).json()


def test_one_default_address_of_each_kind(owner):
    company_id = add_company(owner).json()["id"]
    path = f"companies/{company_id}/branches/"
    head = call(owner, "get", f"companies/{company_id}/").json()["branches"][0]
    assert head["default_billing"] and head["default_ship_to"] and head["default_ship_from"]

    depot = call(
        owner,
        "post",
        path,
        {"name": "Bhiwandi depot", "state_code": "27", "default_ship_from": True},
    ).json()
    branches = {
        b["name"]: b for b in call(owner, "get", f"companies/{company_id}/").json()["branches"]
    }
    assert branches["Bhiwandi depot"]["default_ship_from"]
    assert not branches["Head office"]["default_ship_from"]
    assert branches["Head office"]["default_billing"]

    # Unticking the only default is refused; it moves by ticking another branch.
    bad = call(owner, "patch", f"branches/{depot['id']}/", {"default_ship_from": False})
    assert "default_ship_from" in bad.json()
    # A branch holding a default cannot be closed.
    bad = call(owner, "patch", f"branches/{depot['id']}/", {"is_active": False})
    assert "is_active" in bad.json()
    call(owner, "patch", f"branches/{head['id']}/", {"default_ship_from": True})
    ok = call(owner, "patch", f"branches/{depot['id']}/", {"is_active": False})
    assert ok.status_code == 200, ok.json()


def test_certificates_with_renewal_dates(owner):
    company_id = add_company(owner).json()["id"]
    head = call(owner, "get", f"companies/{company_id}/").json()["branches"][0]
    path = f"companies/{company_id}/certificates/"
    fssai = {
        "kind": "fssai",
        "number": "11526998000123",
        "issued_by": "FSSAI",
        "branch": head["id"],
        "valid_from": "2023-04-01",
        "valid_until": "2028-03-31",
    }
    response = call(owner, "post", path, fssai)
    assert response.status_code == 201, response.json()
    assert response.json()["branch_name"] == "Head office"
    udyam = call(owner, "post", path, {"kind": "udyam", "number": "udyam-mh-26-0012345"}).json()
    assert udyam["number"] == "UDYAM-MH-26-0012345" and udyam["valid_until"] is None

    assert "number" in call(owner, "post", path, {**fssai, "number": "12ab"}).json()
    iec = {"kind": "iec", "number": "aapfu0939f", "valid_until": "2027-06-30"}
    assert call(owner, "post", path, iec).json()["number"] == "AAPFU0939F"
    assert "name" in call(owner, "post", path, {"kind": "other", "number": "X1"}).json()
    backwards = {**fssai, "valid_until": "2022-01-01"}
    assert "valid_until" in call(owner, "post", path, backwards).json()

    other_company = add_company(owner, name="Apurva Organics Ltd", gstin="").json()["id"]
    other_head = call(owner, "get", f"companies/{other_company}/").json()["branches"][0]
    bad = call(owner, "post", path, {**fssai, "branch": other_head["id"]})
    assert "branch" in bad.json()

    renewed = call(owner, "patch", f"certificates/{udyam['id']}/", {"notes": "Re-classified"})
    assert renewed.status_code == 200
    assert call(owner, "delete", f"certificates/{udyam['id']}/").status_code == 405
    detail = call(owner, "get", f"companies/{company_id}/").json()
    assert [c["kind"] for c in detail["certificates"]] == ["fssai", "iec", "udyam"]
