"""Warehouses: a branch ticked as a warehouse, its racks, bins and areas."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from openpyxl import load_workbook

from accounts.models import Role, User
from audit.models import AuditEntry
from core.companies import create_company
from core.models import WarehouseLocation
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
def warehouse(owner, company):
    """A branch that holds stock (the normal case); returns its id."""
    made = call(
        owner,
        "post",
        f"companies/{company}/branches/",
        {"name": "Bhiwandi warehouse", "state_code": "27"},
    )
    assert made.status_code == 201, made.json()
    assert made.json()["no_stock"] is False
    return made.json()["id"]


def add(client, company, **body):
    return call(client, "post", f"companies/{company}/warehouse-locations/", body)


def tree(client, company):
    return call(client, "get", f"companies/{company}/warehouses/").json()


def _house(client, company, name="Bhiwandi warehouse"):
    return next(h for h in tree(client, company) if h["name"] == name)


def test_racks_bins_and_areas_build_the_tree(owner, company, warehouse):
    rack = add(owner, company, branch=warehouse, kind="rack", name="  R1 ")
    assert rack.status_code == 201, rack.json()
    assert rack.json()["name"] == "R1"
    for name in ("A1", "A2"):
        r = add(owner, company, branch=warehouse, kind="bin", parent=rack.json()["id"], name=name)
        assert r.status_code == 201, r.json()
    area = add(owner, company, branch=warehouse, kind="area", name="Despatch", purpose="despatch")
    assert area.status_code == 201, area.json()
    assert area.json()["purpose_label"] == "Despatch"

    house = _house(owner, company)
    assert house["name"] == "Bhiwandi warehouse"
    assert [b["name"] for b in house["racks"][0]["bins"]] == ["A1", "A2"]
    assert house["racks"][0]["bin_count"] == 2
    assert [a["name"] for a in house["areas"]] == ["Despatch", "Store"]


def test_a_location_says_what_uses_it_and_what_is_locked(owner, company, warehouse):
    from core import locks

    rack = add(owner, company, branch=warehouse, kind="rack", name="R1").json()
    assert rack["lock"] == {"in_use": [], "locked": []}
    locks.register("warehouse_location", lambda loc: "2 stock entries")
    try:
        house = _house(owner, company)
        assert house["racks"][0]["lock"]["in_use"] == ["2 stock entries"]
        assert set(house["racks"][0]["lock"]["locked"]) == {"kind", "parent"}
    finally:
        locks._USES["warehouse_location"].pop()


def test_every_branch_holds_stock_unless_ticked_no_stock(owner, company):
    # The head office holds stock like any branch, with a default store and nothing else.
    (head,) = tree(owner, company)
    assert head["name"] == "Head office" and head["racks"] == []
    (store,) = head["areas"]
    assert store["name"] == "Store" and store["is_default"] is True
    assert store["purpose"] == "storage"

    shop = call(
        owner,
        "post",
        f"companies/{company}/branches/",
        {"name": "Sales office", "state_code": "27", "no_stock": True},
    ).json()["id"]
    assert [h["name"] for h in tree(owner, company)] == ["Head office"]
    r = add(owner, company, branch=shop, kind="rack", name="R1")
    assert r.status_code == 400 and "No stock" in str(r.json())

    # Untick No stock and the branch gets its default store.
    call(owner, "patch", f"branches/{shop}/", {"no_stock": False})
    assert _house(owner, company, "Sales office")["areas"][0]["is_default"] is True


def test_the_default_store_stays_and_is_not_duplicated(owner, company, warehouse):
    store = _house(owner, company)["areas"][0]
    r = call(owner, "patch", f"warehouse-locations/{store['id']}/", {"is_active": False})
    assert r.status_code == 400 and "default store" in str(r.json())
    r = call(owner, "patch", f"warehouse-locations/{store['id']}/", {"name": "Main Store"})
    assert r.status_code == 200 and r.json()["is_default"] is True
    # Saving the branch again does not add a second default store.
    call(owner, "patch", f"branches/{warehouse}/", {"phone": ""})
    assert [a["name"] for a in _house(owner, company)["areas"]] == ["Main Store"]
    # No stock cannot be ticked while racks exist, but the lone default store does not count.
    add(owner, company, branch=warehouse, kind="rack", name="R1")
    r = call(owner, "patch", f"branches/{warehouse}/", {"no_stock": True})
    assert r.status_code == 400 and "racks, bins or areas" in str(r.json())


def test_no_stock_with_only_the_default_store_closes_it(owner, company, warehouse):
    r = call(owner, "patch", f"branches/{warehouse}/", {"no_stock": True})
    assert r.status_code == 200, r.json()
    assert "Bhiwandi warehouse" not in [h["name"] for h in tree(owner, company)]
    call(owner, "patch", f"branches/{warehouse}/", {"no_stock": False})
    assert [a["name"] for a in _house(owner, company)["areas"]] == ["Store"]


def test_the_shape_rules(owner, company, warehouse):
    rack = add(owner, company, branch=warehouse, kind="rack", name="R1").json()["id"]

    def bad(**body):
        r = add(owner, company, branch=warehouse, **body)
        assert r.status_code == 400, r.json()
        return str(r.json())

    assert "Pick the rack" in bad(kind="bin", name="B1")
    assert "Pick an area" in bad(kind="rack", name="R2", parent=rack)
    assert "does not stand in" in bad(kind="area", name="X", purpose="receiving", parent=rack)
    assert "for" in bad(kind="area", name="Dock")  # an area needs its purpose
    bin_ = add(owner, company, branch=warehouse, kind="bin", parent=rack, name="B1").json()["id"]
    assert "Pick a rack" in bad(kind="bin", name="B2", parent=bin_)
    # A purpose means nothing on a rack.
    quiet = add(owner, company, branch=warehouse, kind="rack", name="R3", purpose="despatch")
    assert quiet.json()["purpose"] == ""


def test_racks_stand_in_an_area(owner, company, warehouse, alpha):
    """Sidharth, 2026-11-19: the Finished Goods area holds racks with bins under them."""
    fg = add(owner, company, branch=warehouse, kind="area", name="FG", purpose="storage")
    fg = fg.json()["id"]
    dock = add(owner, company, branch=warehouse, kind="area", name="Despatch", purpose="despatch")
    rack = add(owner, company, branch=warehouse, kind="rack", name="FG-R1", parent=fg)
    assert rack.status_code == 201 and rack.json()["parent"] == fg
    add(owner, company, branch=warehouse, kind="bin", parent=rack.json()["id"], name="B01")
    # Rack names stay unique in the warehouse, whichever area they stand in.
    again = add(owner, company, branch=warehouse, kind="rack", name="fg-r1")
    assert again.status_code == 400
    dock_id = dock.json()["id"]
    again = add(owner, company, branch=warehouse, kind="rack", name="FG-R1", parent=dock_id)
    assert again.status_code == 400
    # A rack straight in the warehouse can be given an area later, and moved.
    old = add(owner, company, branch=warehouse, kind="rack", name="R-OLD").json()["id"]
    moved = call(owner, "patch", f"warehouse-locations/{old}/", {"parent": fg})
    assert moved.status_code == 200 and moved.json()["parent"] == fg
    out = call(owner, "patch", f"warehouse-locations/{old}/", {"parent": None})
    assert out.status_code == 200 and out.json()["parent"] is None
    # Only an active area of the same warehouse.
    call(owner, "patch", f"warehouse-locations/{dock.json()['id']}/", {"is_active": False})
    shut = call(owner, "patch", f"warehouse-locations/{old}/", {"parent": dock.json()["id"]})
    assert shut.status_code == 400 and "disabled" in str(shut.json())
    busy = call(owner, "patch", f"warehouse-locations/{fg}/", {"is_active": False})
    assert busy.status_code == 400 and "Disable its 1 rack" in str(busy.json())
    racks = {r["name"]: r for r in _house(owner, company)["racks"]}
    assert racks["FG-R1"]["parent"] == fg and len(racks["FG-R1"]["bins"]) == 1


def test_names_do_not_repeat_but_bins_can_on_other_racks(owner, company, warehouse):
    r1 = add(owner, company, branch=warehouse, kind="rack", name="R1").json()
    r2 = add(owner, company, branch=warehouse, kind="rack", name="R2").json()
    add(owner, company, branch=warehouse, kind="bin", parent=r1["id"], name="A1")
    again = add(owner, company, branch=warehouse, kind="bin", parent=r1["id"], name=" a1")
    assert again.status_code == 400
    assert again.json()["existing"]["kind"] == "warehouse_location"
    assert (
        add(owner, company, branch=warehouse, kind="bin", parent=r2["id"], name="A1").status_code
        == 201
    )
    clash = add(owner, company, branch=warehouse, kind="rack", name="r1")
    assert clash.status_code == 400
    # A rack and an area may share a name.
    assert (
        add(owner, company, branch=warehouse, kind="area", name="R1", purpose="storage").status_code
        == 201
    )


def test_a_rack_with_open_bins_cannot_be_disabled(owner, company, warehouse):
    rack = add(owner, company, branch=warehouse, kind="rack", name="R1").json()["id"]
    bin_ = add(owner, company, branch=warehouse, kind="bin", parent=rack, name="B1").json()["id"]
    refused = call(owner, "patch", f"warehouse-locations/{rack}/", {"is_active": False})
    assert refused.status_code == 400 and "Disable its 1 bin" in str(refused.json())
    assert (
        call(owner, "patch", f"warehouse-locations/{bin_}/", {"is_active": False}).status_code
        == 200
    )
    assert (
        call(owner, "patch", f"warehouse-locations/{rack}/", {"is_active": False}).status_code
        == 200
    )
    # No new bin on a disabled rack, and a bin cannot come back under it.
    assert (
        add(owner, company, branch=warehouse, kind="bin", parent=rack, name="B2").status_code == 400
    )
    back = call(owner, "patch", f"warehouse-locations/{bin_}/", {"is_active": True})
    assert back.status_code == 400 and "Enable the rack" in str(back.json())


def test_renaming_is_allowed_and_recorded(alpha, owner, company, warehouse):
    rack = add(owner, company, branch=warehouse, kind="rack", name="R1").json()["id"]
    done = call(owner, "patch", f"warehouse-locations/{rack}/", {"name": "Rack 1"})
    assert done.status_code == 200 and done.json()["name"] == "Rack 1"
    with use_tenant(alpha):
        entries = AuditEntry.objects.filter(record_type="warehouse_location")
        # The branch's default store was added too, and recorded.
        assert entries.count() == 3
        assert any("Rack 1" in str(e.changes) for e in entries)


def test_a_warehouse_with_locations_stays_a_warehouse(owner, company, warehouse):
    add(owner, company, branch=warehouse, kind="rack", name="R1")
    r = call(owner, "patch", f"branches/{warehouse}/", {"no_stock": True})
    assert r.status_code == 400 and "racks, bins or areas" in str(r.json())


def test_another_company_cannot_use_the_warehouse(alpha, owner, company, warehouse):
    with use_tenant(alpha):
        other = create_company(name="Second Co", state_code="27").pk
    r = add(owner, other, branch=warehouse, kind="rack", name="R1")
    assert r.status_code == 400 and "of this company" in str(r.json())


def test_viewers_read_but_cannot_change(viewer, owner, company, warehouse):
    assert call(viewer, "get", f"companies/{company}/warehouses/").status_code == 200
    assert add(viewer, company, branch=warehouse, kind="rack", name="R1").status_code == 403
    rack = add(owner, company, branch=warehouse, kind="rack", name="R1").json()["id"]
    assert call(viewer, "patch", f"warehouse-locations/{rack}/", {"name": "x"}).status_code == 403


def _book(rows):
    from openpyxl import Workbook

    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_racks_bins_and_areas_import_and_export(alpha, owner, company, warehouse):
    url = "/api/v1/exchange/warehouse-locations/"
    first = owner.get(f"{url}?as=xlsx&blank=1&company={company}", HTTP_HOST=HOST)
    head = [list(r) for r in load_workbook(io.BytesIO(first.content)).worksheets[0].values][0]
    for label in ("Warehouse", "Type", "Name", "On rack / in area", "Area is for"):
        assert label in head, head
    col = {name: head.index(name) for name in head}

    def row(**cells):
        out = [None] * len(head)
        for label, value in cells.items():
            out[col["On rack / in area" if label == "On_rack" else label.replace("_", " ")]] = value
        return out

    rows = [
        head,
        row(Warehouse="Bhiwandi warehouse", Type="Area", Name="Receiving", Area_is_for="Receiving"),
        row(Warehouse="Bhiwandi warehouse", Type="Rack", Name="R1", On_rack="Receiving"),
        row(Warehouse="Bhiwandi warehouse", Type="Bin", Name="A1", On_rack="R1"),
        row(Warehouse="Bhiwandi warehouse", Type="Bin", Name="B1", On_rack="Nope"),
    ]

    def send(rows, commit):
        return owner.post(
            f"{url}import/",
            {
                "file": SimpleUploadedFile("x.xlsx", _book(rows)),
                "commit": "1" if commit else "0",
                "company": str(company),
            },
            HTTP_HOST=HOST,
        ).json()

    bad = send(rows, commit=True)
    assert bad["errors"] and not bad["saved"]  # the unknown rack stops the whole file
    assert "Nope" in str(bad["errors"])
    out = send(rows[:4], commit=True)
    assert out["errors"] == [] and out["saved"] and out["new"] == 3
    with use_tenant(alpha):
        a1 = WarehouseLocation.objects.get(name="A1")
        assert a1.kind == "bin" and a1.parent.name == "R1"
        assert a1.parent.parent.name == "Receiving"  # the rack stands in the area
        assert WarehouseLocation.objects.get(name="Receiving").purpose == "receiving"
    back = owner.get(f"{url}?as=xlsx&company={company}", HTTP_HOST=HOST)
    cells = [list(r) for r in load_workbook(io.BytesIO(back.content)).worksheets[0].values]
    on = col["On rack / in area"]
    assert any(r[col["Name"]] == "A1" and r[on] == "R1" for r in cells)
    assert any(r[col["Name"]] == "R1" and r[on] == "Receiving" for r in cells)
    names = [r[col["Name"]] for r in cells[1:]]
    assert names.index("Receiving") < names.index("R1") < names.index("A1")


def test_old_default_stores_are_renamed_store(alpha, owner, company, warehouse):
    """Default stores named after the branch read just "Store" after the migration, unless
    renamed by hand or the branch already has another area called "Store"."""
    import importlib

    from django.apps import apps

    renamer = importlib.import_module("core.migrations.0063_default_store_named_store")
    with use_tenant(alpha):
        stores = WarehouseLocation.objects.filter(
            is_default=True, branch__company_id=company
        ).select_related("branch")
        for store in stores:
            store.name = f"{store.branch.name} Store"
            store.save(update_fields=["name"])
        house, head = sorted(stores, key=lambda s: s.branch.name)
        WarehouseLocation.objects.create(
            branch=house.branch, kind="area", name="Store", purpose="storage"
        )
        renamer.name_default_stores_store(apps, None)
        head.refresh_from_db()
        house.refresh_from_db()
    assert head.name == "Store"
    assert house.name == "Bhiwandi warehouse Store"
