# ruff: noqa: F811  (the purchase order fixtures are imported and used as arguments)
"""Insurance policies (Sidharth, 2026-11-18, previews 93a-93d): the master,
its top-ups and balance, and the policy on a purchase order."""

import datetime

import pytest

from core.models import Notification
from insurance.models import InsurancePolicy
from tenancy.context import use_tenant
from tests.test_purchase_orders import (  # noqa: F401  (fixtures)
    TODAY,
    add_supplier,
    buyer,
    call,
    client_for,
    order,
    owner,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

YEAR_START = TODAY - datetime.timedelta(days=30)
YEAR_END = TODAY + datetime.timedelta(days=300)


@pytest.fixture
def insurer(owner, world):
    return add_supplier(owner, world["company"], "New India Assurance", "AAACN1234F", state="27")


def policy(insurer, **more):
    return {
        "number": "2414/0005873/000/00",
        "insurer": insurer,
        "kind": "marine_inland",
        "covers": "both",
        "valid_from": YEAR_START.isoformat(),
        "valid_to": YEAR_END.isoformat(),
        "sum_insured": "200000.00",
        "declare_to": "marine@insurer.example; broker@insurer.example",
        **more,
    }


def add_policy(client, world, insurer, **more):
    made = call(
        client, "post", f"companies/{world['company']}/insurance-policies/", policy(insurer, **more)
    )
    assert made.status_code == 201, made.json()
    return made.json()


def test_a_policy_is_saved_with_its_top_ups_and_cover(owner, world, insurer):
    p = add_policy(
        owner,
        world,
        insurer,
        top_ups=[
            {"date": TODAY.isoformat(), "endorsement_no": "END/01", "amount": "150000"},
        ],
    )
    assert p["insurer_name"] == "New India Assurance"
    setup = call(owner, "get", f"companies/{world['company']}/insurance-policies/setup/").json()
    assert "New India Assurance" in [s["name"] for s in setup["insurers"]]
    assert setup["supplier_group"]
    assert p["kind_label"] == "Marine (inland transit)"
    assert p["declare_to"] == "marine@insurer.example, broker@insurer.example"
    assert (p["cover"], p["used"], p["balance"]) == ("350000.00", "0", "350000.00")
    assert len(p["top_ups"]) == 1


def test_policy_numbers_are_unique_in_a_company(owner, world, insurer):
    add_policy(owner, world, insurer)
    again = call(
        owner,
        "post",
        f"companies/{world['company']}/insurance-policies/",
        policy(insurer, number=" 2414/0005873/000/00 "),
    )
    assert again.status_code == 400
    assert "already has policy number" in again.json()["number"][0]
    assert again.json()["existing"]["kind"] == "insurance_policy"


def test_the_insurer_is_a_supplier_and_dates_and_top_ups_are_checked(owner, world, insurer):
    url = f"companies/{world['company']}/insurance-policies/"
    bad = call(owner, "post", url, policy(world["shop"]))
    assert "suppliers" in bad.json()["insurer"][0]
    bad = call(
        owner,
        "post",
        url,
        policy(insurer, valid_to=(YEAR_START - datetime.timedelta(1)).isoformat()),
    )
    assert "ends before it starts" in bad.json()["valid_to"][0]
    late = (YEAR_END + datetime.timedelta(days=5)).isoformat()
    bad = call(owner, "post", url, policy(insurer, top_ups=[{"date": late, "amount": "10"}]))
    assert "outside the policy" in bad.json()["top_ups"][0]
    bad = call(owner, "post", url, policy(insurer, declare_to="not an email"))
    assert "not an email" in bad.json()["declare_to"][0]


def test_only_marine_policies_can_be_a_default_and_one_default_per_side(owner, world, insurer):
    url = f"companies/{world['company']}/insurance-policies/"
    fire = call(
        owner, "post", url, policy(insurer, number="FIRE-1", kind="fire", default_for="purchase")
    )
    assert "marine" in fire.json()["default_for"][0]
    first = add_policy(owner, world, insurer, default_for="both")
    add_policy(owner, world, insurer, number="MAR-2", default_for="purchase")
    rows = {p["number"]: p for p in call(owner, "get", url).json()}
    assert rows[first["number"]]["default_for"] == "sales"
    assert rows["MAR-2"]["default_for"] == "purchase"


def test_an_order_insured_by_us_takes_the_policy_and_insured_value(buyer, owner, world, insurer):
    p = add_policy(owner, world, insurer, default_for="purchase")
    setup = call(buyer, "get", f"companies/{world['company']}/purchase-orders/setup/").json()
    assert [r["number"] for r in setup["insurance_policies"]] == [p["number"]]
    assert setup["insurance_policies"][0]["is_default"] is True
    made = call(
        buyer,
        "post",
        f"companies/{world['company']}/purchase-orders/",
        order(world, insured_by="us", insurance_policy=p["id"]),
    )
    assert made.status_code == 201, made.json()
    po = made.json()
    # Total 94,933.00 plus 10%.
    assert po["total"] == "94933.00"
    assert (po["insured_by"], po["insured_value"]) == ("us", "104426.30")
    assert po["insurance_policy_label"].startswith("2414/0005873/000/00 · New India Assurance")
    # Saved by the supplier: no policy is kept.
    po2 = call(
        buyer,
        "post",
        f"companies/{world['company']}/purchase-orders/",
        order(world, insured_by="supplier", insurance_policy=p["id"]),
    ).json()
    assert (po2["insurance_policy"], po2["insured_value"]) == (None, "0.00")


def test_an_order_needs_a_valid_transit_policy(buyer, owner, world, insurer):
    url = f"companies/{world['company']}/purchase-orders/"
    none = call(buyer, "post", url, order(world, insured_by="us"))
    assert "Pick the policy" in none.json()["insurance_policy"][0]
    fire = add_policy(owner, world, insurer, number="FIRE-1", kind="fire")
    bad = call(buyer, "post", url, order(world, insured_by="us", insurance_policy=fire["id"]))
    assert "not a transit one" in bad.json()["insurance_policy"][0]
    sales = add_policy(owner, world, insurer, number="EXP-1", kind="marine_export", covers="sales")
    bad = call(buyer, "post", url, order(world, insured_by="us", insurance_policy=sales["id"]))
    assert "does not cover purchases" in bad.json()["insurance_policy"][0]
    old = add_policy(
        owner,
        world,
        insurer,
        number="OLD-1",
        valid_from=(TODAY - datetime.timedelta(days=400)).isoformat(),
        valid_to=(TODAY - datetime.timedelta(days=40)).isoformat(),
    )
    bad = call(buyer, "post", url, order(world, insured_by="us", insurance_policy=old["id"]))
    assert "runs from" in bad.json()["insurance_policy"][0]


def test_submitted_orders_use_up_the_cover_and_low_balance_tells_owners(
    alpha,
    buyer,
    owner,
    world,
    insurer,
):
    p = add_policy(owner, world, insurer, sum_insured="150000", alert_below="50000")
    url = f"companies/{world['company']}/purchase-orders/"
    po = call(buyer, "post", url, order(world, insured_by="us", insurance_policy=p["id"])).json()
    # A draft uses nothing yet.
    got = call(owner, "get", f"companies/{world['company']}/insurance-policies/").json()[0]
    assert got["used"] == "0"
    sent = call(buyer, "post", f"purchase-orders/{po['id']}/submit/")
    assert sent.status_code == 200, sent.json()
    got = call(owner, "get", f"companies/{world['company']}/insurance-policies/").json()[0]
    assert (got["used"], got["balance"], got["low"]) == ("104426.30", "45573.70", True)
    assert got["lock"]["in_use"] == ["1 purchase order"]
    with use_tenant(alpha):
        notes = list(Notification.objects.filter(title__contains="2414/0005873/000/00"))
    assert notes and all("top-up" in n.body for n in notes)
    # The insurer and type are locked now; the number and cover stay open.
    locked = call(owner, "patch", f"insurance-policies/{p['id']}/", {"kind": "fire"})
    assert "in use" in locked.json()["kind"][0]
    ok = call(owner, "patch", f"insurance-policies/{p['id']}/", {"sum_insured": "500000"})
    assert ok.status_code == 200, ok.json()


def test_a_stop_policy_refuses_an_order_beyond_its_balance(alpha, buyer, owner, world, insurer):
    p = add_policy(owner, world, insurer, sum_insured="100000", when_out="stop")
    url = f"companies/{world['company']}/purchase-orders/"
    po = call(buyer, "post", url, order(world, insured_by="us", insurance_policy=p["id"])).json()
    sent = call(buyer, "post", f"purchase-orders/{po['id']}/submit/")
    assert sent.status_code == 400
    assert "top-up" in sent.json()["insurance_policy"][0]
    with use_tenant(alpha):
        assert InsurancePolicy.objects.get(pk=p["id"]).purchase_orders.get().status == "draft"
    top = call(
        owner,
        "patch",
        f"insurance-policies/{p['id']}/",
        {"top_ups": [{"date": TODAY.isoformat(), "endorsement_no": "END/01", "amount": "50000"}]},
    )
    assert top.json()["cover"] == "150000.00"
    assert call(buyer, "post", f"purchase-orders/{po['id']}/submit/").status_code == 200


def test_policies_import_and_export_with_their_top_ups(owner, world, insurer):
    add_policy(
        owner,
        world,
        insurer,
        top_ups=[{"date": TODAY.isoformat(), "endorsement_no": "END/01", "amount": "150000"}],
    )
    got = call(
        owner,
        "get",
        f"exchange/insurance-policies/?as=xlsx&company={world['company']}",
    )
    assert got.status_code == 200
