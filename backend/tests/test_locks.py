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


def test_credit_terms_in_use_keep_their_parts(accountant, company, alpha):
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
    refused = call(accountant, "patch", f"credit-terms/{term['id']}/", {"parts": again})
    assert refused.status_code == 400 and "parts" in refused.json()
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
