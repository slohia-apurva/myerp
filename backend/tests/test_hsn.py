"""HSN codes: the shared list, its import and the picker search."""

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
    {"hsn_code": "1701", "description": "Cane or beet sugar and chemically pure sucrose"},
    {"hsn_code": "170199", "description": "Jaggery and other sugar, in solid form"},
    {
        "hsn_code": "0910",
        "description": "Ginger, saffron, turmeric (curcuma), thyme, bay leaves, curry",
    },
    {"hsn_code": "4819", "description": "Cartons, boxes, cases of corrugated paper"},
]


def results(client, query=""):
    return call(client, "get", f"hsn/?{query}").json()["results"]


def test_import_adds_updates_and_searches(accountant, company):
    done = call(accountant, "post", "hsn/import/", {"rows": ROWS})
    assert done.status_code == 200, done.json()
    assert done.json() == {"added": 4, "updated": 0, "unchanged": 0}

    again = call(
        accountant,
        "post",
        "hsn/import/",
        {"rows": [*ROWS[:2], {**ROWS[2], "description": "Turmeric and spices"}]},
    )
    assert again.json() == {"added": 0, "updated": 1, "unchanged": 2}

    by_code = [r["hsn_code"] for r in results(accountant, "q=17")]
    assert by_code == ["1701", "170199"]
    assert [r["hsn_code"] for r in results(accountant, "q=turmeric")] == ["0910"]
    assert [
        r["hsn_code"] for r in results(accountant, "q=carton%20ginger")
    ] == []  # every word must match
    assert [r["hsn_code"] for r in results(accountant, "q=carton%20corrugated")] == ["4819"]
    assert call(accountant, "get", "hsn/").json()["total"] == 4


def test_a_bad_row_stops_the_whole_import(accountant, company):
    bad = call(
        accountant,
        "post",
        "hsn/import/",
        {"rows": [ROWS[0], {"hsn_code": "17x", "description": "Oops"}]},
    )
    assert bad.status_code == 400 and "Row 2" in bad.json()["rows"][0]
    assert call(accountant, "get", "hsn/").json()["total"] == 0
    blank = call(
        accountant, "post", "hsn/import/", {"rows": [{"hsn_code": "1701", "description": " "}]}
    )
    assert blank.status_code == 400
    assert call(accountant, "post", "hsn/import/", {"rows": []}).status_code == 400


def test_add_edit_and_disable_one_code(accountant, company):
    made = call(accountant, "post", "hsn/", {"hsn_code": "1701", "description": "Sugar"})
    assert made.status_code == 201, made.json()
    code = made.json()
    assert (
        call(accountant, "post", "hsn/", {"hsn_code": "1701", "description": "Again"}).status_code
        == 400
    )
    assert (
        call(
            accountant, "post", "hsn/", {"hsn_code": "12345", "description": "Five digits"}
        ).status_code
        == 400
    )
    assert call(accountant, "patch", f"hsn/{code['id']}/", {"hsn_code": "1702"}).status_code == 400
    assert (
        call(
            accountant, "patch", f"hsn/{code['id']}/", {"description": "Sugar, all kinds"}
        ).status_code
        == 200
    )
    assert call(accountant, "patch", f"hsn/{code['id']}/", {"is_active": False}).status_code == 200
    assert results(accountant, "active=1&q=1701") == []
    assert len(results(accountant, "q=1701")) == 1
    entries = call(accountant, "get", f"audit/?type=hsn&id={code['id']}").json()["entries"]
    assert entries[-1]["action"] == "create"


def test_viewer_may_search_but_not_change(viewer, accountant, company):
    assert call(viewer, "get", "hsn/").status_code == 200
    assert (
        call(viewer, "post", "hsn/", {"hsn_code": "1701", "description": "Sugar"}).status_code
        == 403
    )
    assert call(viewer, "post", "hsn/import/", {"rows": ROWS}).status_code == 403
