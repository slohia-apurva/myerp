"""Bills of materials (Sidharth, 2026-11-22, preview 14 in mockups/planning):
versions of an item with exactly one default, where each material comes from
("Manufactured", "Purchased", "Customer's stock"), no circles, the cost
estimate, job work and the Import/Export of the master."""

from decimal import Decimal

import pytest

from core import locks
from core.models import Item, ItemUnit, Party, Unit
from manufacturing.models import Bom
from tenancy.context import use_tenant
from tests.test_exchange import send, sheets_of
from tests.test_sales_orders import call, owner, stock_in, world  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def add_item(w, name, unit="kg", **more):
    with use_tenant(w["tenant"]):
        tea = Item.objects.get(pk=w["tea"])
        u = Unit.objects.get(pk=w[unit])
        item = Item.objects.create(
            item_number=f"ITEM-{name[:3].upper()}{Item.objects.count()}",
            name=name,
            stock_unit=u,
            hsn="0902",
            item_group=tea.item_group,
            brand=tea.brand,
            **more,
        )
        ItemUnit.objects.create(item=item, unit=u, factor=1, whole_numbers=unit != "kg")
        return item.pk


def bom(w, item, lines, makes="1", unit="case", **more):
    return {
        "item": w[item] if isinstance(item, str) else item,
        "makes_qty": makes,
        "makes_unit": w[unit],
        "lines": lines,
        **more,
    }


def line(item, qty, unit, loss="0"):
    return {"item": item, "qty": qty, "unit": unit, "loss_pct": loss}


def test_versions_have_exactly_one_default(owner, world):  # noqa: F811
    w = world
    pouch = add_item(w, "Pouch Laminate", unit="pcs")
    first = call(owner, "post", "boms/", bom(w, "tea", [line(w["loose"], "2.4", w["kg"])]))
    assert first.status_code == 201, first.json()
    v1 = first.json()
    assert (v1["number"], v1["version"], v1["name"], v1["is_default"]) == (
        "BOM-00001",
        1,
        "Version 1",
        True,
    )  # fmt: skip  (the first usable version takes the star)
    lines = [line(w["loose"], "2.4", w["kg"], "0.5"), line(pouch, "24", w["pcs"], "2")]
    second = call(
        owner, "post", "boms/", bom(w, "tea", lines, name="New pouch", is_default=True)
    ).json()
    assert second["version"] == 2 and second["is_default"]
    assert [(v["version"], v["is_default"]) for v in second["versions"]] == [(1, False), (2, True)]
    assert second["materials"][0]["issue_qty"] == "2.412"  # 2.4 kg + 0.5 %
    # A third, saved as a draft: never the default.
    draft = call(owner, "post", "boms/", bom(w, "tea", [], name="Trial", status="draft")).json()
    assert draft["version"] == 3 and not draft["is_default"]
    refused = call(owner, "post", f"boms/{draft['id']}/make-default/")
    assert refused.status_code == 400
    # Names are unique per item, ignoring capitals and spaces.
    clash = call(owner, "post", "boms/", bom(w, "tea", lines, name=" new  POUCH"))
    assert clash.status_code == 400 and clash.json()["existing"]["kind"] == "bom"
    # The star moves back; the default cannot be disabled while another version could take it.
    back = call(owner, "post", f"boms/{v1['id']}/make-default/").json()
    assert [v["is_default"] for v in back["versions"]] == [True, False, False]
    stuck = call(owner, "patch", f"boms/{v1['id']}/", {"is_active": False})
    assert stuck.status_code == 400 and "Make another version the default" in str(stuck.json())
    # A unit the item is not kept in is refused.
    odd = call(owner, "post", "boms/", bom(w, "tea", [line(pouch, "1", w["kg"])]))
    assert odd.status_code == 400 and "not kept in" in str(odd.json())
    # Planning reads the default straight from the item.
    with use_tenant(w["tenant"]):
        assert Bom.objects.get(item_id=w["tea"], is_default=True).version == 1
        assert locks.uses("item", Item.objects.get(pk=pouch)) == ["1 BOM"]


def test_sources_cost_and_no_circles(owner, world):  # noqa: F811
    w = world
    blend = add_item(w, "Green Tea Blend", default_request_type=Item.MANUFACTURE)
    pouch = add_item(w, "Pouch Laminate", unit="pcs")
    stock_in(w, "store", "100", item="loose")  # at 10 a kg
    made = call(owner, "post", "boms/", bom(w, blend, [line(w["loose"], "1", w["kg"])], unit="kg"))
    assert made.status_code == 201, made.json()
    assert made.json()["cost"]["per_unit"] == "10.00"
    lines = [line(blend, "2.4", w["kg"], "0.5"), line(pouch, "24", w["pcs"])]
    tea = call(owner, "post", "boms/", bom(w, "tea", lines)).json()
    blend_row, pouch_row = tea["materials"]
    assert blend_row["source_text"] == f"Manufactured: {made.json()['number']} v1 (default)"
    assert blend_row["rate"] == "10.00" and blend_row["cost"] == "24.12"
    assert [c["item_name"] for c in blend_row["children"]] == ["Loose Leaf"]
    assert pouch_row["source_text"] == "Purchased" and pouch_row["cost"] is None
    assert tea["cost"]["missing"] == ["Pouch Laminate"] and tea["cost"]["per_unit"] is None
    # The blend cannot be made from the tea, which is made from the blend.
    circle = call(
        owner, "patch", f"boms/{made.json()['id']}/", {"lines": [line(w["tea"], "1", w["pcs"])]}
    )
    assert circle.status_code == 400 and "circle" in str(circle.json())
    # Nor may a BOM use the item it makes.
    itself = call(owner, "post", "boms/", bom(w, "tea", [line(w["tea"], "1", w["pcs"])]))
    assert itself.status_code == 400


