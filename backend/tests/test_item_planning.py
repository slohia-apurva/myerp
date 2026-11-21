"""Stock Planning on an item (Sidharth, 2026-11-21): a Preferred Supplier, a
Main Fulfilment, and one line per branch with that branch's fulfilment
(buy, make, transfer from another branch of the same company, or the
customer's goods), safety stock and the level a refill brings it up to."""

import pytest

from core.companies import create_company
from core.models import Branch, Party
from tenancy.context import use_tenant
from tests.test_items import (  # noqa: F401  (fixtures)
    accountant,
    call,
    company,
    make,
    unit,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture
def places(alpha, company):  # noqa: F811
    """Sankrail-1 (head office), Sankrail-2 and a no-stock office of one company,
    and a branch of a second company."""
    with use_tenant(alpha):
        head = Branch.objects.get(company_id=company, is_head_office=True)
        two = Branch.objects.create(company_id=company, name="Sankrail-2", state_code="27")
        office = Branch.objects.create(
            company_id=company, name="Office", state_code="27", no_stock=True
        )
        other = create_company(name="Other Foods Pvt Ltd", state_code="19")
        far = Branch.objects.get(company=other, is_head_office=True)
        return {"head": head.pk, "two": two.pk, "office": office.pk, "far": far.pk}


@pytest.fixture
def supplier(alpha):
    with use_tenant(alpha):
        return Party.objects.create(name="Tea Leaf Traders", vendor_number="VEND-0001").pk


def line(branch, fulfilment="purchase", safety="600", up_to="2400", **more):
    return {
        "branch": branch,
        "fulfilment": fulfilment,
        "safety_qty": safety,
        "order_up_to": up_to,
        **more,
    }


def test_branch_lines_and_preferred_supplier_are_saved(accountant, unit, places, supplier):  # noqa: F811
    made = make(
        accountant,
        unit,
        default_request_type="manufacture",
        preferred_supplier=supplier,
        plans=[
            line(places["head"], "manufacture"),
            line(
                places["two"],
                "transfer",
                "240",
                "960",
                transfer_from=places["head"],
                transfer_days=1,
            ),
        ],
    )
    assert made.status_code == 201, made.json()
    item = made.json()
    assert item["preferred_supplier_name"] == "Tea Leaf Traders"
    by = {p["branch"]: p for p in item["plans"]}
    assert by[places["two"]]["transfer_from_name"] is not None
    assert by[places["two"]]["transfer_days"] == 1
    assert by[places["head"]]["transfer_from"] is None
    # a later save replaces the lines
    path = f"items/{item['id']}/"
    again = call(accountant, "patch", path, {"plans": [line(places["head"])]})
    assert again.status_code == 200, again.json()
    assert [p["fulfilment"] for p in again.json()["plans"]] == ["purchase"]
    # a save without "plans" keeps them
    kept = call(accountant, "patch", path, {"notes": "x"}).json()
    assert len(kept["plans"]) == 1


def test_main_fulfilment_is_needed_with_branch_lines(accountant, unit, places):  # noqa: F811
    refused = make(accountant, unit, plans=[line(places["head"])])
    assert refused.status_code == 400
    assert "default_request_type" in refused.json()
    item = make(
        accountant, unit, default_request_type="purchase", plans=[line(places["head"])]
    ).json()
    cleared = call(accountant, "patch", f"items/{item['id']}/", {"default_request_type": ""})
    assert cleared.status_code == 400


@pytest.mark.parametrize(
    "plans, says",
    [
        (lambda p: [line(p["head"]), line(p["head"])], "listed twice"),
        (lambda p: [line(p["office"])], "keeps no stock"),
        (lambda p: [line(p["two"], "transfer")], "transfers from"),
        (lambda p: [line(p["two"], "transfer", transfer_from=p["two"])], "from itself"),
        (lambda p: [line(p["two"], "transfer", transfer_from=p["far"])], "same company"),
        (lambda p: [line(p["head"], safety="600", up_to="100")], "below the safety stock"),
        (
            lambda p: [
                line(p["head"], "transfer", transfer_from=p["two"]),
                line(p["two"], "transfer", transfer_from=p["head"]),
            ],
            "circle",
        ),
    ],
)
def test_bad_branch_lines_are_refused(accountant, unit, places, plans, says):  # noqa: F811
    refused = make(accountant, unit, default_request_type="purchase", plans=plans(places))
    assert refused.status_code == 400
    assert says in str(refused.json()["plans"])


def test_transfer_details_are_cleared_on_other_lines(accountant, unit, places):  # noqa: F811
    item = make(
        accountant,
        unit,
        default_request_type="purchase",
        plans=[line(places["head"], transfer_from=places["two"], transfer_days=3)],
    ).json()
    assert item["plans"][0]["transfer_from"] is None
    assert item["plans"][0]["transfer_days"] is None


def test_preferred_supplier_must_be_a_supplier(accountant, unit, alpha):  # noqa: F811
    with use_tenant(alpha):
        customer = Party.objects.create(name="Organic Harvest", customer_number="CUST-0001").pk
    refused = make(accountant, unit, preferred_supplier=customer)
    assert refused.status_code == 400
    assert "not a supplier" in str(refused.json())


def test_item_without_stock_has_no_planning(accountant, unit, places):  # noqa: F811
    refused = make(
        accountant,
        unit,
        maintain_stock=False,
        default_request_type="purchase",
        plans=[line(places["head"])],
    )
    assert refused.status_code == 400


def test_plan_branches_lists_stock_branches_of_every_company(accountant, places):  # noqa: F811
    rows = call(accountant, "get", "items/plan-branches/").json()
    ids = {r["id"] for r in rows}
    assert {places["head"], places["two"], places["far"]} <= ids
    assert places["office"] not in ids


def test_activity_shows_the_lines(accountant, unit, places, alpha):  # noqa: F811
    item = make(
        accountant, unit, default_request_type="purchase", plans=[line(places["head"])]
    ).json()
    log = call(accountant, "get", f"audit/?type=item&id={item['id']}").json()
    assert "safety 600" in str(log)
