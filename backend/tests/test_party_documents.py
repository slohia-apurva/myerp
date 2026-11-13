"""Documents (with attached files) kept for a customer or supplier."""

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant
from tests.test_parties import add_ledger, call

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def client_for(alpha, email, role):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=role.title())
        user.roles.set(Role.objects.filter(code=role))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def accountant(alpha):
    return client_for(alpha, "accounts@x.in", "accountant")


@pytest.fixture
def party(accountant, alpha):
    with use_tenant(alpha):
        company = create_company(name="Apurvam Organics LLP", state_code="27").pk
    ledger = add_ledger(accountant, company, "Sundry Debtors").json()
    return ledger["party"]["id"]


def post_file(client, doc, name="gst.pdf", body=b"%PDF-1.4 test", size=None):
    file = SimpleUploadedFile(name, body if size is None else b"x" * size)
    return client.post(f"/api/v1/party-documents/{doc}/files/", {"file": file}, HTTP_HOST=HOST)


def add_doc(client, party, **extra):
    body = {"kind": "gst", "number": "29ABCDE1234F1Z5", **extra}
    return call(client, "post", f"parties/{party}/documents/", body)


def test_add_a_document_and_attach_files(accountant, party):
    made = add_doc(accountant, party, issued_by="GST department")
    assert made.status_code == 201, made.json()
    doc = made.json()["id"]
    one = post_file(accountant, doc)
    two = post_file(accountant, doc, name="scan.JPG", body=b"\xff\xd8jpeg")
    assert one.status_code == 201 and two.status_code == 201
    listed = call(accountant, "get", f"parties/{party}/documents/").json()
    assert [f["filename"] for f in listed[0]["files"]] == ["gst.pdf", "scan.JPG"]
    got = accountant.get(f"/api/v1/party-document-files/{one.json()['id']}/", HTTP_HOST=HOST)
    assert got.content == b"%PDF-1.4 test" and got["Content-Type"] == "application/pdf"
    assert "inline" in got["Content-Disposition"] and got["X-Content-Type-Options"] == "nosniff"
    ledger_party = call(accountant, "get", f"parties/{party}/documents/")
    assert ledger_party.status_code == 200


def test_the_party_counts_its_documents(accountant, party, alpha):
    from core.models import Party

    add_doc(accountant, party)
    other = add_doc(accountant, party, kind="pan", number="AAPFU0939F").json()["id"]
    call(accountant, "patch", f"party-documents/{other}/", {"is_active": False})
    with use_tenant(alpha):
        from core.parties import PartySerializer

        assert PartySerializer(Party.objects.get(pk=party)).data["document_count"] == 1


def test_file_checks(accountant, party):
    doc = add_doc(accountant, party).json()["id"]
    assert post_file(accountant, doc, name="virus.exe").status_code == 400
    assert post_file(accountant, doc, name="page.html").status_code == 400
    big = post_file(accountant, doc, name="big.pdf", size=10 * 1024 * 1024 + 1)
    assert big.status_code == 400 and "10 MB" in str(big.json())
    assert post_file(accountant, doc, name="ok.xlsx", body=b"PK").status_code == 201
    files = call(accountant, "get", f"parties/{party}/documents/").json()[0]["files"]
    page = accountant.get(f"/api/v1/party-document-files/{files[0]['id']}/", HTTP_HOST=HOST)
    assert "attachment" in page["Content-Disposition"]  # Excel downloads, never opens inline


def test_document_checks(accountant, party):
    assert add_doc(accountant, party, kind="other").status_code == 400  # needs a name
    assert add_doc(accountant, party, kind="other", name="Brand letter").status_code == 201
    assert add_doc(accountant, party, kind="pan", number="BAD").status_code == 400
    bad = add_doc(accountant, party, valid_from="2026-05-01", valid_until="2026-01-01")
    assert bad.status_code == 400 and "valid_until" in bad.json()


def test_a_wrong_file_can_be_taken_off_and_a_document_is_only_disabled(accountant, party):
    doc = add_doc(accountant, party).json()["id"]
    file = post_file(accountant, doc).json()["id"]
    gone = accountant.delete(f"/api/v1/party-document-files/{file}/", HTTP_HOST=HOST)
    assert gone.status_code == 204
    assert call(accountant, "get", f"parties/{party}/documents/").json()[0]["files"] == []
    assert accountant.delete(f"/api/v1/party-documents/{doc}/", HTTP_HOST=HOST).status_code == 405
    off = call(accountant, "patch", f"party-documents/{doc}/", {"is_active": False})
    assert off.json()["is_active"] is False


def test_viewer_may_read_but_not_change(accountant, party, alpha):
    doc = add_doc(accountant, party).json()["id"]
    file = post_file(accountant, doc).json()["id"]
    viewer = client_for(alpha, "view@x.in", "viewer")
    assert call(viewer, "get", f"parties/{party}/documents/").status_code == 200
    assert viewer.get(f"/api/v1/party-document-files/{file}/", HTTP_HOST=HOST).status_code == 200
    assert add_doc(viewer, party).status_code == 403
    assert post_file(viewer, doc).status_code == 403
    assert call(viewer, "patch", f"party-documents/{doc}/", {"notes": "x"}).status_code == 403
    assert viewer.delete(f"/api/v1/party-document-files/{file}/", HTTP_HOST=HOST).status_code == 403


def test_renewals_for_the_dashboard(accountant, party):
    today = datetime.date.today()
    day = lambda n: (today + datetime.timedelta(days=n)).isoformat()  # noqa: E731
    add_doc(accountant, party, kind="fssai", number="1", valid_until=day(-10))  # old, renewed below
    add_doc(accountant, party, kind="fssai", number="2", valid_until=day(300))  # the renewal
    add_doc(accountant, party, kind="agreement", number="SA1", valid_until=day(20))
    add_doc(accountant, party, kind="udyam", number="U1", valid_until=day(200))  # not soon
    add_doc(accountant, party, kind="gst", number="G1")  # never lapses
    lapsed = add_doc(accountant, party, kind="bank", number="B1", valid_until=day(-3)).json()
    call(accountant, "patch", f"party-documents/{lapsed['id']}/", {"is_active": False})
    rows = call(accountant, "get", "party-documents/renewals/").json()
    assert [r["kind_label"] for r in rows] == ["Agreement or contract"]
    assert rows[0]["party"]
