"""Items: the shared catalogue and each item's chain of units."""

from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

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


@pytest.fixture
def unit(accountant, company):
    ids = {u["name"]: u["id"] for u in call(accountant, "get", "units/").json()}
    return lambda name: ids[name]


def chain(unit):
    return [
        {
            "unit": unit("Packet"),
            "length_cm": "18",
            "breadth_cm": "12",
            "height_cm": "5",
            "net_kg": "0.5",
            "gross_kg": "0.52",
            "barcode": "8901234500011",
            "used_for": ["stock"],
        },
        {"unit": unit("Inner box"), "contains_qty": "6", "contains_unit": unit("Packet")},
        {
            "unit": unit("Carton"),
            "contains_qty": "4",
            "contains_unit": unit("Inner box"),
            "length_cm": "54",
            "breadth_cm": "40",
            "height_cm": "34",
            "used_for": ["purchase"],
        },
        {"unit": unit("Pallet"), "contains_qty": "40", "contains_unit": unit("Carton")},
    ]


def make(client, unit, **data):
    body = {
        "name": "Jaggery Powder 500 g",
        "stock_unit": unit("Packet"),
        "hsn": "0902",
        "units": chain(unit),
        **data,
    }
    return call(client, "post", "items/", body)


def test_item_with_a_chain_of_units(accountant, unit):
    made = make(accountant, unit, hsn="1701", batch_tracked=True)
    assert made.status_code == 201, made.json()
    item = made.json()
    assert item["item_number"] == "ITEM-00001"
    rows = {r["unit_name"]: r for r in item["units"]}
    assert Decimal(rows["Packet"]["factor"]) == 1
    assert Decimal(rows["Inner box"]["factor"]) == 6
    assert Decimal(rows["Carton"]["factor"]) == 24
    assert Decimal(rows["Pallet"]["factor"]) == 960
    assert rows["Carton"]["volume_m3"] == "0.07344"
    assert rows["Packet"]["volume_m3"] == "0.00108"
    assert rows["Pallet"]["volume_m3"] is None
    assert item["warnings"] == ["Size missing for: Inner box, Pallet."]
    # numbers keep counting
    second = make(accountant, unit, name="Turmeric", units=[])
    assert second.json()["item_number"] == "ITEM-00002"


def test_the_stock_unit_always_has_a_row(accountant, unit):
    made = call(
        accountant,
        "post",
        "items/",
        {"name": "Bag of rice", "stock_unit": unit("Kilogram"), "hsn": "0902"},
    )
    assert made.status_code == 201, made.json()
    assert [(r["unit_name"], r["factor"]) for r in made.json()["units"]] == [
        ("Kilogram", "1.000000")
    ]


def test_change_keeps_units_unless_sent(accountant, unit):
    item = make(accountant, unit).json()
    changed = call(accountant, "patch", f"items/{item['id']}/", {"hsn": "1701", "is_active": False})
    assert changed.status_code == 200, changed.json()
    assert changed.json()["is_active"] is False
    assert len(changed.json()["units"]) == 4

    fewer = call(accountant, "patch", f"items/{item['id']}/", {"units": chain(unit)[:2]})
    assert fewer.status_code == 200, fewer.json()
    assert [r["unit_name"] for r in fewer.json()["units"]] == ["Packet", "Inner box"]

    entries = call(accountant, "get", f"audit/?type=item&id={item['id']}").json()["entries"]
    assert [e["action"] for e in entries] == ["update", "update", "create"]
    added = {c["label"]: c["new"] for c in entries[2]["changes"]}
    assert added["Item number"] == "ITEM-00001"
    assert "Carton = 4 Inner box (24 Packet)" in added["Units"]


def test_chain_checks(accountant, unit):
    def error(units, **data):
        r = make(accountant, unit, units=units, **data)
        assert r.status_code == 400, r.json()
        return r.json()

    packet = {"unit": unit("Packet")}
    assert "units" in error([packet, {"unit": unit("Packet")}])  # twice
    assert "units" in error([packet, {"unit": unit("Carton")}])  # says nothing
    assert "units" in error(
        [packet, {"unit": unit("Carton"), "contains_qty": "0", "contains_unit": unit("Packet")}]
    )
    assert "units" in error(
        [packet, {"unit": unit("Carton"), "contains_qty": "4", "contains_unit": unit("Pallet")}]
    )  # Pallet is not listed
    assert "units" in error(
        [packet, {"unit": unit("Carton"), "contains_qty": "4", "contains_unit": unit("Carton")}]
    )
    assert "units" in error(
        [
            packet,
            {"unit": unit("Carton"), "contains_qty": "4", "contains_unit": unit("Pallet")},
            {"unit": unit("Pallet"), "contains_qty": "4", "contains_unit": unit("Carton")},
        ]
    )  # a circle
    assert "units" in error(
        [{"unit": unit("Packet"), "contains_qty": "2", "contains_unit": unit("Nos")}]
    )  # the stock unit contains nothing


