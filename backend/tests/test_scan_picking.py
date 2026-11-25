"""Scan Picking (Sidharth, 2026-11-25, preview mockups/scan-picking): package
labels tick their rows, a free bag of the same item and batch can be taken
instead, unit barcodes count loose goods, rows can be ticked by hand, and wrong
scans tick nothing."""

import datetime

import pytest

from core.models import ItemUnit, Package
from tenancy.context import use_tenant
from tests.test_pick_lists import picked, receive, submit
from tests.test_pick_packages import bags
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    owner,
    seller,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

LATER = TODAY + datetime.timedelta(days=200)


def scan(client, pl, code):
    r = call(client, "post", f"pick-lists/{pl['id']}/scans/", {"code": code})
    assert r.status_code == 200, r.json()
    return r.json()


def test_packages_tick_rows_and_wrong_scans_do_not(seller, world):  # noqa: F811
    receive(world, world["bin"], "30", "A-LATE", LATER)
    one, two, three = bags(world, world["bin"], "A-LATE", 3)
    pl = picked(seller, submit(seller, world, cases="1"))  # 24: 10 + 10 + 4 of the third
    where = f"companies/{world['company']}/scan-picking/find/?code={pl['number'].lower()}"
    assert call(seller, "get", where).json()["id"] == pl["id"]
    got = scan(seller, pl, one.lower().replace("-", ""))  # a scanner may drop the dash
    assert got["result"] == "ok" and got["list"]["done"] == 1
    again = scan(seller, pl, one)
    assert again["result"] == "warn" and "already checked" in again["message"]
    junk = scan(seller, pl, "XYZ-1")
    assert junk["result"] == "wrong" and junk["list"]["wrong"] == 1
    assert scan(seller, pl, "PK-999999")["result"] == "wrong"
    scan(seller, pl, two)
    done = scan(seller, pl, three)["list"]
    assert (done["done"], done["total"], done["scanned"], done["wrong"]) == (3, 3, 3, 2)
    view = picked(seller, {"pick_lists": [pl]})
    assert view["check"]["done"] == 3
    assert view["items"][0]["rows"][0]["verified"]["how"] == "Scanned"
    # Submitted, the list cannot be scanned.
    assert call(seller, "post", f"pick-lists/{pl['id']}/submit/", {}).status_code == 200
    late = call(seller, "post", f"pick-lists/{pl['id']}/scans/", {"code": one})
    assert late.status_code == 400


def test_same_batch_bag_offered_and_swapped(seller, world):  # noqa: F811
    receive(world, world["bin"], "40", "A-LATE", LATER)
    one, two, three, four = bags(world, world["bin"], "A-LATE", 4)
    pl = picked(seller, submit(seller, world, cases="1"))  # one, two, 4 of three
    offer = scan(seller, pl, four)
    assert offer["result"] == "offer" and offer["offer"]["instead_of"] == one
    swap = call(seller, "post", f"pick-lists/{pl['id']}/scans/swap/", offer["offer"])
    assert swap.status_code == 200, swap.json()
    rows = swap.json()["list"]["rows"]
    mine = next(r for r in rows if r["package_number"] == four)
    assert mine["done"] and mine["how"] == f"Swapped for {one}"
    assert one not in {r["package_number"] for r in rows}
    # A bag of another batch is refused.
    receive(world, world["bin"], "10", "B-OTHER", LATER + datetime.timedelta(days=5))
    (other,) = bags(world, world["bin"], "B-OTHER", 1)
    bad = scan(seller, pl, other)
    assert bad["result"] == "wrong" and "batch A-LATE" in bad["message"]


def test_unit_barcode_and_by_hand_for_loose_goods(seller, world):  # noqa: F811
    receive(world, world["bin"], "60")
    with use_tenant(world["tenant"]):
        case = ItemUnit.objects.get(item_id=world["tea"], unit_id=world["case"])
        case.barcode = "8901234567890"
        case.save(update_fields=["barcode"])
        assert not Package.objects.exists()
    pl = picked(seller, submit(seller, world, cases="2"))  # 48 packets, no packages
    got = scan(seller, pl, "8901234567890")
    assert got["result"] == "ok" and "24 pkt to go" in got["message"]
    row = got["list"]["rows"][0]
    assert (row["got"], row["done"]) == ("24", False)
    hand = f"pick-lists/{pl['id']}/scans/hand/"
    assert call(seller, "post", hand, {"row": row["id"], "qty": "30"}).status_code == 400
    ticked = call(seller, "post", hand, {"row": row["id"], "qty": "24"})
    assert ticked.status_code == 200, ticked.json()
    row = ticked.json()["list"]["rows"][0]
    assert row["done"] and "by item barcode" in row["how"] and "By hand" in row["how"]
    assert scan(seller, pl, "8901234567890")["result"] == "warn"
    # Start again clears the ticks.
    cleared = call(seller, "delete", f"pick-lists/{pl['id']}/scans/")
    assert cleared.json()["done"] == 0
