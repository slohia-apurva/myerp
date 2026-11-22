"""Numbering: master numbers and document series that restart each fiscal year."""

from datetime import date

import pytest
from django.test import Client
from rest_framework.exceptions import ValidationError

from accounts.models import Role, User
from audit.models import AuditEntry
from core import fiscal, numbering
from core.companies import create_company
from core.models import Company, FiscalYear, NumberCounter, NumberSeries
from tenancy.context import tenant_atomic, use_tenant

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
def viewer(alpha):
    return _client(alpha, "view@x.in", "viewer")


@pytest.fixture
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27", abbr="AO").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def screen(client, company):
    return call(client, "get", f"companies/{company}/numbering/").json()


def series(client, company, doc_type, branch=None):
    rows = screen(client, company)["formats"]
    return next(r for r in rows if r["doc_type"] == doc_type and r["branch"] == branch)


def issue(alpha, company, doc_type, day, branch=None):
    with use_tenant(alpha):
        c = Company.objects.get(pk=company)
        with tenant_atomic():
            return numbering.next_document_number(c, doc_type, day, branch)


def test_every_kind_of_document_starts_with_a_series(owner, company):
    body = screen(owner, company)
    assert [m["key"] for m in body["masters"]] == ["customer", "vendor", "item", "bom"]
    assert body["masters"][0]["next"] == "CUST-00001"
    kinds = {f["doc_type"] for f in body["formats"]}
    assert kinds == {code for code, *_ in numbering.DOCUMENT_TYPES}
    invoice = series(owner, company, "sales_invoice")
    assert invoice["prefix"] == "AO/SI/{YY}/" and invoice["example"] == "AO/SI/2627/00001"
    assert {y["name"] for y in invoice["years"]}  # a row for every fiscal year


def test_numbers_run_on_and_restart_each_fiscal_year(alpha, company):
    today = date.today()
    with use_tenant(alpha):
        c = Company.objects.get(pk=company)
        year = FiscalYear.objects.get(company=c, start_date__lte=today, end_date__gte=today)
        next_year = fiscal.create_year(
            c,
            fiscal.add_months(year.start_date, 12),
            fiscal.month_end(fiscal.add_months(year.start_date, 23)),
        )
    first = issue(alpha, company, "sales_invoice", today)
    second = issue(alpha, company, "sales_invoice", today)
    yy = numbering.short_year(year.name)
    assert first == f"AO/SI/{yy}/00001" and second == f"AO/SI/{yy}/00002"
    assert issue(alpha, company, "sales_invoice", next_year.start_date) == (
        f"AO/SI/{numbering.short_year(next_year.name)}/00001"
    )  # a new year starts again
    assert issue(alpha, company, "purchase_order", today) == f"AO/PO/{yy}/00001"
    assert issue(alpha, company, "sales_invoice", today) == f"AO/SI/{yy}/00003"


def test_a_long_company_code_gets_fewer_digits_to_fit_gst(alpha):
    with use_tenant(alpha):
        c = create_company(name="Long Name Exports", state_code="27", abbr="LNEX")
        numbering.ensure_formats(c)
        invoice = c.number_formats.get(doc_type="sales_invoice")
        order = c.number_formats.get(doc_type="purchase_order")
    assert (invoice.prefix, invoice.width) == ("LNEX/SI/{YY}/", 3)
    assert len(numbering.render(invoice.prefix, "2026-27", invoice.width, 1)) <= 16
    assert (order.prefix, order.width) == ("LNEX/PO/{YY}/", 5)  # no 16-character limit
    assert numbering.short_year("2026-27") == "2627" and numbering.short_year("2026") == "26"


def test_a_date_outside_every_year_gets_no_number(alpha, company):
    with use_tenant(alpha):
        c = Company.objects.get(pk=company)
        with pytest.raises(ValidationError, match="No fiscal year"):
            with tenant_atomic():
                numbering.next_document_number(c, "journal", date(1990, 1, 1))


def test_a_branch_can_have_its_own_series(alpha, owner, company):
    branch = call(
        owner, "post", f"companies/{company}/branches/", {"name": "Pune depot", "state_code": "27"}
    ).json()["id"]
    made = call(
        owner,
        "post",
        f"companies/{company}/numbering/formats/",
        {"doc_type": "sales_invoice", "branch": branch, "prefix": "PN/{YY}/", "width": 4},
    )
    assert made.status_code == 201, made.json()
    today = date.today()
    with use_tenant(alpha):
        pune = alpha_branch(company, branch)
    mine = issue(alpha, company, "sales_invoice", today, branch=pune)
    head = issue(alpha, company, "sales_invoice", today)
    assert mine.startswith("PN/") and mine.endswith("/0001")
    assert head.startswith("AO/SI/") and head.endswith("/00001")
    # A branch without its own series uses the company's.
    other = call(
        owner, "post", f"companies/{company}/branches/", {"name": "Surat depot", "state_code": "24"}
    ).json()["id"]
    with use_tenant(alpha):
        surat = alpha_branch(company, other)
    assert issue(alpha, company, "sales_invoice", today, branch=surat).endswith("/00002")