def test_item_checks(accountant, unit):
    assert make(accountant, unit).status_code == 201
    clash = make(accountant, unit, name="jaggery powder 500 G", units=[])
    assert clash.status_code == 400 and "name" in clash.json()
    assert "hsn" in make(accountant, unit, name="X", units=[], hsn="17A1").json()
    # the same barcode on another item
    again = make(accountant, unit, name="Other", units=chain(unit)[:1])
    assert again.status_code == 400 and "barcode" in str(again.json())


def test_disabled_units_cannot_be_newly_added(accountant, unit):
    call(accountant, "patch", f"units/{unit('Pallet')}/", {"is_active": False})
    r = make(
        accountant,
        unit,
        name="New",
        units=[
            {"unit": unit("Packet")},
            {"unit": unit("Pallet"), "contains_qty": "5", "contains_unit": unit("Packet")},
        ],
    )
    assert r.status_code == 400 and "disabled" in str(r.json())


def test_changing_the_stock_unit_must_keep_the_chain_whole(accountant, unit):
    item = make(accountant, unit).json()
    r = call(accountant, "patch", f"items/{item['id']}/", {"stock_unit": unit("Carton")})
    # Carton becomes the stock unit, but Packet no longer chains to it.
    assert r.status_code == 400, r.json()


def test_viewer_may_read_but_not_change(viewer, accountant, unit):
    make(accountant, unit)
    assert len(call(viewer, "get", "items/").json()) == 1
    assert (
        call(
            viewer, "post", "items/", {"name": "X", "stock_unit": unit("Nos"), "hsn": "0902"}
        ).status_code
        == 403
    )


def test_sales_and_purchase_details(accountant, unit):
    made = make(
        accountant,
        unit,
        sales_description="  Organic jaggery powder, 500 g pouch  ",
        sales_unit=unit("Carton"),
        purchase_description="Jaggery powder in 25 kg bags",
        purchase_unit=unit("Pallet"),
    )
    assert made.status_code == 201, made.json()
    item = made.json()
    assert item["sales_description"] == "Organic jaggery powder, 500 g pouch"
    assert item["sales_unit_name"] == "Carton"
    assert item["purchase_unit_name"] == "Pallet"

    # a default unit must be one of the item's units
    bad = make(accountant, unit, name="Other", sales_unit=unit("Kilogram"))
    assert bad.status_code == 400
    assert "not one of the item's units" in bad.json()["sales_unit"][0]

    # dropping the unit from the list while it is the default is refused
    fewer = call(accountant, "patch", f"items/{item['id']}/", {"units": chain(unit)[:3]})
    assert fewer.status_code == 400
    assert "Pallet" in fewer.json()["purchase_unit"][0]

    cleared = call(
        accountant,
        "patch",
        f"items/{item['id']}/",
        {"purchase_unit": None, "units": chain(unit)[:3]},
    )
    assert cleared.status_code == 200, cleared.json()
    assert cleared.json()["purchase_unit"] is None