def test_job_work_mixes_the_customers_goods_with_ours(owner, world):  # noqa: F811
    w = world
    with use_tenant(w["tenant"]):
        party = Party.objects.get(name="Organic Harvest Foods")
        other = Party.objects.exclude(pk=party.pk).exclude(customer_number="").first()
    # The customer is tagged on the item (Sidharth, 2026-11-23, preview 18).
    untagged = add_item(w, "Loose CTC", default_request_type=Item.CUSTOMER_PROVIDED)
    theirs = add_item(
        w, "OHF Assam CTC", default_request_type=Item.CUSTOMER_PROVIDED, customer_id=party.pk
    )
    stock_in(w, "store", "50", item="loose")
    lines = [line(untagged, "2.4", w["kg"])]
    refused = call(owner, "post", "boms/", bom(w, "tea", lines))
    assert refused.status_code == 400 and "set the customer on the item" in str(refused.json())
    if other is not None:
        mixed = add_item(
            w, "Their Pouch", unit="pcs", default_request_type=Item.CUSTOMER_PROVIDED,
            customer_id=other.pk,
        )  # fmt: skip
        both = [line(theirs, "2.4", w["kg"]), line(mixed, "1", w["pcs"])]
        two = call(owner, "post", "boms/", bom(w, "tea", both))
        assert two.status_code == 400 and "cannot use goods of" in str(two.json())
    # A customer's goods make it job work for that customer; nothing to pick.
    lines = [line(theirs, "2.4", w["kg"]), line(w["loose"], "0.1", w["kg"])]
    job = call(owner, "post", "boms/", bom(w, "tea", lines))
    assert job.status_code == 201, job.json()
    j = job.json()
    assert (j["kind"], j["customer_name"]) == ("job_work", "Organic Harvest Foods")
    theirs_row, ours_row = j["materials"]
    assert theirs_row["source_text"] == "Customer's stock" and theirs_row["cost"] == "0.00"
    assert ours_row["cost"] == "1.00"  # only our own material is costed
    # Billed under SAC, despatched under HSN: a goods item is not set up for that.
    assert j["job"]["note"] and j["job"]["hsn"] == "0902"
    with use_tenant(w["tenant"]):
        Item.objects.filter(pk=w["tea"]).update(
            item_type=Item.SERVICE, hsn="998817", delivery_hsn="0902"
        )
    again = call(owner, "get", f"boms/{j['id']}/").json()
    assert again["job"] == {"sac": "998817", "hsn": "0902", "note": ""}


def test_boms_export_and_import_with_materials_on_a_sheet(owner, world):  # noqa: F811
    w = world
    call(owner, "post", "boms/", bom(w, "tea", [line(w["loose"], "2.4", w["kg"], "1")]))
    got = sheets_of(owner, "boms")
    assert list(got) == ["BOMs", "Materials", "By-products", "How to fill"]
    assert got["Materials"][0][:3] == ["BOM", "Item", "Qty"]
    assert got["Materials"][1][:2] == ["BOM-00001", "Loose Leaf"]
    head = got["BOMs"][0]
    row = dict.fromkeys(head)
    row.update(
        {
            "BOM No": "BOM-00009", "Item": "Green Tea 100 g", "Name": "Bigger batch",
            "Makes Qty": 2, "Makes Unit": "Carton", "Kind": "Own production",
            "Status": "Active", "Active": "Yes", "Default": "No",
        }
    )  # fmt: skip
    sheets = {
        "BOMs": [head, [row[h] for h in head]],
        "Materials": [got["Materials"][0], ["BOM-00009", "Loose Leaf", 4.8, "Kg", 1]],
    }
    done = send(owner, "boms", sheets, commit=True)
    assert done.status_code == 200, done.json()
    assert done.json()["errors"] == [], done.json()
    with use_tenant(w["tenant"]):
        new = Bom.objects.get(number="BOM-00009")
        assert (new.version, new.is_default, new.lines.get().qty) == (2, False, Decimal("4.8"))
    nxt = call(owner, "post", "boms/", bom(w, "tea", [line(w["loose"], "1", w["kg"])])).json()
    assert nxt["number"] == "BOM-00010"  # carries on after the imported number
