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
from core.india import gstin_check_char
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
    assert [s["title"] for s in data["sheets"]] == ["Units"]
    data = data["sheets"][0]
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
    assert by_row[3] == ["Name: There is already a unit with this name."]
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
            "sheet": "Units",
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
    assert len(export(owner).json()["sheets"][0]["rows"]) == len(exported["sheets"][0]["rows"])


def test_unknown_columns_are_refused(owner):
    res = upload(owner, [["Name", "Colour"], ["Drum", "red"]])
    assert res.status_code == 400
    assert "Colour" in res.json()["detail"]


# --- Rows inside rows: credit terms' parts, items' units and GST rates ------


def book(sheets: dict[str, list[list]]) -> bytes:
    wb = Workbook()
    for n, (title, rows) in enumerate(sheets.items()):
        ws = wb.active if n == 0 else wb.create_sheet()
        ws.title = title
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def send(client, key, sheets, commit=False):
    return client.post(
        f"/api/v1/exchange/{key}/import/",
        {"file": SimpleUploadedFile("f.xlsx", book(sheets)), "commit": "1" if commit else "0"},
        HTTP_HOST=HOST,
    )


def sheets_of(client, key):
    res = client.get(f"/api/v1/exchange/{key}/?as=xlsx", HTTP_HOST=HOST)
    wb = load_workbook(io.BytesIO(res.content))
    return {ws.title: [list(r) for r in ws.values] for ws in wb.worksheets}


TERMS = ["Name", "Active", "Notes"]
PARTS = ["Credit terms", "Share (%)", "Due", "Plus days"]


def test_credit_terms_carry_their_parts_on_a_sheet(owner, alpha):
    got = sheets_of(owner, "credit-terms")
    assert list(got) == ["Credit terms", "Parts", "How to fill"]
    assert got["Credit terms"][0] == ["ID", "Name", "Active", "Notes", "When payment is due"]
    assert got["Parts"][0] == PARTS
    assert ["50% advance, 50% on delivery", 50, "On delivery", 0] in got["Parts"]

    out = send(
        owner,
        "credit-terms",
        {
            "Credit terms": [TERMS, ["30/70", "Yes", ""], ["Bad split", "Yes", ""]],
            "Parts": [
                PARTS,
                ["30/70", "30", "With the order (advance)", "0"],
                ["30/70", "70", "bill", "30"],
                ["Bad split", "60", "On delivery", "0"],
                ["Bad split", "30", "Sometime", "0"],
                ["Nobody", "100", "bill", "0"],
            ],
        },
        commit=True,
    ).json()
    assert out["saved"] is False
    where = {(e["sheet"], e["row"]): e["messages"] for e in out["errors"]}
    assert where[("Credit terms", 3)] == ["Parts: The parts add up to 60%; make them 100%."]
    assert where[("Parts", 5)][0].startswith("Due: 'Sometime' is not one of")
    assert where[("Parts", 6)][0].startswith("Credit terms: 'nobody' is not in the Credit terms")

    out = send(
        owner,
        "credit-terms",
        {
            "Credit terms": [TERMS, ["30/70", "Yes", ""]],
            "Parts": [PARTS, ["30/70", "30", "order", "0"], ["30/70", "70", "bill", "30"]],
        },
        commit=True,
    ).json()
    assert out["saved"] is True
    terms = owner.get("/api/v1/credit-terms/", HTTP_HOST=HOST).json()
    term = next(t for t in terms if t["name"] == "30/70")
    assert term["summary"] == "30% advance with the order, 70% 30 days after the bill"


def test_leaving_out_a_child_sheet_keeps_those_rows(owner, alpha):
    got = sheets_of(owner, "credit-terms")
    row = next(r for r in got["Credit terms"] if r[1] == "30 days")
    out = send(
        owner,
        "credit-terms",
        {"Credit terms": [got["Credit terms"][0][:4], [row[0], "30 days", "Yes", "Usual"]]},
        commit=True,
    ).json()
    assert (out["changed"], out["saved"]) == (1, True)
    terms = owner.get("/api/v1/credit-terms/", HTTP_HOST=HOST).json()
    term = next(t for t in terms if t["name"] == "30 days")
    assert term["notes"] == "Usual" and len(term["parts"]) == 1


ITEMS = ["Name", "Type", "Default unit (stock unit)", "HSN"]
UNITS = ["Item", "Unit", "Contains how many", "Of", "Barcode", "Used for"]
RATES = ["Item", "From", "GST rate (%)"]