def test_gst_rates_are_dated(accountant, unit, alpha):
    from datetime import date

    from core.items import gst_rate_on
    from core.models import Item

    made = make(
        accountant,
        unit,
        gst_rates=[
            {"valid_from": "2025-09-22", "rate": "5"},
            {"valid_from": "2017-07-01", "rate": "18"},
        ],
    )
    assert made.status_code == 201, made.json()
    item = made.json()
    assert item["gst_rates"] == [
        {"valid_from": "2017-07-01", "rate": "18.00"},
        {"valid_from": "2025-09-22", "rate": "5.00"},
    ]
    with use_tenant(alpha):
        row = Item.objects.get(pk=item["id"])
        assert gst_rate_on(row, date(2017, 6, 30)) is None
        assert gst_rate_on(row, date(2025, 9, 21)) == Decimal(18)
        assert gst_rate_on(row, date(2025, 9, 22)) == Decimal(5)

    # a new law: add a row, the old ones stay
    later = item["gst_rates"] + [{"valid_from": "2027-04-01", "rate": "3"}]
    changed = call(accountant, "patch", f"items/{item['id']}/", {"gst_rates": later})
    assert changed.status_code == 200, changed.json()
    assert len(changed.json()["gst_rates"]) == 3
    entries = call(accountant, "get", f"audit/?type=item&id={item['id']}").json()["entries"]
    now = {c["label"]: c["new"] for c in entries[0]["changes"]}
    assert "3% from 01-04-2027" in now["GST rates"]

    # other edits leave the rates alone
    kept = call(accountant, "patch", f"items/{item['id']}/", {"notes": "x"})
    assert len(kept.json()["gst_rates"]) == 3

    twice = [{"valid_from": "2027-04-01", "rate": "3"}, {"valid_from": "2027-04-01", "rate": "5"}]
    bad = call(accountant, "patch", f"items/{item['id']}/", {"gst_rates": twice})
    assert bad.status_code == 400
    assert "Two rates start on 01-04-2027" in bad.json()["gst_rates"][0]

    over = call(
        accountant,
        "patch",
        f"items/{item['id']}/",
        {"gst_rates": [{"valid_from": "2027-04-01", "rate": "140"}]},
    )
    assert over.status_code == 400


def test_item_gst_rates_come_from_the_central_list(accountant, unit):
    item = make(accountant, unit).json()
    url = f"items/{item['id']}/"
    odd = call(accountant, "patch", url, {"gst_rates": [{"valid_from": "2027-04-01", "rate": "7"}]})
    assert odd.status_code == 400
    assert "7% is not in the GST rates list" in str(odd.json())
    # 28% is in the list but disabled: refused when new, kept when the item already had it.
    off = [{"valid_from": "2017-07-01", "rate": "28"}]
    assert call(accountant, "patch", url, {"gst_rates": off}).status_code == 400
    from tenancy.models import GstRate

    GstRate.objects.filter(rate=28).update(is_active=True)
    assert call(accountant, "patch", url, {"gst_rates": off}).status_code == 200
    GstRate.objects.filter(rate=28).update(is_active=False)
    again = off + [{"valid_from": "2027-04-01", "rate": "18"}]
    assert call(accountant, "patch", url, {"gst_rates": again}).status_code == 200


def test_item_ticks_allow_purchase_sales_and_stock(accountant, unit):
    item = make(accountant, unit).json()
    assert item["allow_purchase"] is True and item["allow_sales"] is True
    assert item["item_type"] == "goods"
    changed = call(
        accountant,
        "patch",
        f"items/{item['id']}/",
        {"allow_purchase": False, "allow_sales": False},
    ).json()
    assert changed["allow_purchase"] is False and changed["allow_sales"] is False
    listed = {i["id"]: i for i in call(accountant, "get", "items/").json()}
    assert listed[item["id"]]["allow_purchase"] is False
    entries = call(accountant, "get", f"audit/?type=item&id={item['id']}").json()["entries"]
    assert any("Allow purchase" in str(e) for e in entries)


def test_maintain_stock_is_separate_from_goods_or_service(accountant, unit):
    plain = make(accountant, unit).json()
    assert plain["item_type"] == "goods" and plain["maintain_stock"] is True
    service = make(
        accountant, unit, name="Freight", item_type="service", units=[], delivery_hsn="0910"
    ).json()
    assert service["item_type"] == "service" and service["maintain_stock"] is True
    goods = call(accountant, "patch", f"items/{plain['id']}/", {"maintain_stock": False}).json()
    assert goods["item_type"] == "goods" and goods["maintain_stock"] is False


