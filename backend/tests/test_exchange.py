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
from core.models import SalesPerson, Unit
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

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
    rows = [HEADER[1:], ["Barrel", "brl", "DRM", "Yes", "Yes"]]
    assert upload(viewer, rows).status_code == 403
    assert upload(accountant, rows).status_code == 403  # can edit, not import
    allowed = _client(alpha, "imp@x.in", "accountant", extra=["masters.import"])
    assert upload(allowed, rows, commit=True).json()["saved"] is True
    assert "Barrel" in unit_names(alpha)


def test_check_first_then_import(owner, alpha):
    rows = [HEADER[1:], ["Barrel", "brl", "DRM", "Yes", "Yes"], ["Crate", "crt", "box", "", ""]]
    checked = upload(owner, rows).json()
    assert checked["errors"] == []
    assert (checked["new"], checked["saved"]) == (2, False)
    assert not {"Barrel", "Crate"} & unit_names(alpha)  # a check saves nothing

    done = upload(owner, rows, commit=True, name="units.xlsx").json()
    assert done["saved"] is True
    assert {"Barrel", "Crate"} <= unit_names(alpha)
    with use_tenant(alpha):
        box = Unit.objects.get(name="Crate")
        assert box.gst_code == "BOX" and box.whole_numbers is False
        logged = AuditEntry.objects.filter(record_type="unit", record_id=box.pk)
        assert logged.count() == 1


def test_any_bad_row_saves_nothing_and_says_why(owner, alpha):
    rows = [
        HEADER[1:],
        ["Barrel", "brl", "DRM", "Yes", "Yes"],
        ["Carton", "c2", "CTN", "Yes", "Yes"],  # name clash, the form's own check
        ["Jar", "jar", "XYZ", "maybe", "Yes"],  # bad code, bad yes/no
        ["Barrel", "brl2", "DRM", "Yes", "Yes"],  # clashes with row 2 of the same file
    ]
    out = upload(owner, rows, commit=True).json()
    assert out["saved"] is False
    by_row = {e["row"]: e["messages"] for e in out["errors"]}
    assert set(by_row) == {3, 4, 5}
    assert by_row[3] == ['Name: There is already a unit with the name "Carton".']
    assert any(m.startswith("GST unit code:") for m in by_row[4])
    assert any(m.startswith("Whole numbers only: write Yes or No") for m in by_row[4])
    assert "Barrel" not in unit_names(alpha)


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
    changed = [r for r in out["results"] if r["action"] == "changed"]
    assert changed[0]["changes"] == [{"field": "Short name", "old": "kg", "new": "kgs"}]
    with use_tenant(alpha):
        assert Unit.objects.get(pk=kg.pk).short_name == "kgs"
    assert len(export(owner).json()["sheets"][0]["rows"]) == len(exported["sheets"][0]["rows"])


def test_unknown_columns_are_refused(owner):
    res = upload(owner, [["Name", "Colour"], ["Barrel", "red"]])
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


ITEMS = ["Name", "Type", "Item group", "Default unit (stock unit)", "HSN", "Brand"]
UNITS = ["Item", "Unit", "Contains how many", "Of", "Barcode", "Used for"]
RATES = ["Item", "From", "GST rate (%)"]


