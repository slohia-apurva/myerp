"""Purchase orders: drafts, GST, submit and number, cancel, rates, and what locks."""

import datetime

import pytest
from django.test import Client

from accounts.models import Role, User
from audit.models import AuditEntry
from core import locks
from core.companies import create_company
from core.india import gstin_check_char
from core.models import (
    Brand,
    Company,
    Item,
    ItemGroup,
    ItemGstRate,
    ItemUnit,
    Ledger,
    PartyItemPrice,
    PriceList,
    PriceListLine,
    Unit,
)
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HOST = "alpha.localhost"
TODAY = datetime.date.today()


def gstin(state: str, pan: str = "AAPFU0939F") -> str:
    first14 = f"{state}{pan}1Z"
    return first14 + gstin_check_char(first14)


def client_for(alpha, email: str, role: str) -> Client:
    with use_tenant(alpha):
        user = User.objects.create_user(email, full_name=email.split("@")[0].title())
        user.roles.set(Role.objects.filter(code=role))
        client = Client()
        client.force_login(user)
    return client


@pytest.fixture
def owner(alpha):
    return client_for(alpha, "owner@x.in", "owner")


@pytest.fixture
def buyer(alpha):
    return client_for(alpha, "buyer@x.in", "purchase")


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def add_supplier(
    client, company, name, pan="", state="27", gst_type="regular", side="Sundry Creditors"
):
    detail = call(client, "get", f"companies/{company}/").json()
    group = next(g["id"] for g in detail["ledger_groups"] if g["name"] == side)
    party = {"gst_type": gst_type, "state_code": state}
    if gst_type == "regular":
        party["gstin"] = gstin(state, pan)
    made = call(
        client,
        "post",
        f"companies/{company}/ledgers/",
        {"name": name, "group": group, "party": party},
    )
    assert made.status_code == 201, made.json()
    return made.json()["id"]


@pytest.fixture
def world(alpha, owner):
    with use_tenant(alpha):
        company = create_company(name="Apurvam Organics LLP", state_code="27")
        branch = company.branches.get(is_head_office=True)
        kg, pack = Unit.objects.get(name="Kilogram"), Unit.objects.get(name="Packet")
        more = {
            "hsn": "0902",
            "item_group": ItemGroup.objects.get_or_create(name="General")[0],
            "brand": Brand.objects.get_or_create(name="General brand")[0],
        }
        tea = Item.objects.create(item_number="ITEM-71", name="CTC Tea", stock_unit=kg, **more)
        ItemUnit.objects.create(item=tea, unit=kg, factor=1, whole_numbers=False)
        box = Item.objects.create(item_number="ITEM-72", name="Tea Box", stock_unit=pack, **more)
        ItemUnit.objects.create(item=box, unit=pack, factor=1, whole_numbers=True)
        for item, rate in ((tea, "5"), (box, "18")):
            ItemGstRate.objects.create(item=item, valid_from=TODAY.replace(day=1), rate=rate)
    local = add_supplier(owner, company.pk, "Darjeeling Tea Traders", "AAPFD1234F", state="27")
    far = add_supplier(owner, company.pk, "Assam Leaf Estates", "AAPFA1234F", state="18")
    small = add_supplier(owner, company.pk, "Village Farmer", gst_type="unregistered")
    shop = add_supplier(
        owner, company.pk, "Fresh Mart", gst_type="unregistered", side="Sundry Debtors"
    )
    return {
        "company": company.pk, "branch": branch.pk, "tea": tea.pk, "box": box.pk,
        "kg": kg.pk, "pack": pack.pk, "local": local, "far": far, "small": small, "shop": shop,
    }  # fmt: skip


def order(w, supplier="local", lines=None, **more):
    return {
        "supplier": w[supplier],
        "branch": w["branch"],
        "order_date": TODAY.isoformat(),
        "lines": lines
        if lines is not None
        else [
            {"item": w["tea"], "unit": w["kg"], "qty": "500", "rate": "180"},
            {
                "item": w["box"],
                "unit": w["pack"],
                "qty": "33",
                "rate": "12.35",
                "discount_pct": "10",
            },
        ],
        **more,
    }


