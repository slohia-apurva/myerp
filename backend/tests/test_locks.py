"""Masters in use: key fields cannot change once there are entries against
them (Sidharth, 2026-11-11); names, notes and Disable stay open."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core import locks
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
def company(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurvam Organics LLP", state_code="27").pk


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def unit_ids(client):
    return {u["name"]: u["id"] for u in call(client, "get", "units/").json()}


def make_item(client, name="Jaggery", stock="Packet"):
    ids = unit_ids(client)
    made = call(
        client,
        "post",
        "items/",
        {"name": name, "stock_unit": ids[stock], "units": [], "hsn": "0902"},
    )
    assert made.status_code == 201, made.json()
    return made.json(), ids


def test_a_unit_in_use_keeps_its_gst_code_but_can_be_renamed_and_disabled(accountant, company):
    item, ids = make_item(accountant)
    packet = ids["Packet"]

    refused = call(accountant, "patch", f"units/{packet}/", {"gst_code": "BOX"})
    assert refused.status_code == 400
    assert "gst_code" in refused.json()
    assert "1 item" in refused.json()["gst_code"][0]
    assert (
        call(accountant, "patch", f"units/{packet}/", {"whole_numbers": False}).status_code == 400
    )

    # Sending the same values back is fine, and names stay open.
    ok = call(
        accountant,
        "patch",
        f"units/{packet}/",
        {"gst_code": "PAC", "whole_numbers": True, "name": "Pack"},
    )
    assert ok.status_code == 200, ok.json()
    assert call(accountant, "patch", f"units/{packet}/", {"is_active": False}).status_code == 200


def test_a_unit_nobody_uses_can_change(accountant, company):
    carton = unit_ids(accountant)["Carton"]
    assert call(accountant, "patch", f"units/{carton}/", {"gst_code": "BOX"}).status_code == 200


def test_credit_term_parts_stay_editable_when_in_use(accountant, company, alpha):
    made = call(
        accountant,
        "post",
        "credit-terms/",
        {"name": "Lock test terms", "parts": [{"event": "bill", "days": 30, "percent": "100"}]},
    )
    assert made.status_code == 201, made.json()
    term = made.json()
    parts = [{"event": "bill", "days": 45, "percent": "100"}]
    # Not used yet: parts can change.
    assert (
        call(accountant, "patch", f"credit-terms/{term['id']}/", {"parts": parts}).status_code
        == 200
    )

    from core.models import CreditTerm, Party

    with use_tenant(alpha):
        Party.objects.create(name="Buyer", credit_term=CreditTerm.objects.get(pk=term["id"]))
    again = [{"event": "bill", "days": 60, "percent": "100"}]
    # Parts stay editable even when used (Sidharth, 2026-11-13).
    changed = call(accountant, "patch", f"credit-terms/{term['id']}/", {"parts": again})
    assert changed.status_code == 200, changed.json()
    same = call(accountant, "patch", f"credit-terms/{term['id']}/", {"parts": parts, "notes": "x"})
    assert same.status_code == 200, same.json()


def test_a_registered_use_locks_an_item(accountant, company):
    item, ids = make_item(accountant)
    url = f"items/{item['id']}/"
    assert call(accountant, "patch", url, {"hsn": "1701"}).status_code == 200

    fn = lambda record: "2 stock entries"  # noqa: E731
    locks.register("item", fn)
    try:
        refused = call(accountant, "patch", url, {"hsn": "0910"})
        assert refused.status_code == 400
        assert "2 stock entries" in refused.json()["hsn"][0]
        assert call(accountant, "patch", url, {"stock_unit": ids["Nos"]}).status_code == 400
        assert call(accountant, "patch", url, {"notes": "fine"}).status_code == 200
        assert call(accountant, "patch", url, {"is_active": False}).status_code == 200
    finally:
        locks._USES["item"].remove(fn)


def test_an_item_in_use_moves_only_within_its_top_level_group(accountant, company):
    def group(name, parent=None):
        made = call(accountant, "post", "item-groups/", {"name": name, "parent": parent})
        assert made.status_code == 201, made.json()
        return made.json()["id"]

    tea, spice = group("Tea"), group("Spice")
    green, black, whole = group("Green tea", tea), group("Black tea", tea), group("Whole", spice)
    ids = unit_ids(accountant)
    made = call(
        accountant,
        "post",
        "items/",
        {"name": "Darjeeling", "stock_unit": ids["Packet"], "hsn": "0902", "item_group": green},
    )
    assert made.status_code == 201, made.json()
    item = made.json()
    url = f"items/{item['id']}/"
    assert item["lock"] == {"in_use": [], "locked": []}
    # Not used yet: any group.
    assert call(accountant, "patch", url, {"item_group": whole}).status_code == 200
    assert call(accountant, "patch", url, {"item_group": green}).status_code == 200

    fn = lambda record: "2 stock entries"  # noqa: E731
    locks.register("item", fn)
    try:
        assert call(accountant, "patch", url, {"item_group": black}).status_code == 200
        refused = call(accountant, "patch", url, {"item_group": whole})
        assert refused.status_code == 400 and "Tea" in refused.json()["item_group"][0]
        lock = call(accountant, "get", url).json()["lock"]
        assert lock["in_use"] == ["2 stock entries"] and "stock_unit" in lock["locked"]
        # The list leaves "in use" out: a dozen queries per item is too slow for
        # 12,000 items (Sidharth's ERPNext import, 2026-11-24). One item has it.
        asked = []
        locks.register("item", lambda record: asked.append(record) or "")
        listed = call(accountant, "get", "items/").json()
        assert next(i for i in listed if i["id"] == item["id"])["lock"] is None
        assert asked == []
        zipped = accountant.get("/api/v1/items/", HTTP_HOST=HOST, HTTP_ACCEPT_ENCODING="gzip, br")
        assert zipped["Content-Encoding"] == "gzip"
        import gzip
        import json

        assert json.loads(gzip.decompress(zipped.content)) == listed
        locks._USES["item"].pop()
        assert call(accountant, "get", "items/999999/").status_code == 404
    finally:
        locks._USES["item"].remove(fn)


def test_a_group_in_use_moves_only_within_its_top_level_group(accountant, company):
    def group(name, parent=None):
        return call(accountant, "post", "item-groups/", {"name": name, "parent": parent}).json()

    tea, spice = group("Tea"), group("Spice")
    green, black = group("Green tea", tea["id"]), group("Black tea", tea["id"])
    ids = unit_ids(accountant)
    leaf = group("Leaf", green["id"])
    call(
        accountant,
        "post",
        "items/",
        {
            "name": "Darjeeling",
            "stock_unit": ids["Packet"],
            "hsn": "0902",
            "item_group": leaf["id"],
        },
    )
    # "Green tea" is in use (an item sits below it): it may move under "Black tea" but not "Spice".
    ok = call(accountant, "patch", f"item-groups/{green['id']}/", {"parent": black["id"]})
    assert ok.status_code == 200, ok.json()
    out = call(accountant, "patch", f"item-groups/{green['id']}/", {"parent": spice["id"]})
    assert out.status_code == 400 and "Tea" in out.json()["parent"][0]
    top = call(accountant, "patch", f"item-groups/{green['id']}/", {"parent": None})
    assert top.status_code == 400


def test_a_posted_ledger_keeps_its_group_but_opening_balances_stay_editable(accountant, company):
    detail = call(accountant, "get", f"companies/{company}/").json()
    groups = {g["name"]: g["id"] for g in detail["ledger_groups"]}
    cash = groups["Cash-in-Hand"]
    other = groups["Bank Accounts"]
    made = call(
        accountant,
        "post",
        f"companies/{company}/ledgers/",
        {"name": "Petty cash", "group": cash, "opening_amount": "100", "opening_side": "dr"},
    )
    assert made.status_code == 201, made.json()
    url = f"ledgers/{made.json()['id']}/"
    # Opening balances are set-up data: still editable, group can still move.
    assert call(accountant, "patch", url, {"opening_amount": "150"}).status_code == 200

    fn = lambda record: "5 postings"  # noqa: E731
    locks.register("ledger", fn)
    try:
        refused = call(accountant, "patch", url, {"group": other})
        assert refused.status_code == 400 and "5 postings" in refused.json()["group"][0]
        assert call(accountant, "patch", url, {"name": "Cash box"}).status_code == 200
    finally:
        locks._USES["ledger"].remove(fn)
