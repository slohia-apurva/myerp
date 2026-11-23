"""The Owner's reset tool: three levels, guarded."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core import data_reset
from core.companies import create_company
from core.models import Branch, Certificate, Ledger, LedgerGroup, NumberSeries, Party
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HOST = "alpha.localhost"


def login(alpha, email, role):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=role.title())
        user.roles.set(Role.objects.filter(code=role))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def owner(alpha):
    return login(alpha, "owner@x.in", "owner")


@pytest.fixture
def accountant(alpha):
    return login(alpha, "accounts@x.in", "accountant")


@pytest.fixture
def on(settings):
    settings.ALLOW_DATA_RESET = True


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def group(client, company, name):
    detail = call(client, "get", f"companies/{company}/").json()
    return next(g["id"] for g in detail["ledger_groups"] if g["name"] == name)


def populate(client, company, alpha):
    """A customer with an opening balance, a plain ledger, own group, branch,
    licence and an item: what people add in a trial run."""
    debtors = group(client, company, "Sundry Debtors")
    made = call(
        client,
        "post",
        f"companies/{company}/ledgers/",
        {
            "name": "Fresh Mart",
            "group": debtors,
            "opening_amount": "100",
            "opening_side": "dr",
            "opening_bills": [
                {"ref": "B1", "bill_date": "2026-03-10", "amount": "100", "side": "dr"}
            ],
        },
    )
    assert made.status_code == 201, made.json()
    own = call(
        client,
        "post",
        f"companies/{company}/ledger-groups/",
        {"name": "My group", "parent": group(client, company, "Current Assets")},
    )
    assert own.status_code == 201, own.json()
    assert (
        call(
            client, "post", f"companies/{company}/branches/", {"name": "Pune", "state_code": "27"}
        ).status_code
        == 201
    )
    units = {u["name"]: u["id"] for u in call(client, "get", "units/").json()}
    item = call(
        client,
        "post",
        "items/",
        {"name": "Jaggery", "stock_unit": units["Packet"], "units": [], "hsn": "0902"},
    )
    assert item.status_code == 201, item.json()
    custom = call(
        client, "post", "units/", {"name": "Barrel", "short_name": "brl", "gst_code": "DRM"}
    )
    assert custom.status_code == 201, custom.json()


def reset(client, level, company=None, confirm=""):
    return call(
        client, "post", "admin/reset/", {"level": level, "company": company, "confirm": confirm}
    )


def test_only_an_owner_may_use_it(accountant, owner, on, company):
    assert call(accountant, "get", "admin/reset/").status_code == 403
    assert reset(accountant, "masters", company, "Apurvam Organics LLP").status_code == 403
    assert call(owner, "get", "admin/reset/").json()["allowed"] is True


def test_refused_unless_switched_on(owner, company, settings):
    settings.ALLOW_DATA_RESET = False
    assert call(owner, "get", "admin/reset/").json()["allowed"] is False
    refused = reset(owner, "masters", company, "Apurvam Organics LLP")
    assert refused.status_code == 403
    assert "switched off" in str(refused.json())


def test_the_name_must_be_typed(owner, on, company):
    assert reset(owner, "masters", company, "apurvam").status_code == 400
    assert reset(owner, "masters", company, "").status_code == 400
    assert reset(owner, "nonsense", company, "x").status_code == 400
    assert reset(owner, "masters", None, "x").status_code == 400


def test_entries_level_keeps_masters(owner, on, company, alpha):
    populate(owner, company, alpha)
    done = reset(owner, "entries", company, "Apurvam Organics LLP")
    assert done.status_code == 200, done.json()
    with use_tenant(alpha):
        assert Ledger.objects.filter(name="Fresh Mart").exists()
        assert Branch.objects.filter(name="Pune").exists()


def test_masters_level_clears_one_company_and_restores_the_start(owner, on, company, alpha):
    populate(owner, company, alpha)
    with use_tenant(alpha):
        other = create_company(name="Other Co", state_code="27").pk
    other_debtors = group(owner, other, "Sundry Debtors")
    call(
        owner,
        "post",
        f"companies/{other}/ledgers/",
        {"name": "Their ledger", "group": other_debtors},
    )
    call(owner, "post", f"companies/{other}/branches/", {"name": "Nashik", "state_code": "27"})

    seen = call(owner, "get", f"admin/reset/?level=masters&company={company}").json()["preview"]
    counts = {r["label"]: r["count"] for r in seen}
    assert counts["Ledgers"] >= 2 and counts["Customers and suppliers"] == 1

    done = reset(owner, "masters", company, "Apurvam Organics LLP")
    assert done.status_code == 200, done.json()
    body = done.json()
    assert body["filename"].startswith("myerp-backup-company-")
    assert any(o["model"] == "core.ledger" for o in body["backup"])
    with use_tenant(alpha):
        assert not Ledger.objects.filter(company=company).exclude(name="Cash").exists()
        assert Ledger.objects.filter(company=company, name="Cash").exists()  # starting ledger back
        assert not LedgerGroup.objects.filter(company=company, is_standard=False).exists()
        assert LedgerGroup.objects.filter(company=company, code="sundry_debtors").exists()
        assert list(Branch.objects.filter(company=company).values_list("name", flat=True)) == [
            "Head office"
        ]
        assert not Party.objects.filter(name="Fresh Mart").exists()
        # The other company and the shared items are untouched.
        assert Ledger.objects.filter(company=other, name="Their ledger").exists()
        assert Branch.objects.filter(company=other, name="Nashik").exists()
    items = call(owner, "get", "items/").json()
    assert [i["name"] for i in items] == ["Jaggery"]
    log = call(owner, "get", f"audit/?company={company}").json()["entries"]
    assert any(c["label"] == "Data reset" for e in log for c in e["changes"])


def test_all_level_blanks_the_group_but_keeps_companies_and_people(owner, on, company, alpha):
    populate(owner, company, alpha)
    with use_tenant(alpha):
        NumberSeries.objects.filter(key="item").update(last=5)
    assert reset(owner, "all", None, "reset all data").status_code == 400
    done = reset(owner, "all", None, data_reset.ALL_PHRASE)
    assert done.status_code == 200, done.json()
    assert call(owner, "get", "items/").json() == []
    names = {u["name"] for u in call(owner, "get", "units/").json()}
    assert "Barrel" not in names and "Packet" in names
    with use_tenant(alpha):
        assert Ledger.objects.filter(company=company, name="Cash").exists()
        assert not Ledger.objects.filter(name="Fresh Mart").exists()
        assert User.objects.filter(email="owner@x.in").exists()
        assert not Certificate.objects.exists()
        assert NumberSeries.objects.get(key="item").last == 0
    assert call(owner, "get", "companies/").status_code == 200


def test_entry_modules_can_plug_in(owner, on, company, alpha):
    deleted = []
    data_reset.register_entries(
        "Test vouchers", lambda scope: 3, lambda scope: deleted.append(scope)
    )
    try:
        seen = call(owner, "get", f"admin/reset/?level=entries&company={company}").json()["preview"]
        assert {"label": "Test vouchers", "count": 3} in seen
        assert reset(owner, "entries", company, "Apurvam Organics LLP").status_code == 200
        assert len(deleted) == 1 and deleted[0].pk == company
    finally:
        data_reset._ENTRIES.pop()