def test_items_with_units_and_gst_rates(owner, alpha):
    sheets = {
        "Items": [ITEMS, ["Ghee 500 ml", "Goods", "Dairy", "pkt", "0405", "Apurvam"]],
        "Units of measure": [
            UNITS,
            ["Ghee 500 ml", "Packet", "", "", "8901234500011", "Sales, Stock"],
            ["Ghee 500 ml", "Carton", "24", "Packet", "", "Purchase"],
            ["Ghee 500 ml", "Crate", "2", "Carton", "", ""],
        ],
        "GST rates": [
            RATES,
            ["Ghee 500 ml", "01-07-2017", "18"],
            ["Ghee 500 ml", "22-09-2025", "5"],
        ],
    }
    owner.post(
        "/api/v1/item-groups/",
        data='{"name": "Dairy"}',
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    owner.post(
        "/api/v1/brands/",
        data='{"name": "Apurvam"}',
        content_type="application/json",
        HTTP_HOST=HOST,
    )
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
    assert [r["rate"] for r in item["gst_rates"]] == ["18.00", "5.00"]

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
        'Units of measure: The barcode 8901234500011 is already on the item "Ghee 500 ml".'
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
    with use_tenant(alpha):
        SalesPerson.objects.create(name="Ravi Kumar", is_salesman=True)
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
                "ravi kumar",
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
    assert fresh["party"]["salesman_name"] == "Ravi Kumar"
    assert fresh["party"]["customer_number"].startswith("CUST-")
    assert fresh["party"]["contacts"][0]["kinds"] == ["accounts", "sales"]
    assert [b["ref"] for b in fresh["opening_bills"]] == ["INV-1", "INV-2"]

    # The export goes back in with no change.
    res = owner.get(f"/api/v1/exchange/ledgers/?as=xlsx&company={company}", HTTP_HOST=HOST)
    wb = load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == [
        "Ledgers",
        "Opening bills",
        "Addresses",
        "Contacts",
        "Products",
        "How to fill",
    ]
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


# --- Re-importing an export: found by ID, or by the master's code ----------


def test_reimport_finds_items_by_number_and_never_changes_it(owner, alpha):
    for path, body in (("item-groups", '{"name": "Dairy"}'), ("brands", '{"name": "Apurvam"}')):
        owner.post(f"/api/v1/{path}/", data=body, content_type="application/json", HTTP_HOST=HOST)
    sheets = {"Items": [ITEMS, ["Ghee 500 ml", "Goods", "Dairy", "pkt", "0405", "Apurvam"]]}
    assert send(owner, "items", sheets, commit=True).json()["saved"] is True
    got = sheets_of(owner, "items")["Items"]
    head = got[0]
    row = ["" if v is None else str(v) for v in got[1]]
    number = row[head.index("Item number")]
    assert row[0] and number

    # The ID taken out (a file from elsewhere): the item number finds the item.
    row[0] = ""
    row[head.index("Name")] = "Ghee 500 ml jar"
    out = send(owner, "items", {"Items": [head, row]}, commit=True).json()
    assert (out["new"], out["changed"], out["saved"]) == (0, 1, True), out
    assert out["results"][0]["code"] == number
    assert {"field": "Name", "old": "Ghee 500 ml", "new": "Ghee 500 ml jar"} in out["results"][0][
        "changes"
    ]

    # With its ID, the row may not give the item another number.
    row[0] = got[1][0]
    row[head.index("Item number")] = "IT-999999"
    out = send(owner, "items", {"Items": [head, row]}).json()
    assert out["errors"][0]["messages"] == [
        f"Item number: the ID {got[1][0]} is the item {number}, and its item number never "
        f"changes. Put back {number}, or leave the ID and Item number empty to add a new item."
    ]

    # No ID and a number MyERP does not have: a new item with that number.
    row[0] = ""
    row[head.index("Name")] = "Ghee 1 litre"
    out = send(owner, "items", {"Items": [head, row]}, commit=True).json()
    assert (out["new"], out["saved"]) == (1, True), out
    with use_tenant(alpha):
        from core.models import Item

        assert Item.objects.get(item_number="IT-999999").name == "Ghee 1 litre"


def test_items_tds_section_is_filled_in_by_reimport(owner, alpha):
    """Sidharth 2026-11-26: the Items list finds the items with no TDS section, and
    the exported file, filled in, sets each item's section by its item number. The
    new number works where only one old section has it; the help sheet lists them."""
    for path, body in (("item-groups", '{"name": "Dairy"}'), ("brands", '{"name": "Apurvam"}')):
        owner.post(f"/api/v1/{path}/", data=body, content_type="application/json", HTTP_HOST=HOST)
    sheets = {
        "Items": [
            ITEMS,
            ["Ghee 500 ml", "Goods", "Dairy", "pkt", "0405", "Apurvam"],
            ["Butter 100 g", "Goods", "Dairy", "pkt", "0405", "Apurvam"],
            ["Paneer 200 g", "Goods", "Dairy", "pkt", "0405", "Apurvam"],
        ]
    }
    assert send(owner, "items", sheets, commit=True).json()["saved"] is True

    def listed(**params):
        query = "&".join(f"{k}={v}" for k, v in {"page": 1, **params}.items())
        res = owner.get(f"/api/v1/items/?{query}", HTTP_HOST=HOST)
        return sorted((i["name"], i["tds_section"]) for i in res.json()["results"])

    assert len(listed(tds="none")) == 3

    got = sheets_of(owner, "items")
    head = got["Items"][0]
    assert "TDS section" in head
    how = [r for r in got["How to fill"] if r[1] == "TDS section"]
    assert "194Q" in how[0][3] and "393(1) Sl. 8(ii)" in how[0][3], how
    name = head.index("Name")
    rows = {r[name]: ["" if v is None else str(v) for v in r] for r in got["Items"][1:]}
    col = head.index("TDS section")
    for name, section in (("Ghee 500 ml", "194q"), ("Butter 100 g", "393(1) Sl. 8(ii)")):
        rows[name][0] = ""  # by item number alone, as from a file kept elsewhere
        rows[name][col] = section
    out = send(owner, "items", {"Items": [head, rows["Ghee 500 ml"], rows["Butter 100 g"]]}, True)
    out = out.json()
    assert (out["new"], out["changed"], out["saved"]) == (0, 2, True), out
    assert listed(tds="194Q") == [("Butter 100 g", "194Q"), ("Ghee 500 ml", "194Q")]
    assert listed(tds="purchase goods") == listed(tds="sl. 8(ii)") == listed(tds="194Q")
    assert listed(tds="none") == [("Paneer 200 g", "")]
    assert [i[0] for i in listed(sort="-tds")][:2] == ["Butter 100 g", "Ghee 500 ml"]

    # A new number several old sections share, or one not in the list, is refused.
    rows["Paneer 200 g"][col] = "393(1) Sl. 6(iii)"
    out = send(owner, "items", {"Items": [head, rows["Paneer 200 g"]]}).json()
    assert "give the old number" in str(out["errors"]), out
    assert "194J(a), 194J(b), 194J(ba)" in str(out["errors"]), out
    rows["Paneer 200 g"][col] = "194Z"
    out = send(owner, "items", {"Items": [head, rows["Paneer 200 g"]]}).json()
    assert "194Z is not in the TDS sections list" in str(out["errors"]), out


def test_reimport_finds_customers_by_customer_number(owner, company, alpha):
    sheets = {
        "Ledgers": [
            LEDGERS,
            ["Fresh Mart", "Sundry Debtors", "", "", "Regular", FRESH_GSTIN, "", "", ""],
        ]
    }
    assert send_ledgers(owner, company, sheets, commit=True).json()["saved"] is True
    res = owner.get(f"/api/v1/exchange/ledgers/?as=xlsx&company={company}", HTTP_HOST=HOST)
    ws = load_workbook(io.BytesIO(res.content))["Ledgers"]
    rows = [["" if v is None else str(v) for v in r] for r in ws.values]
    head = rows[0]
    row = next(r for r in rows if r[1] == "Fresh Mart")
    number = row[head.index("Customer number")]
    assert number.startswith("CUST-")
    row[0] = ""
    row[head.index("Notes")] = "Pays on time"
    out = send_ledgers(owner, company, {"Ledgers": [head, row]}, commit=True).json()
    assert (out["new"], out["changed"], out["saved"]) == (0, 1, True), out
    assert out["results"][0]["changes"] == [{"field": "Notes", "old": "", "new": "Pays on time"}]


def test_reimport_cannot_change_locked_fields_of_a_master_in_use(owner, alpha):
    """A record in use keeps its key fields on import too, as on its form:
    the row is refused with the form's own message and nothing is saved;
    fields that stay open (the name) still change."""
    for path, body in (("item-groups", '{"name": "Dairy"}'), ("brands", '{"name": "Apurvam"}')):
        owner.post(f"/api/v1/{path}/", data=body, content_type="application/json", HTTP_HOST=HOST)
    sheets = {"Items": [ITEMS, ["Ghee 500 ml", "Goods", "Dairy", "pkt", "0405", "Apurvam"]]}
    assert send(owner, "items", sheets, commit=True).json()["saved"] is True
    with use_tenant(alpha):
        packet = Unit.objects.get(short_name__iexact="pkt")
        code = packet.gst_code

    row = [str(packet.pk), packet.name, packet.short_name, "BOX", "Yes", "Yes"]
    out = upload(owner, [HEADER, row], commit=True).json()
    assert out["saved"] is False
    assert out["errors"][0]["messages"] == [
        "GST unit code: Cannot change the GST unit code: this is in use (1 item). "
        "You can still disable it."
    ]
    with use_tenant(alpha):
        assert Unit.objects.get(pk=packet.pk).gst_code == code

    row = [
        str(packet.pk),
        "Pouch",
        packet.short_name,
        code,
        "Yes" if packet.whole_numbers else "No",
    ]
    out = upload(owner, [HEADER[:5], row], commit=True).json()
    assert (out["changed"], out["saved"]) == (1, True), out


def test_an_export_skips_the_in_use_checks(viewer, alpha, monkeypatch):
    """Each record's "in use" checks are a dozen queries; an export never shows
    them, and 12,000 items took over 300 s on staging (2026-11-24)."""
    from core import locks

    asked = []
    real = locks.lock_status
    monkeypatch.setattr(locks, "lock_status", lambda *a: asked.append(a) or real(*a))
    from core import units

    monkeypatch.setattr(units, "lock_status", locks.lock_status)
    assert export(viewer).status_code == 200
    assert asked == []