def alpha_branch(company, pk):
    from core.models import Branch

    return Branch.objects.get(pk=pk, company_id=company)


def test_the_rules_for_a_prefix(owner, company):
    invoice = series(owner, company, "sales_invoice")

    def patch(**body):
        return call(owner, "patch", f"numbering/formats/{invoice['id']}/", body)

    long_prefix = patch(prefix="APURVAM-EXP/{YY}/")
    assert long_prefix.status_code == 400 and "16 characters" in str(long_prefix.json())
    assert patch(prefix="SI #{YY}").status_code == 400  # a space or # is not allowed
    assert patch(width=2).status_code == 400
    clash = patch(prefix="ao/po/{YY}/")  # the purchase order's
    assert clash.status_code == 400 and "already the series" in str(clash.json())
    ok = patch(prefix="INV/{YY}/", width=5)
    assert ok.status_code == 200 and ok.json()["example"] == "INV/2627/00001"
    assert patch(width=8).status_code == 400  # 17 characters
    # A purchase order is not a GST invoice: it may be longer.
    po = series(owner, company, "purchase_order")
    long_po = call(
        owner, "patch", f"numbering/formats/{po['id']}/", {"prefix": "PURCHASE-ORDER/{FY}/"}
    )
    assert long_po.status_code == 200


def test_prefix_and_width_lock_once_a_number_is_issued(alpha, owner, company):
    issue(alpha, company, "journal", date.today())
    journal = series(owner, company, "journal")
    assert journal["in_use"] is True
    r = call(owner, "patch", f"numbering/formats/{journal['id']}/", {"prefix": "J/{YY}/"})
    assert r.status_code == 400 and "numbers already issued" in str(r.json())
    same = call(
        owner, "patch", f"numbering/formats/{journal['id']}/", {"prefix": journal["prefix"]}
    )
    assert same.status_code == 200


def test_the_last_number_can_only_go_up(alpha, owner, company):
    receipt = series(owner, company, "receipt")
    year = receipt["years"][0]["year"]
    url = f"numbering/formats/{receipt['id']}/years/{year}/"
    done = call(owner, "patch", url, {"last": 250})
    assert done.status_code == 200
    assert next(y for y in done.json()["years"] if y["year"] == year)["last"] == 250
    assert call(owner, "patch", url, {"last": 100}).status_code == 400
    assert call(owner, "patch", url, {"last": "x"}).status_code == 400
    with use_tenant(alpha):
        y = FiscalYear.objects.get(pk=year)
    day = y.start_date
    assert issue(alpha, company, "receipt", day).endswith("/00251")
    with use_tenant(alpha):
        texts = [str(e.changes) for e in AuditEntry.objects.filter(record_type="number_format")]
        assert any("Last numbers" in t for t in texts)


def test_master_numbers_change_prefix_and_move_up(alpha, owner, company):
    r = call(owner, "patch", "numbering/masters/customer/", {"prefix": "C-", "last": 40})
    assert r.status_code == 200
    assert r.json()[0]["next"] == "C-00041"
    assert call(owner, "patch", "numbering/masters/customer/", {"last": 10}).status_code == 400
    assert call(owner, "patch", "numbering/masters/nope/", {"last": 10}).status_code == 404
    with use_tenant(alpha):
        assert NumberSeries.objects.get(key="customer").last == 40


def test_viewers_read_but_cannot_change(viewer, owner, company):
    assert call(viewer, "get", f"companies/{company}/numbering/").status_code == 200
    invoice = series(owner, company, "sales_invoice")
    r = call(viewer, "patch", f"numbering/formats/{invoice['id']}/", {"width": 5})
    assert r.status_code == 403
    assert call(viewer, "patch", "numbering/masters/item/", {"last": 5}).status_code == 403


def test_entries_reset_starts_the_series_again(alpha, company):
    from core import data_reset

    issue(alpha, company, "journal", date.today())
    with use_tenant(alpha):
        c = Company.objects.get(pk=company)
        assert any(
            r["label"] == "Document numbers used" and r["count"] == 1
            for r in data_reset.preview("entries", c)
        )
        with tenant_atomic():
            for _label, _count, delete in data_reset._ENTRIES:
                delete(c)
        assert NumberCounter.objects.filter(last__gt=0).count() == 0
