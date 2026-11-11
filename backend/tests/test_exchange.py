"""Import, export and print on masters screens (core/exchange.py), tried on
Units, the first master to use it."""

import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from openpyxl import Workbook, load_workbook
from rest_framework import serializers

from accounts.models import Role, User
from audit.models import AuditEntry
from core import exchange
from core.models import Unit
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def _client(alpha, email, role, extra=()):
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=email.split("@")[0])
        user.roles.set(Role.objects.filter(code=role))
        if extra:
            custom = Role.objects.create(code=f"x-{role}", name=f"X {role}", permissions=extra)
            user.roles.add(custom)
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


def export(client, fmt="json", **params):
    query = "&".join(f"{k}={v}" for k, v in {"as": fmt, **params}.items())
    return client.get(f"/api/v1/exchange/units/?{query}", HTTP_HOST=HOST)


def upload(client, rows, commit=False, name="units.csv"):
    if name.endswith(".xlsx"):
        wb = Workbook()
        for row in rows:
            wb.active.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()
    else:
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        content = buf.getvalue().encode("utf-8-sig")
    return client.post(
        "/api/v1/exchange/units/import/",
        {"file": SimpleUploadedFile(name, content), "commit": "1" if commit else "0"},
        HTTP_HOST=HOST,
    )


def unit_names(alpha):
    with use_tenant(alpha):
        return set(Unit.objects.values_list("name", flat=True))


HEADER = ["ID", "Name", "Short name", "GST unit code", "Whole numbers only", "Active"]


def test_columns_follow_the_form_fields():
    cols = exchange.MASTERS["units"].columns()
    assert [c.label for c in cols] == HEADER[1:]
    assert [c.kind for c in cols][3:] == ["yesno", "yesno"]


def test_a_field_the_framework_cannot_hold_must_be_handled():
    class Odd(serializers.Serializer):
        id = serializers.IntegerField(read_only=True)
        tags = serializers.ListField(child=serializers.CharField())

    with pytest.raises(Exception, match="tags"):
        exchange.register(
            exchange.Master("odd", "Odd", Odd, lambda ctx: [], lambda ctx, i, d: None)
        )
    assert "odd" not in exchange.MASTERS


def test_export_for_print_and_as_files(viewer, alpha):
    data = export(viewer).json()
    assert data["title"] == "Units"
    assert data["columns"] == HEADER[1:]
    kg = next(r for r in data["rows"] if r[0] == "Kilogram")
    assert kg == ["Kilogram", "kg", "KGS", "No", "Yes"]

    xlsx = export(viewer, "xlsx")
    assert xlsx["Content-Disposition"].endswith('.xlsx"')
    wb = load_workbook(io.BytesIO(xlsx.content))
    sheet = list(wb.worksheets[0].values)
    assert list(sheet[0]) == HEADER
    assert len(sheet) == 1 + len(data["rows"])
    assert wb.sheetnames[1] == "How to fill"

    text = export(viewer, "csv").content.decode("utf-8-sig")
    assert text.splitlines()[0] == ",".join(HEADER)

    blank = load_workbook(io.BytesIO(export(viewer, "xlsx", blank=1).content))
    assert len(list(blank.worksheets[0].values)) == 1


def test_only_import_permission_may_import(viewer, accountant, alpha):
    rows = [HEADER[1:], ["Drum", "drm", "DRM", "Yes", "Yes"]]
    assert upload(viewer, rows).status_code == 403
    assert upload(accountant, rows).status_code == 403  # can edit, not import
    allowed = _client(alpha, "imp@x.in", "accountant", extra=["masters.import"])
    assert upload(allowed, rows, commit=True).json()["saved"] is True
    assert "Drum" in unit_names(alpha)


def test_check_first_then_import(owner, alpha):
    rows = [HEADER[1:], ["Drum", "drm", "DRM", "Yes", "Yes"], ["Box", "box", "box", "", ""]]
    checked = upload(owner, rows).json()
    assert checked["errors"] == []
    assert (checked["new"], checked["saved"]) == (2, False)
    assert not {"Drum", "Box"} & unit_names(alpha)  # a check saves nothing

    done = upload(owner, rows, commit=True, name="units.xlsx").json()
    assert done["saved"] is True
    assert {"Drum", "Box"} <= unit_names(alpha)
    with use_tenant(alpha):
        box = Unit.objects.get(name="Box")
        assert box.gst_code == "BOX" and box.whole_numbers is False
        logged = AuditEntry.objects.filter(record_type="unit", record_id=box.pk)
        assert logged.count() == 1


def test_any_bad_row_saves_nothing_and_says_why(owner, alpha):
    rows = [
        HEADER[1:],
        ["Drum", "drm", "DRM", "Yes", "Yes"],
        ["Carton", "c2", "CTN", "Yes", "Yes"],  # name clash, the form's own check
        ["Jar", "jar", "XYZ", "maybe", "Yes"],  # bad code, bad yes/no
        ["Drum", "drm2", "DRM", "Yes", "Yes"],  # clashes with row 2 of the same file
    ]
    out = upload(owner, rows, commit=True).json()
    assert out["saved"] is False
    by_row = {e["row"]: e["messages"] for e in out["errors"]}
    assert set(by_row) == {3, 4, 5}
    assert by_row[3] == ['Name: There is already a unit with the name "Carton".']
    assert any(m.startswith("GST unit code:") for m in by_row[4])
    assert any(m.startswith("Whole numbers only: write Yes or No") for m in by_row[4])
    assert "Drum" not in unit_names(alpha)


def test_change_by_id_and_report_unchanged(owner, alpha):
    exported = export(owner).json()
    with use_tenant(alpha):
        kg = Unit.objects.get(name="Kilogram")
        nos = Unit.objects.get(name="Nos")
    rows = [
        HEADER,
        [str(kg.pk), "Kilogram", "kgs", "KGS", "No", "Yes"],
        [str(nos.pk), "Nos", "nos", "NOS", "Yes", "Yes"],
        ["99999", "Ghost", "gh", "OTH", "No", "Yes"],
    ]
    out = upload(owner, rows).json()
    assert out["errors"] == [
        {
            "row": 4,
            "messages": [
                "ID: there is no unit with ID 99999. Leave the ID empty to add a new one."
            ],
        }
    ]
    out = upload(owner, rows[:3], commit=True).json()
    assert (out["changed"], out["same"], out["saved"]) == (1, 1, True)
    with use_tenant(alpha):
        assert Unit.objects.get(pk=kg.pk).short_name == "kgs"
    assert len(export(owner).json()["rows"]) == len(exported["rows"])


def test_unknown_columns_are_refused(owner):
    res = upload(owner, [["Name", "Colour"], ["Drum", "red"]])
    assert res.status_code == 400
    assert "Colour" in res.json()["detail"]
