"""Print and PDF: the columnar report every list screen offers (core/printout.py)."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core import printout
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


@pytest.fixture
def viewer(alpha):
    with use_tenant(alpha):
        user = User.objects.create_user("view@x.in", full_name="View")
        user.roles.set(Role.objects.filter(code="viewer"))
        client = Client()
        client.force_login(user)
    return client


def test_amounts_are_grouped_the_indian_way():
    assert printout.indian("12345678.50") == "1,23,45,678.50"
    assert printout.indian("-1000") == "-1,000"
    assert printout.indian("999") == "999"
    assert printout.indian("ABC-1") == "ABC-1"


def test_number_columns_sit_on_the_right():
    assert printout.numeric(["1,000.00 Dr", "", "—", "25"])
    assert not printout.numeric(["10", "Kilogram"])
    assert not printout.numeric(["", "—"])


def test_pdf_of_a_master_list(viewer):
    response = viewer.get("/api/v1/exchange/units/?as=pdf", HTTP_HOST=HOST)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].endswith('.pdf"')
    assert response.content.startswith(b"%PDF")


def test_pdf_of_what_a_screen_shows(viewer):
    body = {
        "title": "Users",
        "sheets": [
            {
                "title": "Users",
                "columns": ["Name", "Roles"],
                "rows": [["Asha · asha@x.in", "Owner"]],
            },
            {"title": "Empty", "columns": ["Name"], "rows": []},
        ],
    }
    response = viewer.post(
        "/api/v1/print/pdf/", body, content_type="application/json", HTTP_HOST=HOST
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert 'filename="users-' in response["Content-Disposition"]


def test_a_pdf_needs_a_table(viewer):
    for sheets in (None, [], [{"columns": [], "rows": []}]):
        response = viewer.post(
            "/api/v1/print/pdf/",
            {"title": "X", "sheets": sheets},
            content_type="application/json",
            HTTP_HOST=HOST,
        )
        assert response.status_code == 400


def test_signed_out_gets_no_pdf():
    response = Client().post(
        "/api/v1/print/pdf/",
        {"title": "X", "sheets": []},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert response.status_code in (401, 403)


def test_excel_of_a_report_keeps_numbers_as_numbers(viewer):
    import io

    from openpyxl import load_workbook

    body = {
        "title": "Pending Purchase Orders",
        "scope": "Apurvam Organics LLP",
        "sheets": [
            {
                "title": "Pending Purchase Orders",
                "columns": ["PO No", "Pending Value ₹"],
                "rows": [["AO/PO/26-27/00412", "2,31,860.40"], ["AO/PO/26-27/00431", "9"]],
                "text": [0],
            }
        ],
    }
    response = viewer.post(
        "/api/v1/print/xlsx/", body, content_type="application/json", HTTP_HOST=HOST
    )
    assert response.status_code == 200
    assert 'filename="pending-purchase-orders-' in response["Content-Disposition"]
    ws = load_workbook(io.BytesIO(response.content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0][0] == "Pending Purchase Orders"
    assert rows[1][0] == "Apurvam Organics LLP"
    assert rows[3] == ["PO No", "Pending Value ₹"]
    assert rows[4] == ["AO/PO/26-27/00412", 231860.4]
    assert rows[5] == ["AO/PO/26-27/00431", 9]
