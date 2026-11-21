"""Items from ERPNext's own Item export (Sidharth, 2026-11-21): codes kept as
item numbers, groups and brands only matched, HSN checked, Description and
planning figures left out, new items carry on the ERPNext series."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from core.models import Item, NumberSeries
from tenancy.context import use_tenant
from tenancy.models import HsnCode

from .test_exchange import HOST, ITEMS, _client, send

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HEAD = [
    "ID",
    "Item Code",
    "Item Name",
    "Item Group",
    "Default Unit of Measure",
    "Brand",
    "HSN/SAC",
    "Maintain Stock",
    "Allow Purchase",
    "Allow Sales",
    "Has Batch No",
    "Disabled",
    "Description",
    "Safety Stock",
    "ID (UOMs)",
    "UOM (UOMs)",
    "Conversion Factor (UOMs)",
    "ID (Taxes)",
    "Item Tax Template (Taxes)",
    "Valid From (Taxes)",
]


def row(code="", name="", group="", unit="", brand="", hsn="", stock=1, disabled=0, **kw):
    r = dict.fromkeys(HEAD, "")
    if code:
        r.update(
            {
                "ID": code,
                "Item Code": code,
                "Item Name": name,
                "Item Group": group,
                "Default Unit of Measure": unit,
                "Brand": brand,
                "HSN/SAC": hsn,
                "Maintain Stock": stock,
                "Allow Purchase": 1,
                "Allow Sales": 1,
                "Has Batch No": 0,
                "Disabled": disabled,
                "Description": "<p>Old text</p>",
                "Safety Stock": 50,
            }
        )
    r.update(kw)
    return [r[h] for h in HEAD]


def erpnext_file(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Item"
    ws.append(HEAD)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def send_erpnext(client, rows, commit=False):
    return client.post(
        "/api/v1/exchange/items/import/",
        {
            "file": SimpleUploadedFile("Item.xlsx", erpnext_file(rows)),
            "commit": "1" if commit else "0",
            "source": "erpnext",
        },
        HTTP_HOST=HOST,
    )


@pytest.fixture
def owner(alpha):
    HsnCode.objects.get_or_create(hsn_code="998541", defaults={"description": "Packing"})
    client = _client(alpha, "owner@x.in", "owner")
    for path, name in (("item-groups", "Tea"), ("item-groups", "Services"), ("brands", "Apurvam")):
        client.post(
            f"/api/v1/{path}/",
            data=f'{{"name": "{name}"}}',
            content_type="application/json",
            HTTP_HOST=HOST,
        )
    return client


GOOD = [
    row("IT-012465", "Assam Tea 1 kg", "Tea", "Kg", "Apurvam", "0902", **{
        "UOM (UOMs)": "Kg", "Conversion Factor (UOMs)": 1,
        "Item Tax Template (Taxes)": "GST 5% - AO",
    }),
    row(**{"UOM (UOMs)": "Carton", "Conversion Factor (UOMs)": 12,
           "Item Tax Template (Taxes)": "IGST 5% - AO"}),
    row("IT-000412", "Packing Charges", "Services", "Nos", "Apurvam", "998541", stock=0,
        disabled=1),
]  # fmt: skip


def test_erpnext_export_comes_in_with_its_codes(owner, alpha):
    out = send_erpnext(owner, GOOD).json()
    assert out["errors"] == [] and out["new"] == 2, out
    assert any("1 item had no GST rate" in n and "IT-000412" in n for n in out["notes"])
    assert any("Description" in n and "Safety Stock" in n for n in out["notes"])
    with use_tenant(alpha):
        assert not Item.objects.filter(item_number="IT-012465").exists()  # only checked

    out = send_erpnext(owner, GOOD, commit=True).json()
    assert out["saved"] is True
    with use_tenant(alpha):
        tea = Item.objects.get(item_number="IT-012465")
        assert (tea.name, tea.item_type, tea.hsn) == ("Assam Tea 1 kg", "goods", "0902")
        assert tea.stock_unit.name == "Kilogram" and tea.brand.name == "Apurvam"
        assert tea.safety_stock_qty is None and tea.notes == ""  # left out, as agreed
        carton = tea.units.get(unit__name="Carton")
        assert carton.factor == 12 and carton.contains_unit == tea.stock_unit
        assert [(r.valid_from.isoformat(), r.rate) for r in tea.gst_rates.all()] == [
            ("2017-07-01", 5)
        ]
        packing = Item.objects.get(item_number="IT-000412")
        assert packing.item_type == "service" and packing.is_active is False
        series = NumberSeries.objects.get(key="item")
        assert (series.prefix, series.width, series.last) == ("IT-", 6, 12465)

    # A new item made in MyERP carries on the ERPNext series.
    made = owner.post(
        "/api/v1/items/",
        data={"name": "Green Tea", "item_type": "goods", "stock_unit": tea.stock_unit_id,
              "hsn": "0902"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )  # fmt: skip
    assert made.status_code == 201, made.json()
    assert made.json()["item_number"] == "IT-012466"

    # The same file again changes nothing.
    out = send_erpnext(owner, GOOD, commit=True).json()
    assert (out["new"], out["changed"], out["errors"]) == (0, 0, [])


def test_items_made_by_hand_get_their_erpnext_codes(owner, alpha):
    hand = ["Assam Tea 1 kg", "Goods", "Tea", "kg", "0902", "Apurvam"]
    out = send(owner, "items", {"Items": [ITEMS, hand]}, commit=True).json()
    assert out["saved"] is True
    with use_tenant(alpha):
        before = Item.objects.get(name="Assam Tea 1 kg")
        assert before.item_number.startswith("ITEM-")

    out = send_erpnext(owner, GOOD, commit=True).json()
    assert (out["new"], out["changed"], out["saved"]) == (1, 1, True), out
    with use_tenant(alpha):
        assert Item.objects.get(pk=before.pk).item_number == "IT-012465"
        # Nothing holds an ITEM- number any more: the series follows IT-.
        assert NumberSeries.objects.get(key="item").prefix == "IT-"


def test_problems_point_at_rows_of_the_erpnext_file(owner):
    rows = [
        GOOD[0],
        GOOD[1],
        row("IT-000500", "Old Box", "Packing Material - Old", "Nos", "Apurvam", "4819"),
        row("IT-000501", "Mystery Tea", "Tea", "Kg", "Apurvam", "0902100"),
    ]
    out = send_erpnext(owner, rows, commit=True).json()
    assert out["saved"] is False
    where = {(e["sheet"], e["row"]): e["messages"] for e in out["errors"]}
    assert where[("Items", 4)] == [
        "Item group: there is no item group called 'Packing Material - Old'"
    ]
    assert where[("Items", 5)] == ["HSN: That HSN code is not in the list. Pick one from the list."]


def test_an_item_number_taken_by_another_item_is_refused(owner, alpha):
    send_erpnext(owner, GOOD, commit=True)
    rows = [row("IT-012465", "Darjeeling Tea", "Tea", "Kg", "Apurvam", "0902")]
    out = send_erpnext(owner, rows).json()
    # Found by its number: the existing item is renamed, not doubled.
    assert (out["changed"], out["errors"]) == (1, [])
    out = send(
        owner, "items", {"Items": [["Item number", *ITEMS], ["it-012465", "Nilgiri", "Goods",
                                                             "Tea", "kg", "0902", "Apurvam"]]},
    ).json()  # fmt: skip
    assert out["errors"][0]["messages"] == [
        'Item number: The item number IT-012465 is already on the item "Assam Tea 1 kg".'
    ]


def test_not_an_erpnext_file(owner):
    res = owner.post(
        "/api/v1/exchange/items/import/",
        {"file": SimpleUploadedFile("x.csv", b"Colour,Size\nred,2\n"), "source": "erpnext"},
        HTTP_HOST=HOST,
    )
    assert res.status_code == 400 and "not an ERPNext Item export" in res.json()["detail"]


def test_migration_tools_switch(owner, alpha, settings):
    """Central › Customers: platform admins switch Migration Tools off after the
    cutover; the session tells the menu, and the server refuses the imports."""
    settings.MYERP_PLATFORM_ADMINS = "owner@x.in"
    session = owner.get("/api/auth/session/", HTTP_HOST=HOST).json()
    assert session["migration_tools"] is True
    tenants = owner.get("/api/v1/central/", HTTP_HOST=HOST).json()["tenants"]
    assert next(t for t in tenants if t["slug"] == "alpha")["migration_tools"] is True

    res = owner.patch(
        "/api/v1/central/tenants/alpha/",
        data='{"migration_tools": false}',
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert res.json() == {"slug": "alpha", "migration_tools": False}
    assert owner.get("/api/auth/session/", HTTP_HOST=HOST).json()["migration_tools"] is False
    res = send_erpnext(owner, GOOD)
    assert res.status_code == 403 and "switched off" in res.json()["detail"]

    # Only platform admins may change it.
    settings.MYERP_PLATFORM_ADMINS = "someone@else.in"
    res = owner.patch(
        "/api/v1/central/tenants/alpha/",
        data='{"migration_tools": true}',
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert res.status_code == 403
    alpha.refresh_from_db()
    assert alpha.migration_tools is False