def test_a_draft_works_out_cgst_and_sgst_and_rounds_the_total(buyer, world):
    made = call(buyer, "post", f"companies/{world['company']}/purchase-orders/", order(world))
    assert made.status_code == 201, made.json()
    po = made.json()
    assert (po["status"], po["number"]) == ("draft", "")
    # 500 × 180 = 90,000 at 5%; 33 × 12.35 = 407.55 less 10% = 366.795 → 366.80 at 18%.
    assert [ln["taxable"] for ln in po["lines"]] == ["90000.00", "366.80"]
    assert po["taxable_total"] == "90366.80"
    assert po["cgst_total"] == po["sgst_total"] == "2283.01"
    assert po["igst_total"] == "0.00"
    assert po["total"] == "94933.00"
    assert po["round_off"] == "0.18"
    listed = call(buyer, "get", f"companies/{world['company']}/purchase-orders/").json()
    assert [o["id"] for o in listed] == [po["id"]]


def test_another_state_gives_igst_and_an_unregistered_supplier_no_gst(buyer, world):
    url = f"companies/{world['company']}/purchase-orders/"
    far = call(buyer, "post", url, order(world, "far")).json()
    assert far["interstate"] is True
    assert (far["igst_total"], far["cgst_total"]) == ("4566.02", "0.00")
    small = call(buyer, "post", url, order(world, "small")).json()
    assert small["total"] == "90367.00"
    assert {ln["gst_rate"] for ln in small["lines"]} == {"0"}


def test_submit_numbers_the_order_and_fixes_it(buyer, world):
    url = f"companies/{world['company']}/purchase-orders/"
    po = call(buyer, "post", url, order(world)).json()
    submitted = call(buyer, "post", f"purchase-orders/{po['id']}/submit/", {})
    assert submitted.status_code == 200, submitted.json()
    body = submitted.json()
    assert body["status"] == "ordered"
    assert "/PO/" in body["number"] and body["number"].endswith("00001")
    change = call(buyer, "patch", f"purchase-orders/{po['id']}/", order(world, supplier_ref="X"))
    assert "cannot be changed" in str(change.json())
    # "Submit" on a new form saves and submits at once; numbers follow on.
    second = call(buyer, "post", url, order(world, submit=True)).json()
    assert second["number"].endswith("00002")


def test_cancel_needs_the_right_and_a_reason(buyer, owner, world):
    po = call(
        buyer, "post", f"companies/{world['company']}/purchase-orders/", order(world, submit=True)
    ).json()
    cancel = f"purchase-orders/{po['id']}/cancel/"
    assert call(buyer, "post", cancel, {"reason": "x"}).status_code == 403
    assert "Say why" in str(call(owner, "post", cancel, {}).json())
    done = call(owner, "post", cancel, {"reason": "Supplier out of stock"}).json()
    assert (done["status"], done["cancel_reason"]) == ("cancelled", "Supplier out of stock")
    assert "already cancelled" in str(call(owner, "post", cancel, {"reason": "x"}).json())


def test_wrong_lines_and_parties_are_refused(buyer, world):
    url = f"companies/{world['company']}/purchase-orders/"
    bad = [
        {"item": world["box"], "unit": world["kg"], "qty": "1", "rate": "1"},
        {"item": world["box"], "unit": world["pack"], "qty": "1.5", "rate": "1"},
        {"item": world["tea"], "unit": world["kg"], "qty": "0", "rate": "1"},
    ]
    errors = call(buyer, "post", url, order(world, lines=bad)).json()["lines"]
    assert "Line 1: Pick one of the units of Tea Box." in errors
    assert any("whole numbers" in e for e in errors)
    assert any("more than zero" in e for e in errors)
    assert (
        "Add at least one item." in call(buyer, "post", url, order(world, lines=[])).json()["lines"]
    )
    customer = call(buyer, "post", url, order(world, "shop")).json()
    assert customer["supplier"] == ["Pick a supplier of this company."]
    late = order(world, expected_date=(TODAY - datetime.timedelta(days=1)).isoformat())
    assert "before the order date" in str(call(buyer, "post", url, late).json())


def test_an_item_without_a_gst_rate_is_refused_for_a_gst_supplier(buyer, world, alpha):
    with use_tenant(alpha):
        ItemGstRate.objects.filter(item_id=world["box"]).delete()
    url = f"companies/{world['company']}/purchase-orders/"
    errors = call(buyer, "post", url, order(world)).json()["lines"]
    assert errors == [f"Line 2: Tea Box has no GST rate on {TODAY:%d-%m-%Y}; add one on the item."]


