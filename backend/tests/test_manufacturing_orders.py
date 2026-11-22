"""Manufacturing Orders (Sidharth, 2026-11-23, preview 15d in mockups/planning):
the BOM version (default, or another active one), fixed BOM materials and
added ones, Pack Details with the expiry worked out from the Pkd Date, the
Stock Check figures, and what stays open after Submit."""

import datetime
from decimal import Decimal

import pytest

from buying import planning
from core import locks
from core.models import Branch, Item, Party
from manufacturing.models import Bom, ManufacturingOrder
from manufacturing.orders import expiry
from tenancy.context import use_tenant
from tests.test_boms import add_item, bom, line
from tests.test_sales_orders import TODAY, call, owner, stock_in, world  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def url(w):
    return f"companies/{w['company']}/manufacturing-orders/"


def order(w, qty="40", **more):
    return {
        "branch": w["branch"],
        "order_date": TODAY.isoformat(),
        "item": w["tea"],
        "qty": qty,
        "unit": w["case"],
        "start_date": TODAY.isoformat(),
        "due_date": (TODAY + datetime.timedelta(days=3)).isoformat(),
        **more,
    }


def setup_boms(owner, w):  # noqa: F811
    pouch = add_item(w, "Pouch Laminate", unit="pcs")
    v1 = call(owner, "post", "boms/", bom(w, "tea", [line(w["loose"], "2.4", w["kg"], "0.5")]))
    lines = [line(w["loose"], "2.4", w["kg"], "0.5"), line(pouch, "24", w["pcs"], "2")]
    v2 = call(owner, "post", "boms/", bom(w, "tea", lines, name="New pouch", packing_notes="12 µ"))
    assert v1.status_code == v2.status_code == 201, (v1.json(), v2.json())
    return v1.json(), v2.json(), pouch