def test_items_with_units_and_gst_rates(owner, alpha):
    sheets = {
        "Items": [ITEMS, ["Ghee 500 ml", "Goods", "pkt", "0405"]],
        "Units of measure": [
            UNITS,
            ["Ghee 500 ml", "Packet", "", "", "8901234500011", "Sales, Stock"],
            ["Ghee 500 ml", "Carton", "24", "Packet", "", "Purchase"],
            ["Ghee 500 ml", "Crate", "2", "Carton", "", ""],
        ],
        "GST rates": [
            RATES,
            ["Ghee 500 ml", "01-07-2017", "12"],
            ["Ghee 500 ml", "22-09-2025", "5"],
        ],
    }
    out = send(owner, "items", sheets).json()
    assert out["errors"] == [
        {
            "sheet": "Units of measure",
            "row": 4,
            "messages": ["Unit: there is no unit called 'Crate'"],
        }
    ]
    sheets["Units of measure"].pop()
    out = send(owner, "items", sheets, commit=True).json()
    assert (out["new"], out["saved"]) == (1, True)
    item = next(
        i for i in owner.get("/api/v1/items/", HTTP_HOST=HOST).json() if i["name"] == "Ghee 500 ml"
    )
    assert item["hsn"] == "0405"
    carton = next(u for u in item["units"] if u["unit_name"] == "Carton")
    assert carton["factor"] == "24.000000" and carton["used_for"] == ["purchase"]
    assert [r["rate"] for r in item["gst_rates"]] == ["12.00", "5.00"]

    # The exported file goes back in unchanged.
    got = sheets_of(owner, "items")
    assert got["Items"][0][:3] == ["ID", "Item number", "Name"]
    again = {
        t: [[("" if v is None else str(v)) for v in r] for r in rows] for t, rows in got.items()
    }
    del again["How to fill"]
    out = send(owner, "items", again, commit=True).json()
    assert out["errors"] == [] and out["changed"] == 0 and out["same"] >= 1

    # A barcode used by another item is caught as on the form.
    sheets["Items"][1][0] = "Ghee 1 litre"
    for r in sheets["Units of measure"][1:] + sheets["GST rates"][1:]:
        r[0] = "Ghee 1 litre"
    out = send(owner, "items", sheets).json()
    assert out["errors"][0]["messages"] == [
        "Units of measure: The barcode 8901234500011 is already used by another item."
    ]


# --- Ledgers: company-wise, with party details and opening bills -----------


@pytest.fixture
def company(alpha):
    from core.companies import create_company

    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def send_ledgers(client, company, sheets, commit=False):
    return client.post(
        "/api/v1/exchange/ledgers/import/",
        {
            "file": SimpleUploadedFile("l.xlsx", book(sheets)),
            "commit": "1" if commit else "0",
            "company": str(company),
        },
        HTTP_HOST=HOST,
    )


LEDGERS = ["Name", "Under group", "Opening balance (₹)", "Opening Dr/Cr", "GST type", "GSTIN"]
LEDGERS += ["State", "Credit terms", "Salesman or purchaser"]
BILLS = ["Ledger", "Bill reference", "Bill date", "Amount (₹)", "Dr/Cr"]
CONTACTS = ["Ledger", "Name", "Phone", "Main", "Types"]
FRESH_GSTIN = "29AAPFU0939F1Z" + gstin_check_char("29AAPFU0939F1Z")


def test_ledgers_with_customers_contacts_and_opening_bills(owner, company, alpha):
    assert owner.get("/api/v1/exchange/ledgers/?as=json", HTTP_HOST=HOST).status_code == 400
    sheets = {
        "Ledgers": [
            LEDGERS,
            ["Petty cash", "Cash-in-hand", "5000", "Dr", "", "", "", "", ""],
            [
                "Fresh Mart",
                "Sundry Debtors",
                "15000",
                "Dr",
                "Regular",
                FRESH_GSTIN,
                "Karnataka",
                "30 days",
                "owner@x.in",
            ],
        ],
        "Opening bills": [
            BILLS,
            ["Fresh Mart", "INV-1", "15-03-2026", "10000", "Dr"],
            ["Fresh Mart", "INV-2", "20-03-2026", "4000", "Dr"],
        ],
        "Contacts": [CONTACTS, ["Fresh Mart", "Mr Rao", "9876543210", "Yes", "Accounting, Sales"]],
    }
    out = send_ledgers(owner, company, sheets).json()
    assert out["errors"] == [
        {
            "sheet": "Ledgers",
            "row": 3,
            "messages": [
                "Opening bills: The bills add up to 14,000.00 Dr but the opening balance "
                "is 15,000.00 Dr."
            ],
        }
    ]
    sheets["Opening bills"][2][3] = "5000"
    out = send_ledgers(owner, company, sheets, commit=True).json()
    assert (out["new"], out["saved"]) == (2, True), out

    ledgers = owner.get(f"/api/v1/companies/{company}/ledgers/", HTTP_HOST=HOST).json()
    by_name = {x["name"]: x for x in ledgers}
    assert by_name["Petty cash"]["party"] is None
    fresh = by_name["Fresh Mart"]
    assert fresh["party"]["state_code"] == "29"
    assert fresh["party"]["credit_term_name"] == "30 days"
    assert fresh["party"]["customer_number"].startswith("CUST-")
    assert fresh["party"]["contacts"][0]["kinds"] == ["accounts", "sales"]
    assert [b["ref"] for b in fresh["opening_bills"]] == ["INV-1", "INV-2"]

    # The export goes back in with no change.
    res = owner.get(f"/api/v1/exchange/ledgers/?as=xlsx&company={company}", HTTP_HOST=HOST)
    wb = load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["Ledgers", "Opening bills", "Addresses", "Contacts", "How to fill"]
    again = {
        ws.title: [[("" if v is None else str(v)) for v in r] for r in ws.values]
        for ws in wb.worksheets
        if ws.title != "How to fill"
    }
    row = next(r for r in again["Ledgers"] if r[1] == "Fresh Mart")
    assert row[again["Ledgers"][0].index("State")] == "Karnataka"
    out = send_ledgers(owner, company, again, commit=True).json()
    assert out["errors"] == [] and out["changed"] == 0, out

    # A group of another company is not found by name here.
    sheets = {"Ledgers": [["Name", "Under group"], ["Odd", "No such group"]]}
    out = send_ledgers(owner, company, sheets).json()
    assert out["errors"][0]["messages"] == [
        "Under group: there is no ledger group called 'No such group'"
    ]