def test_the_rate_comes_from_own_prices_then_the_buying_list(buyer, world, alpha):
    with use_tenant(alpha):
        party = Ledger.objects.get(pk=world["local"]).party
        plist = PriceList.objects.create(name="Tea Buying 26-27", kind=PriceList.BUYING)
        party.buying_price_list = plist
        party.save()
        start = TODAY.replace(day=1)
        for item, unit, rate in (
            (world["tea"], world["kg"], "175"),
            (world["box"], world["pack"], "12"),
        ):
            PriceListLine.objects.create(
                price_list=plist, item_id=item, unit_id=unit, rate=rate, from_date=start
            )
        PartyItemPrice.objects.create(
            party=party, side="buying", item_id=world["tea"], unit_id=world["kg"], rate="170",
            min_qty="100", from_date=start,
        )  # fmt: skip
    base = f"companies/{world['company']}/purchase-orders/rate/?supplier={world['local']}"
    own = call(buyer, "get", f"{base}&item={world['tea']}&unit={world['kg']}&qty=500").json()
    assert own == {"rate": "170", "source": "From supplier's own price"}
    # Below its own price's slab there is no rate (its own prices win outright).
    assert (
        call(buyer, "get", f"{base}&item={world['tea']}&unit={world['kg']}&qty=5").json()["rate"]
        is None
    )
    listed = call(buyer, "get", f"{base}&item={world['box']}&unit={world['pack']}&qty=5").json()
    assert listed == {"rate": "12", "source": 'From price list "Tea Buying 26-27"'}


def test_the_form_gets_suppliers_branches_and_items(buyer, world):
    setup = call(buyer, "get", f"companies/{world['company']}/purchase-orders/setup/").json()
    assert {s["name"] for s in setup["suppliers"]} == {
        "Darjeeling Tea Traders", "Assam Leaf Estates", "Village Farmer",
    }  # fmt: skip
    assert setup["branches"][0]["store"]
    assert setup["supplier_group"]
    url = f"companies/{world['company']}/purchase-orders/items/?supplier={world['local']}"
    items = {i["name"]: i for i in call(buyer, "get", url).json()}
    assert items["CTC Tea"]["gst_rate"] == "5"
    assert items["CTC Tea"]["units"] == [
        {"unit": world["kg"], "name": "kg", "whole_numbers": False}
    ]


def test_a_submitted_order_puts_its_masters_in_use_but_a_draft_does_not(buyer, world, alpha):
    url = f"companies/{world['company']}/purchase-orders/"
    po = call(buyer, "post", url, order(world)).json()
    with use_tenant(alpha):
        assert locks.uses("item", Item.objects.get(pk=world["tea"])) == []
    call(buyer, "post", f"purchase-orders/{po['id']}/submit/", {})
    with use_tenant(alpha):
        assert locks.uses("item", Item.objects.get(pk=world["tea"])) == ["1 purchase order"]
        assert locks.uses("ledger", Ledger.objects.get(pk=world["local"])) == ["1 purchase order"]


def test_changes_are_in_the_activity_log(buyer, world, alpha):
    po = call(buyer, "post", f"companies/{world['company']}/purchase-orders/", order(world)).json()
    call(buyer, "post", f"purchase-orders/{po['id']}/submit/", {})
    with use_tenant(alpha):
        entries = AuditEntry.objects.filter(record_type="purchase_order", record_id=po["id"])
        assert entries.count() == 2
        changed = {c["field"] for c in entries.order_by("-id").first().changes}
    assert {"number", "order_status"} <= changed


def test_a_company_without_purchase_has_no_orders(buyer, world, alpha):
    with use_tenant(alpha):
        company = Company.objects.get(pk=world["company"])
        company.modules = ["accounts", "sales"]
        company.save()
    assert call(buyer, "get", f"companies/{world['company']}/purchase-orders/").status_code == 404


