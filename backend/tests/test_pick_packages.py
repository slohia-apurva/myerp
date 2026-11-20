"""Packages on pick lists (Sidharth, 2026-11-20, previews 12a/12b): bags are
picked whole, lowest number first, and only the last is opened; a bag on
another list is not offered; the delivery note uses them up and its cancel
puts them back."""

import datetime
from decimal import Decimal

import pytest

from core.models import Batch, Item, Package, WarehouseLocation
from tenancy.context import use_tenant
from tests.test_delivery_notes import body, books, new_note  # noqa: F401  (fixtures)
from tests.test_pick_lists import new_bin, picked, receive, submit
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    TODAY,
    call,
    owner,
    seller,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

_seq = iter(range(1, 1000))


def bags(w, where, batch, count, each="10"):
    """Numbered bags in a bin, as a goods receipt makes them."""
    with use_tenant(w["tenant"]):
        tea = Item.objects.get(pk=w["tea"])
        lot = Batch.objects.get(item=tea, number=batch)
        loc = WarehouseLocation.objects.get(pk=where)
        made = []
        for n in range(1, count + 1):
            seq = next(_seq)
            made.append(
                Package.objects.create(
                    company_id=w["company"], seq=seq, number=f"PK-{seq:06d}", kind="bag",
                    item=tea, batch=lot, location=loc, qty=Decimal(each), left_qty=Decimal(each),
                    voucher_type="test_receipt", voucher_id=1, voucher_number="T-1",
                    position=n, of_count=count,
                ).number
            )  # fmt: skip
        return made


def packs(pl):
    return [(r["package_number"], r["qty"]) for i in pl["items"] for r in i["rows"]]


def test_whole_bags_first_then_one_opened(seller, world):  # noqa: F811
    soon = TODAY + datetime.timedelta(days=60)
    later = TODAY + datetime.timedelta(days=200)
    other = new_bin(world, "FG-R1-B2")
    receive(world, world["bin"], "20", "A-SOON", soon)
    one, two = bags(world, world["bin"], "A-SOON", 2)
    receive(world, other, "34", "Z-LATE", later)
    three, four, five = bags(world, other, "Z-LATE", 3)  # 30 in bags, 4 loose
    pl = picked(seller, submit(seller, world, cases="1"))  # 24 packets
    assert packs(pl) == [(one, "10"), (two, "10"), (three, "4")]
    row = pl["items"][0]["rows"][2]
    assert row["package_label"] == "Bag 1 of 3" and row["area_name"] == "Finished Goods"
    # The next order is not offered the opened bag, nor what is left in it.
    nxt = picked(seller, submit(seller, world, cases="1"))
    assert packs(nxt) == [(four, "10"), (five, "10"), ("", "4")]
    places = call(seller, "get", f"pick-lists/{nxt['id']}/places/?item={world['tea']}").json()
    assert three not in {p["package_number"] for p in places}
    # Choosing it by hand is refused.
    with use_tenant(world["tenant"]):
        bag = Package.objects.get(number=three)
    line = nxt["items"][0]["order_line"]
    taken = call(
        seller,
        "patch",
        f"pick-lists/{nxt['id']}/",
        {"rows": [{"order_line": line, "location": other, "batch": bag.batch_id,
                   "package": bag.pk, "qty": "2"}]},
    )  # fmt: skip
    assert "on another pick list" in str(taken.json())


def test_delivery_uses_up_bags_and_cancel_restores(seller, owner, books):  # noqa: F811
    w = books
    later = TODAY + datetime.timedelta(days=200)
    receive(w, w["bin"], "30", "A-LATE", later)
    one, two, three = bags(w, w["bin"], "A-LATE", 3)
    pl = picked(seller, submit(seller, w, cases="1"))
    done = call(seller, "post", f"pick-lists/{pl['id']}/submit/", {})
    assert done.status_code == 200, done.json()
    note = new_note(seller, pl)
    assert [b["package_number"] for b in note["lines"][0]["bins"]] == [one, two, three]
    sent = call(seller, "patch", f"delivery-notes/{note['id']}/", body(note, submit=True))
    assert sent.status_code == 200, sent.json()

    def state():
        with use_tenant(w["tenant"]):
            return [
                (p.status, f"{p.left_qty.normalize():f}")
                for p in Package.objects.filter(number__in=[one, two, three]).order_by("seq")
            ]

    assert state() == [("used_up", "0"), ("used_up", "0"), ("part_used", "6")]
    gone = call(owner, "post", f"delivery-notes/{note['id']}/cancel/", {"reason": "Wrong lorry"})
    assert gone.status_code == 200, gone.json()
    assert state() == [("in_stock", "10"), ("in_stock", "10"), ("in_stock", "10")]
