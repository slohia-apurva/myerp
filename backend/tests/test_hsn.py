"""HSN codes: the central list in the platform database, its import and the picker search."""

import io

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy import hsn_import
from tenancy.context import use_tenant
from tenancy.models import HsnCode

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
def viewer(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("view@x.in", full_name="Vee")
        user.roles.set(Role.objects.filter(code="viewer"))
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


ROWS = [
    ("1701", "Cane or beet sugar and chemically pure sucrose"),
    ("170199", "Jaggery and other sugar, in solid form"),
    ("0910", "Ginger, saffron, turmeric (curcuma), thyme, bay leaves, curry"),
    ("4819", "Cartons, boxes, cases of corrugated paper"),
]


def results(client, query=""):
    return call(client, "get", f"hsn/?{query}").json()["results"]


def test_import_adds_updates_and_searches(accountant, company):
    first = hsn_import.load(ROWS)
    assert (first["added"], first["updated"], first["unchanged"], first["problems"]) == (
        4,
        0,
        0,
        [],
    )
    again = hsn_import.load([*ROWS[:2], (ROWS[2][0], "Turmeric and spices")])
    assert (again["added"], again["updated"], again["unchanged"]) == (0, 1, 2)

    assert [r["hsn_code"] for r in results(accountant, "q=17")] == ["1701", "170199"]
    assert [r["hsn_code"] for r in results(accountant, "q=turmeric")] == ["0910"]
    assert [r["hsn_code"] for r in results(accountant, "q=carton%20ginger")] == []  # every word
    assert [r["hsn_code"] for r in results(accountant, "q=carton%20corrugated")] == ["4819"]
    assert call(accountant, "get", "hsn/").json()["total"] == 4

    # The search box under each column narrows by that column alone, with the top box too.
    assert [r["hsn_code"] for r in results(accountant, "code=17")] == ["1701", "170199"]
    assert [r["hsn_code"] for r in results(accountant, "desc=sugar%20solid")] == ["170199"]
    assert [r["hsn_code"] for r in results(accountant, "code=09&desc=sugar")] == []
    assert [r["hsn_code"] for r in results(accountant, "q=sugar&code=1701")] == ["1701", "170199"]
    assert [r["hsn_code"] for r in results(accountant, "q=jaggery&code=1701")] == ["170199"]


def test_every_tenant_sees_the_same_central_list(accountant, company):
    hsn_import.load(ROWS)
    # The list lives in the platform database, not in any tenant's own.
    assert HsnCode.objects.db_manager("default").count() == 4
    assert [r["hsn_code"] for r in results(accountant, "limit=pick&q=sugar")] == ["1701", "170199"]


def test_picker_shows_only_active_codes(accountant, company):
    hsn_import.load(ROWS)
    HsnCode.objects.filter(hsn_code="1701").update(is_active=False)
    assert "1701" not in [r["hsn_code"] for r in results(accountant, "limit=pick&q=17")]
    assert "1701" in [r["hsn_code"] for r in results(accountant, "q=17")]


def test_a_bad_row_is_left_out_and_the_rest_load():
    done = hsn_import.load([ROWS[0], ("17x", "Oops")])
    assert done["added"] == 1 and done["skipped"] == ["17x"]
    assert done["problems"][0].startswith("Row 2 (17x)")
    assert done["rejected"][0][0] == "17x"
    done = hsn_import.load([("1701", "")])
    assert done["skipped"] == ["1701"] and done["added"] == 0


def test_codes_of_the_wrong_length_are_left_out_and_named():
    done = hsn_import.load([ROWS[0], ("30559", "Fish, dried"), ("3074330", "Molluscs")])
    assert done["added"] == 1 and done["skipped"] == ["30559", "3074330"]
    assert done["problems"] == [
        "30559: not 2, 4, 6 or 8 digits",
        "3074330: not 2, 4, 6 or 8 digits",
    ]
    assert not HsnCode.objects.filter(hsn_code="30559").exists()


def test_the_command_reads_a_csv_and_skips_headings(tmp_path):
    f = tmp_path / "hsn.csv"
    f.write_text('HSN,Description\n1701,"Sugar, cane or beet"\n0910,Spices\n,\n', encoding="utf-8")
    out = io.StringIO()
    call_command("import_hsn", str(f), stdout=out)
    assert "2 added" in out.getvalue()
    assert HsnCode.objects.get(hsn_code="1701").description == "Sugar, cane or beet"
    empty = tmp_path / "empty.csv"
    empty.write_text("HSN,Description\n", encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("import_hsn", str(empty))


def test_tenants_cannot_change_the_list(accountant, viewer, company):
    hsn_import.load(ROWS)
    assert call(viewer, "get", "hsn/").status_code == 200
    assert (
        call(accountant, "post", "hsn/", {"hsn_code": "9999", "description": "Mine"}).status_code
        == 405
    )
    assert HsnCode.objects.count() == 4
