"""Fiscal years and monthly periods: rules, locking and the posting check."""

from datetime import date

import pytest
from django.test import Client
from rest_framework.exceptions import ValidationError

from accounts.models import Role, User
from audit.models import AuditEntry
from core import fiscal
from core.companies import create_company
from core.models import FiscalYear
from tenancy.context import use_tenant

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


def years(client, company):
    return call(client, "get", f"companies/{company}/fiscal-years/").json()


def test_date_helpers():
    assert fiscal.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert fiscal.add_months(date(2026, 4, 1), 12) == date(2027, 4, 1)
    assert fiscal.month_end(date(2028, 2, 10)) == date(2028, 2, 29)
    assert fiscal.year_name(date(2026, 4, 1), date(2027, 3, 31)) == "2026-27"
    assert fiscal.year_name(date(2026, 1, 1), date(2026, 12, 31)) == "2026"


def test_a_new_company_gets_the_years_up_to_today(owner, company):
    rows = years(owner, company)
    assert rows, "the year holding today must exist"
    today = date.today()
    holding = [
        y
        for y in rows
        if date.fromisoformat(y["start_date"]) <= today <= date.fromisoformat(y["end_date"])
    ]
    assert len(holding) == 1
    assert len(holding[0]["periods"]) == 12


def test_add_a_year_and_the_rules(owner, company):
    last = years(owner, company)[0]
    start = fiscal.add_months(date.fromisoformat(last["start_date"]), 12)
    end = fiscal.month_end(fiscal.add_months(start, 11))
    made = call(
        owner,
        "post",
        f"companies/{company}/fiscal-years/",
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    assert made.status_code == 201, made.json()
    assert made.json()["name"] == fiscal.year_name(start, end)
    assert len(made.json()["periods"]) == 12

    def bad(start_date, end_date):
        r = call(
            owner,
            "post",
            f"companies/{company}/fiscal-years/",
            {"start_date": start_date, "end_date": end_date},
        )
        assert r.status_code == 400
        return str(r.json())

    assert "overlap" in bad(start.isoformat(), end.isoformat())
    far = fiscal.add_months(start, 36)
    assert "1st of a month" in bad(far.replace(day=2).isoformat(), "2099-03-31")
    assert "last day" in bad(far.isoformat(), "2099-03-30")
    before = fiscal.month_end(fiscal.add_months(far, -1)).isoformat()
    assert "after it starts" in bad(far.isoformat(), before)
    too_long = fiscal.month_end(fiscal.add_months(far, 20)).isoformat()
    assert "at most 18" in bad(far.isoformat(), too_long)


def test_assert_open_needs_a_year_and_an_unlocked_month(alpha, company):
    with use_tenant(alpha):
        from core.models import Company

        c = Company.objects.get(pk=company)
        period = fiscal.assert_open(c, date.today())
        assert period.start_date <= date.today() <= period.end_date
        with pytest.raises(ValidationError, match="No fiscal year"):
            fiscal.assert_open(c, date(1990, 1, 1))
        period.is_locked = True
        period.save()
        with pytest.raises(ValidationError, match="is locked"):
            fiscal.assert_open(c, date.today())
        period.year.is_active = False
        period.year.save()
        period.is_locked = False
        period.save()
        with pytest.raises(ValidationError, match="No fiscal year"):
            fiscal.assert_open(c, date.today())


def test_lock_and_unlock_a_month(accountant, owner, company, alpha):
    period = years(owner, company)[0]["periods"][0]
    locked = call(accountant, "patch", f"fiscal-periods/{period['id']}/", {"is_locked": True})
    assert locked.status_code == 200
    assert locked.json()["periods"][0]["is_locked"] is True
    refused = call(accountant, "patch", f"fiscal-periods/{period['id']}/", {"is_locked": False})
    assert refused.status_code == 403
    done = call(owner, "patch", f"fiscal-periods/{period['id']}/", {"is_locked": False})
    assert done.status_code == 200 and done.json()["periods"][0]["is_locked"] is False
    with use_tenant(alpha):
        entries = AuditEntry.objects.filter(record_type="fiscal_year").order_by("pk")
        texts = [str(e.changes) for e in entries]
        assert any("Locked months" in t for t in texts)


def test_two_years_cannot_share_a_name(owner, company):
    first = years(owner, company)[0]
    start = fiscal.add_months(date.fromisoformat(first["start_date"]), 12)
    made = call(
        owner,
        "post",
        f"companies/{company}/fiscal-years/",
        {
            "start_date": start.isoformat(),
            "end_date": fiscal.month_end(fiscal.add_months(start, 11)).isoformat(),
        },
    ).json()
    r = call(owner, "patch", f"fiscal-years/{made['id']}/", {"name": f"  {first['name'].lower()} "})
    assert r.status_code == 400
    assert r.json()["existing"]["kind"] == "fiscal_year"
    assert str(r.json()["existing"]["id"]) == str(first["id"])


def test_dates_cannot_change_while_a_month_is_locked(owner, company):
    year = years(owner, company)[0]
    call(owner, "patch", f"fiscal-periods/{year['periods'][0]['id']}/", {"is_locked": True})
    end = fiscal.month_end(fiscal.add_months(date.fromisoformat(year["start_date"]), 10))
    bad = call(owner, "patch", f"fiscal-years/{year['id']}/", {"end_date": end.isoformat()})
    assert bad.status_code == 400 and "Unlock" in str(bad.json())
    ok = call(owner, "patch", f"fiscal-years/{year['id']}/", {"name": "FY renamed"})
    assert ok.status_code == 200 and ok.json()["name"] == "FY renamed"


def test_changing_dates_rebuilds_the_months(owner, company):
    year = years(owner, company)[0]
    end = fiscal.month_end(fiscal.add_months(date.fromisoformat(year["start_date"]), 10))
    done = call(owner, "patch", f"fiscal-years/{year['id']}/", {"end_date": end.isoformat()})
    assert done.status_code == 200, done.json()
    assert len(done.json()["periods"]) == 11


def test_viewers_read_but_cannot_change(viewer, owner, company):
    assert call(viewer, "get", f"companies/{company}/fiscal-years/").status_code == 200
    year = years(owner, company)[0]
    r = call(viewer, "patch", f"fiscal-years/{year['id']}/", {"name": "x"})
    assert r.status_code == 403


def test_existing_companies_are_seeded_by_the_helper(alpha, company):
    with use_tenant(alpha):
        from core.models import Company

        c = Company.objects.get(pk=company)
        FiscalYear.objects.filter(company=c).delete()
        fiscal.ensure_years(c, today=date(2027, 5, 1))
        assert FiscalYear.objects.filter(company=c).exists()
        before = FiscalYear.objects.filter(company=c).count()
        fiscal.ensure_years(c, today=date(2027, 5, 1))  # again: nothing doubles
        assert FiscalYear.objects.filter(company=c).count() == before