def test_an_order_takes_the_default_version_and_fixes_its_materials(owner, world):  # noqa: F811
    w = world
    v1, v2, pouch = setup_boms(owner, w)
    stock_in(w, "store", "60", item="loose")
    made = call(owner, "post", url(w), order(w, mrp="120", batch_no="AGT-1"))
    assert made.status_code == 201, made.json()
    mo = made.json()
    assert (mo["bom"], mo["bom_default"], mo["status"], mo["number"]) == (
        v1["id"],
        True,
        "draft",
        "",
    )
    [blend] = mo["lines"]
    # 2.4 kg a carton for 40 cartons, plus 0.5 %.
    assert (blend["required"], blend["from_bom"], blend["free"]) == ("96.48", True, "60")
    assert blend["short"] and mo["stock_qty"] == "960"
    with use_tenant(w["tenant"]):
        head = Branch.objects.get(pk=w["branch"])
        assert planning.reserved(head, [w["loose"]])[w["loose"]] == Decimal("96.48")
        assert planning.incoming(head, [w["tea"]])[w["tea"]] == 960  # cartons of 24
    # Another version, and a material added on the order.
    extra = [{"item": pouch, "unit": w["pcs"], "per_unit": "1"}]
    body = order(w, bom=v2["id"], added=extra, packing_notes="12 µ")
    changed = call(owner, "patch", f"manufacturing-orders/{mo['id']}/", body)
    assert changed.status_code == 400 and "already on the order" in str(changed.json())
    sachet = add_item(w, "Silica Sachet", unit="pcs")
    body["added"] = [{"item": sachet, "unit": w["pcs"], "per_unit": "1"}]
    mo = call(owner, "patch", f"manufacturing-orders/{mo['id']}/", body).json()
    assert [(ln["item_name"], ln["required"], ln["from_bom"]) for ln in mo["lines"]] == [
        ("Loose Leaf", "96.48", True),
        ("Pouch Laminate", "979.2", True),  # 24 x 40 + 2 %
        ("Silica Sachet", "40", False),
    ]
    assert mo["packing_notes"] == "12 µ"
    # Submit: the branch, item, quantity and version stay; added materials stay open.
    done = call(owner, "post", f"manufacturing-orders/{mo['id']}/submit/").json()
    assert done["status"] == "not_started" and "/MO/" in done["number"]
    bigger = call(owner, "patch", f"manufacturing-orders/{mo['id']}/", {**body, "qty": "50"})
    assert bigger.status_code == 400 and "keeps its branch" in str(bigger.json())
    body["added"] = [{"item": sachet, "unit": w["pcs"], "per_unit": "2"}]
    more = call(owner, "patch", f"manufacturing-orders/{mo['id']}/", body)
    assert more.status_code == 200, more.json()
    assert more.json()["lines"][2]["required"] == "80" and more.json()["status"] == "not_started"
    # The version is now in use: its materials stop changing.
    with use_tenant(w["tenant"]):
        assert locks.uses("bom", Bom.objects.get(pk=v2["id"])) == ["1 manufacturing order"]
    stuck = call(owner, "patch", f"boms/{v2['id']}/", {"lines": [line(pouch, "25", w["pcs"])]})
    assert stuck.status_code == 400 and "Duplicate as new version" in str(stuck.json())
    pdf = call(owner, "get", f"manufacturing-orders/{mo['id']}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    closed = call(owner, "post", f"manufacturing-orders/{mo['id']}/close/").json()
    assert closed["status"] == "closed"
    with use_tenant(w["tenant"]):
        assert planning.incoming(head, [w["tea"]]).get(w["tea"], 0) == 0


def test_job_work_needs_the_customer_and_customer_goods_need_job_work(owner, world):  # noqa: F811
    w = world
    theirs = add_item(w, "OHF CTC", default_request_type=Item.CUSTOMER_PROVIDED)
    setup_boms(owner, w)
    job = call(
        owner, "post", "boms/", bom(w, "tea", [line(theirs, "2.4", w["kg"])], kind="job_work")
    ).json()
    refused = call(owner, "post", url(w), order(w, bom=job["id"]))
    assert refused.status_code == 400 and "needs the customer" in str(refused.json())
    with use_tenant(w["tenant"]):
        party = Party.objects.get(name="Organic Harvest Foods")
    made = call(owner, "post", url(w), order(w, bom=job["id"], customer=party.pk))
    assert made.status_code == 201, made.json()
    assert made.json()["lines"][0]["source_text"] == "Customer's stock"
    own = call(
        owner, "post", url(w), order(w, added=[{"item": theirs, "unit": w["kg"], "per_unit": "1"}])
    )
    assert own.status_code == 400 and "only a job work order" in str(own.json())


def test_pack_details_and_the_expiry_date(owner, world):  # noqa: F811
    w = world
    setup_boms(owner, w)
    assert expiry(datetime.date(2026, 11, 24), 18, Item.MONTHS) == datetime.date(2028, 5, 23)
    assert expiry(datetime.date(2026, 11, 24), 30, Item.DAYS) == datetime.date(2026, 12, 23)
    body = order(
        w, pkd_date="2026-11-24", best_before_value=18, best_before_unit="months",
        usp="1.20", usp_per=w["kg"],
    )  # fmt: skip
    mo = call(owner, "post", url(w), body).json()
    assert (mo["expiry_date"], mo["usp"], mo["usp_per_name"]) == (
        datetime.date(2028, 5, 23).isoformat(), "1.20", "kg",
    )  # fmt: skip
    form = call(owner, "get", f"{url(w)}form/").json()
    tea = next(i for i in form["makes"] if i["id"] == w["tea"])
    assert [v["is_default"] for v in tea["versions"]] == [True, False]
    cancel = call(owner, "post", f"manufacturing-orders/{mo['id']}/cancel/", {"reason": "Trial"})
    assert cancel.json()["status"] == "cancelled"
    with use_tenant(w["tenant"]):
        assert ManufacturingOrder.objects.get(pk=mo["id"]).cancel_reason == "Trial"