def test_sales_and_purchase_tab_fields(accountant, unit):
    made = make(
        accountant,
        unit,
        mrp="125.50",
        usp="Single-origin, stone ground",
        best_before_value=12,
        best_before_unit="months",
        batch_no="  B-2627  ",
        lead_time_days=14,
        min_order_qty="100",
    )
    assert made.status_code == 201, made.json()
    item = made.json()
    assert item["mrp"] == "125.50" and item["batch_no"] == "B-2627"
    assert (item["best_before_value"], item["best_before_unit"]) == (12, "months")
    assert item["lead_time_days"] == 14 and item["min_order_qty"] == "100.000000"
    assert "sales_name" not in item and "purchase_name" not in item
    assert "shelf_life_days" not in item
    # no negative quantities
    path = f"items/{item['id']}/"
    assert call(accountant, "patch", path, {"min_order_qty": "-1"}).status_code == 400
    assert call(accountant, "patch", path, {"mrp": "-1"}).status_code == 400
    assert call(accountant, "patch", path, {"best_before_unit": "years"}).status_code == 400
    # the defaults for an item with none of them
    plain = make(accountant, unit, name="Plain", units=[]).json()
    assert plain["mrp"] is None and plain["best_before_unit"] == "days"


def test_default_material_request_type(accountant, unit):
    made = make(accountant, unit, default_request_type="customer_provided").json()
    assert made["default_request_type"] == "customer_provided"
    path = f"items/{made['id']}/"
    assert (
        call(accountant, "patch", path, {"default_request_type": "manufacture"}).status_code == 200
    )
    assert call(accountant, "patch", path, {"default_request_type": "rent"}).status_code == 400
    assert (
        call(accountant, "patch", path, {"default_request_type": ""}).json()["default_request_type"]
        == ""
    )
    plain = make(accountant, unit, name="Plain", units=[]).json()
    assert plain["default_request_type"] == ""


def test_hsn_code_is_required(accountant, unit):
    body = {"name": "No HSN", "stock_unit": unit("Packet"), "units": []}
    refused = call(accountant, "post", "items/", body)
    assert refused.status_code == 400
    assert "hsn" in refused.json()
    assert call(accountant, "post", "items/", {**body, "hsn": "0902"}).status_code == 201


def test_hsn_code_must_be_in_the_central_list(accountant, unit):
    body = {"name": "Odd HSN", "stock_unit": unit("Packet"), "units": [], "hsn": "9999"}
    refused = call(accountant, "post", "items/", body)
    assert refused.status_code == 400
    assert "not in the list" in str(refused.json()["hsn"])
    made = call(accountant, "post", "items/", {**body, "hsn": "0902"})
    assert made.status_code == 201
    other = call(accountant, "patch", f"items/{made.json()['id']}/", {"hsn": "8888"})
    assert other.status_code == 400


def test_a_service_that_keeps_stock_needs_a_delivery_hsn(accountant, unit):
    """Job work: the service code (SAC) goes on the invoice, the goods code on the challan."""
    from tenancy.models import HsnCode

    HsnCode.objects.get_or_create(hsn_code="998818", defaults={"description": "Job work, food"})
    body = {
        "name": "Private label tea, packed",
        "item_type": "service",
        "maintain_stock": True,
        "stock_unit": unit("Packet"),
        "units": [],
        "hsn": "998818",
    }
    refused = call(accountant, "post", "items/", body)
    assert refused.status_code == 400 and "delivery_hsn" in refused.json()
    digits = call(accountant, "post", "items/", {**body, "delivery_hsn": "09A2"})
    assert digits.status_code == 400 and "digits only" in str(digits.json()["delivery_hsn"])
    odd = call(accountant, "post", "items/", {**body, "delivery_hsn": "99999999"})
    assert odd.status_code == 400 and "not in the list" in str(odd.json()["delivery_hsn"])
    made = call(accountant, "post", "items/", {**body, "delivery_hsn": "0902"})
    assert made.status_code == 201, made.json()
    assert made.json()["hsn"] == "998818" and made.json()["delivery_hsn"] == "0902"
    blank = call(accountant, "patch", f"items/{made.json()['id']}/", {"delivery_hsn": ""})
    assert blank.status_code == 400


def test_the_delivery_hsn_is_cleared_when_it_does_not_apply(accountant, unit):
    plain = {"name": "Loose tea", "stock_unit": unit("Packet"), "units": [], "hsn": "0902"}
    made = call(accountant, "post", "items/", {**plain, "delivery_hsn": "0910"})
    assert made.status_code == 201 and made.json()["delivery_hsn"] == ""  # goods: not used
    service = {**plain, "name": "Blending charges", "item_type": "service", "maintain_stock": False}
    free = call(accountant, "post", "items/", {**service, "delivery_hsn": "0910"})
    assert free.status_code == 201 and free.json()["delivery_hsn"] == ""  # no stock: not used
