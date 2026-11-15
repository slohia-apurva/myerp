"""Batches: lots of batch-tracked items, numbered per item."""

import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HOST = "alpha.localhost"


def _client(alpha, email, role):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=email.split("@")[0])
        user.roles.set(Role.objects.filter(code=role))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def accountant(alpha):
    return _client(alpha, "accounts@x.in", "accountant")


@pytest.fixture
def owner(alpha):
    return _client(alpha, "owner@x.in", "owner")


@pytest.fixture
def viewer(alpha):
    return _client(alpha, "view@x.in", "viewer")


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


@pytest.fixture
def brand(accountant, company):
    return call(accountant, "post", "brands/", {"name": "Apurvam"}).json()["id"]


def item(client, brand, name, **extra):
    kg = next(u["id"] for u in call(client, "get", "units/").json() if u["name"] == "Kilogram")
    data = {"name": name, "stock_unit": kg, "brand": brand, "hsn": "0902", **extra}
    made = call(client, "post", "items/", data)
    assert made.status_code == 201, made.json()
    return made.json()["id"]


@pytest.fixture
def tea(accountant, brand):
    return item(
        accountant,
        brand,
        "Tulsi green tea",
        batch_tracked=True,
        best_before_value=24,
        best_before_unit="months",
    )


@pytest.fixture
def coffee(accountant, brand):
    return item(accountant, brand, "Filter coffee", batch_tracked=True)


def test_two_items_may_share_a_batch_number(accountant, tea, coffee):
    # Sidharth, 2026-11-15: item A and item B can both have batch 1234.
    a = call(accountant, "post", "batches/", {"item": tea, "number": "1234"})
    b = call(accountant, "post", "batches/", {"item": coffee, "number": "1234"})
    assert a.status_code == 201, a.json()
    assert b.status_code == 201, b.json()


def test_one_item_cannot_have_the_same_batch_twice(accountant, tea):
    call(accountant, "post", "batches/", {"item": tea, "number": "26K09D"})
    again = call(accountant, "post", "batches/", {"item": tea, "number": " 26k09d "})
    assert again.status_code == 400
    assert "already has a batch" in str(again.json())
    assert again.json()["existing"]["kind"] == "batch"


def test_expiry_comes_from_the_items_best_before(accountant, tea):
    made = call(
        accountant, "post", "batches/", {"item": tea, "number": "B1", "mfg_date": "2026-11-30"}
    )
    assert made.json()["expiry_date"] == "2028-11-30"
    given = call(
        accountant,
        "post",
        "batches/",
        {"item": tea, "number": "B2", "mfg_date": "2026-11-01", "expiry_date": "2027-06-30"},
    )
    assert given.json()["expiry_date"] == "2027-06-30"


def test_expiry_cannot_be_before_mfg(accountant, tea):
    bad = call(
        accountant,
        "post",
        "batches/",
        {"item": tea, "number": "B1", "mfg_date": "2026-11-01", "expiry_date": "2026-10-01"},
    )
    assert bad.status_code == 400 and "expiry_date" in bad.json()


def test_only_batch_tracked_items_have_batches(accountant, brand):
    plain = item(accountant, brand, "Jute bag")
    bad = call(accountant, "post", "batches/", {"item": plain, "number": "X1"})
    assert bad.status_code == 400 and "not batch-tracked" in str(bad.json())


def test_status_edit_and_list_by_item(accountant, viewer, tea, coffee):
    made = call(accountant, "post", "batches/", {"item": tea, "number": "B1"}).json()
    assert made["status"] == "released"
    call(accountant, "post", "batches/", {"item": coffee, "number": "C1"})
    held = call(accountant, "patch", f"batches/{made['id']}/", {"status": "quarantine"})
    assert held.json()["status_label"] == "Quarantine"
    rows = call(viewer, "get", f"batches/?item={tea}").json()
    assert [r["number"] for r in rows] == ["B1"]
    assert call(viewer, "post", "batches/", {"item": tea, "number": "B9"}).status_code == 403


def test_batches_export_and_import(owner, tea):
    accountant = owner
    call(accountant, "post", "batches/", {"item": tea, "number": "B1"})
    out = accountant.get("/api/v1/exchange/batches/?as=csv", HTTP_HOST=HOST)
    assert out.status_code == 200
    rows = list(csv.reader(io.StringIO(out.content.decode("utf-8-sig"))))
    head = rows[0]
    new = dict.fromkeys(head, "")
    new.update({"Item": "Tulsi green tea", head[head.index("Item") + 1]: "B2"})
    for label in head:
        if label.lower().startswith("mfg"):
            new[label] = "2026-01-15"
        if label.lower() in ("active", "is active"):
            new[label] = "Yes"
        if label == "Status":
            new[label] = "Released"
    buf = io.StringIO()
    csv.writer(buf).writerows([head, [new[h] for h in head]])
    res = accountant.post(
        "/api/v1/exchange/batches/import/",
        {"file": SimpleUploadedFile("b.csv", buf.getvalue().encode()), "commit": "1"},
        HTTP_HOST=HOST,
    )
    assert res.status_code == 200, res.json()
    assert res.json()["new"] == 1, res.json()
    two = call(accountant, "get", f"batches/?item={tea}").json()
    assert {r["number"]: r["expiry_date"] for r in two}["B2"] == "2028-01-15"