def test_the_order_is_mailed_to_ticked_contacts_of_the_supplier_and_agent(buyer, world, alpha):
    from core.models import PartyContact

    with use_tenant(alpha):
        supplier = Ledger.objects.get(pk=world["local"]).party
        agent = Ledger.objects.get(pk=world["far"]).party
        ram = PartyContact.objects.create(party=supplier, name="Ram", email="ram@dtt.in")
        nomail = PartyContact.objects.create(party=supplier, name="Shyam", phone="9876543210")
        broker = PartyContact.objects.create(party=agent, name="Broker", email="b@ale.in")
        stranger = PartyContact.objects.create(
            party=Ledger.objects.get(pk=world["small"]).party, name="X", email="x@y.in"
        )
    url = f"companies/{world['company']}/purchase-orders/"
    po = call(buyer, "post", url, order(world, agent=world["far"], mail_to=[ram.pk, broker.pk]))
    assert po.status_code == 201, po.json()
    body = po.json()
    assert body["agent_name"] == "Assam Leaf Estates"
    assert [(c["name"], c["of"]) for c in body["mail_contacts"]] == [
        ("Ram", "Supplier"),
        ("Broker", "Agent"),
    ]
    wrong = call(buyer, "post", url, order(world, mail_to=[stranger.pk])).json()
    assert wrong["mail_to"] == ["Pick contacts of the supplier or the agent."]
    blank = call(buyer, "post", url, order(world, mail_to=[nomail.pk])).json()
    assert "without an email" in str(blank)
    itself = call(buyer, "post", url, order(world, agent=world["local"])).json()
    assert itself["agent"] == ["The agent is not the supplier itself."]


def test_the_agent_can_be_an_employee(buyer, world, alpha):
    with use_tenant(alpha):
        rina = User.objects.create_user("rina@x.in", full_name="Rina").pk
    url = f"companies/{world['company']}/purchase-orders/"
    po = call(buyer, "post", url, order(world, agent_user=rina, mail_agent_user=True)).json()
    assert po["agent_user_name"] == "Rina"
    assert [(c["name"], c["email"], c["of"]) for c in po["mail_contacts"]] == [
        ("Rina", "rina@x.in", "Agent")
    ]
    both = call(buyer, "post", url, order(world, agent=world["far"], agent_user=rina)).json()
    assert both["agent_user"] == ["Pick one agent: a supplier firm or an employee."]


def test_the_transporter_is_by_supplier_or_one_of_ours(buyer, world, alpha):
    from shipping.models import CourierAccount

    with use_tenant(alpha):
        ours = CourierAccount.objects.create(company_id=world["company"], name="VRL Logistics")
        other = create_company(name="Second Co", state_code="27")
        theirs = CourierAccount.objects.create(company=other, name="Blue Dart")
        off = CourierAccount.objects.create(
            company_id=world["company"], name="Old Lorry", is_active=False
        )
        Ledger.objects.filter(pk=world["local"]).update(preferred_transporter=ours)
    url = f"companies/{world['company']}/purchase-orders/"
    # The form gets the company's transporters and the supplier's preferred one.
    setup = call(buyer, "get", f"{url}setup/").json()
    assert [t["name"] for t in setup["transporters"]] == ["Old Lorry", "VRL Logistics"]
    local = next(s for s in setup["suppliers"] if s["id"] == world["local"])
    assert local["transporter"] == ours.pk
    # None means the supplier sends the goods.
    plain = call(buyer, "post", url, order(world)).json()
    assert plain["transporter"] is None and plain["transporter_name"] == "By Supplier"
    po = call(buyer, "post", url, order(world, transporter=ours.pk, submit=True)).json()
    assert po["transporter_name"] == "VRL Logistics"
    for bad, says in ((theirs.pk, "of this company"), (off.pk, "disabled")):
        refused = call(buyer, "post", url, order(world, transporter=bad))
        assert says in str(refused.json())
    # A transporter on a submitted order is in use.
    with use_tenant(alpha):
        assert "1 purchase order" in locks.uses("courier_account", ours)


def test_a_line_takes_the_items_purchase_description_unless_changed(buyer, world, alpha):
    with use_tenant(alpha):
        Item.objects.filter(pk=world["tea"]).update(purchase_description="Assam CTC\n50 kg sacks")
    url = f"companies/{world['company']}/purchase-orders/"
    picked = call(buyer, "get", f"{url}items/?supplier={world['local']}").json()
    assert next(i for i in picked if i["id"] == world["tea"])["description"] == (
        "Assam CTC\n50 kg sacks"
    )
    lines = [
        {"item": world["tea"], "unit": world["kg"], "qty": "5", "rate": "180"},
        {
            "item": world["tea"],
            "unit": world["kg"],
            "qty": "5",
            "rate": "180",
            "description": "Second flush only  \n",
        },
    ]
    po = call(buyer, "post", url, order(world, lines=lines)).json()
    assert [ln["description"] for ln in po["lines"]] == [
        "Assam CTC\n50 kg sacks",
        "Second flush only",
    ]
