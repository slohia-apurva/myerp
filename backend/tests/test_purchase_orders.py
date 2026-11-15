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
    # A draft may have no items yet; submitting needs one, and nothing is saved then.
    empty = call(buyer, "post", url, order(world, lines=[]))
    assert empty.status_code == 201, empty.json()
    assert empty.json()["status"] == "draft"
    refused = call(buyer, "post", f"purchase-orders/{empty.json()['id']}/submit/", {}).json()
    assert refused["lines"] == ["Add at least one item before submitting."]
    before = len(call(buyer, "get", url).json())
    at_once = call(buyer, "post", url, {**order(world, lines=[]), "submit": True}).json()
    assert at_once["lines"] == ["Add at least one item before submitting."]
    assert len(call(buyer, "get", url).json()) == before
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


def test_contacts_ticked_for_whatsapp(buyer, world, alpha):
    from core.models import PartyContact

    with use_tenant(alpha):
        supplier = Ledger.objects.get(pk=world["local"]).party
        ram = PartyContact.objects.create(party=supplier, name="Ram", email="ram@dtt.in")
        shyam = PartyContact.objects.create(party=supplier, name="Shyam", phone="9876543210")
        stranger = PartyContact.objects.create(
            party=Ledger.objects.get(pk=world["small"]).party, name="X", phone="9876543211"
        )
    url = f"companies/{world['company']}/purchase-orders/"
    po = call(buyer, "post", url, order(world, mail_to=[ram.pk], whatsapp_to=[shyam.pk]))
    assert po.status_code == 201, po.json()
    body = po.json()
    assert body["whatsapp_to"] == [shyam.pk]
    assert [(c["name"], c["mail"], c["whatsapp"]) for c in body["mail_contacts"]] == [
        ("Ram", True, False),
        ("Shyam", False, True),
    ]
    nophone = call(buyer, "post", url, order(world, whatsapp_to=[ram.pk])).json()
    assert nophone["whatsapp_to"] == ["A contact without a phone number cannot get WhatsApp."]
    wrong = call(buyer, "post", url, order(world, whatsapp_to=[stranger.pk])).json()
    assert wrong["whatsapp_to"] == ["Pick contacts of the supplier or the agent."]


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


def test_bill_to_ship_to_and_the_suppliers_address(buyer, world, alpha):
    from core.models import Branch, Certificate, PartyAddress, PartyDocument

    with use_tenant(alpha):
        company = Company.objects.get(pk=world["company"])
        head = company.branches.get(is_head_office=True)
        Branch.objects.filter(pk=head.pk).update(
            address="10/D/2, Ho Chi Minh Sarani", city="Kolkata", pincode="700071",
            contact_person="Accounts Desk", phone="9830012345", email="accounts@example.in",
        )  # fmt: skip
        godown = Branch.objects.create(
            company=company, name="Sankrail Godown", state_code="27", address="Dag 177",
            city="Howrah", pincode="711302",
        )  # fmt: skip
        Certificate.objects.create(company=company, kind="fssai", number="10019031002962")
        party = Ledger.objects.get(pk=world["local"]).party
        PartyAddress.objects.create(
            party=party, label="Head office", address="4 Hill Cart Road", city="Siliguri",
            pincode="734001", state_code="27", is_billing=True,
        )  # fmt: skip
        PartyAddress.objects.create(
            party=party, label="Godown", address="Plot 9", city="Pune", state_code="27"
        )
        PartyDocument.objects.create(party=party, kind="fssai", number="12823999000123")
    url = f"companies/{world['company']}/purchase-orders/"
    setup = call(buyer, "get", f"{url}setup/").json()
    local = next(s for s in setup["suppliers"] if s["id"] == world["local"])
    assert [a["label"] for a in local["addresses"]] == ["Head office", "Godown"]

    # Left out: the default billing branch and the supplier's billing address.
    po = call(buyer, "post", url, order(world, branch=godown.pk)).json()
    assert po["bill_to"] == head.pk and po["supplier_address"]["label"] == "Head office"
    shown = po["addresses"]
    assert shown["bill_to"]["address"] == "10/D/2, Ho Chi Minh Sarani"
    assert shown["bill_to"]["contact"] == "Accounts Desk"
    assert shown["bill_to"]["fssai"] == "10019031002962"
    assert shown["ship_to"]["label"] == "Sankrail Godown"
    assert shown["ship_to"]["city"] == "Howrah"
    assert shown["supplier"]["city"] == "Siliguri"
    assert shown["supplier"]["fssai"] == "12823999000123"

    # Another of the supplier's addresses, by name; one it does not have is refused.
    other = call(buyer, "post", url, order(world, supplier_address="godown")).json()
    assert other["supplier_address"]["city"] == "Pune"
    refused = call(buyer, "post", url, order(world, supplier_address="Mumbai"))
    assert "supplier's addresses" in str(refused.json())

    # The address is kept as it was when the supplier's addresses change later.
    with use_tenant(alpha):
        PartyAddress.objects.filter(party=party).delete()
    kept = call(buyer, "get", f"purchase-orders/{po['id']}/").json()
    assert kept["addresses"]["supplier"]["address"] == "4 Hill Cart Road"


def test_terms_come_from_the_supplier_else_the_company_default(owner, buyer, world, alpha):
    from core.models import Company, TermsSet

    general = {"name": "Purchase - general", "kind": "purchase", "text": "Delivery:"}
    made = call(owner, "post", "terms/", {**general, "default_for": [world["company"]]})
    assert made.status_code == 201, made.json()
    base = made.json()
    assert base["default_companies"][0]["id"] == world["company"]
    own = call(owner, "post", "terms/", {"name": "Tea estates", "kind": "purchase",
               "text": "Invoices:\nOriginal bills with the goods."}).json()  # fmt: skip
    sales = call(owner, "post", "terms/", {"name": "Sales - general", "kind": "sales",
                 "text": "Goods once sold are not taken back."}).json()  # fmt: skip
    with use_tenant(alpha):
        party = Ledger.objects.get(pk=world["far"]).party
        party.purchase_terms_id = own["id"]
        party.save()
    url = f"companies/{world['company']}/purchase-orders/"
    # Left out: the supplier's own set, else the company's default, with its text.
    po = call(buyer, "post", url, order(world)).json()
    assert "terms_set_name" in po, po
    assert (po["terms_set_name"], po["terms"]) == (
        "Purchase - general",
        "Delivery:",
    )
    po = call(buyer, "post", url, order(world, supplier="far")).json()
    assert po["terms_set_name"] == "Tea estates"
    assert po["terms"] == "Invoices:\nOriginal bills with the goods."
    # The text is the order's own: changed here, the set stays as it is.
    po = call(buyer, "post", url, order(world, terms_set=own["id"], terms="Our own words")).json()
    assert (po["terms_set"], po["terms"]) == (own["id"], "Our own words")
    wrong = call(buyer, "post", url, order(world, terms_set=sales["id"])).json()
    assert wrong["terms_set"] == ["Pick a set of purchase terms."]
    # A second default takes the company off the first; a submitted order locks the type.
    call(owner, "patch", f"terms/{own['id']}/", {"default_for": [world["company"]]})
    with use_tenant(alpha):
        assert Company.objects.get(pk=world["company"]).purchase_terms_id == own["id"]
    sub = call(buyer, "post", url, {**order(world, terms_set=base["id"]), "submit": True})
    assert sub.status_code == 201, sub.json()
    locked = call(owner, "patch", f"terms/{base['id']}/", {"kind": "sales"})
    assert locked.status_code == 400
    with use_tenant(alpha):
        assert TermsSet.objects.get(pk=base["id"]).kind == "purchase"
    same = call(owner, "post", "terms/", {"name": " purchase -  GENERAL ", "kind": "purchase",
                "text": "x"}).json()  # fmt: skip
    assert same["existing"]["kind"] == "terms"


def test_a_supplier_carries_purchase_terms_only(owner, world):
    def terms(kind):
        body = {"name": f"{kind} terms", "kind": kind, "text": "Subject to Kolkata jurisdiction."}
        return call(owner, "post", "terms/", body).json()["id"]

    buying, selling = terms("purchase"), terms("sales")
    url = f"ledgers/{world['local']}/"
    bad = call(owner, "patch", url, {"party": {"purchase_terms": selling}}).json()
    assert "purchase_terms" in str(bad)
    good = call(owner, "patch", url, {"party": {"purchase_terms": buying}})
    assert good.status_code == 200, good.json()
    assert good.json()["party"]["purchase_terms_name"] == "purchase terms"


def test_an_import_order_keeps_its_currency_and_import_details(owner, buyer, world, alpha):
    from core.models import Currency

    detail = call(owner, "get", f"companies/{world['company']}/").json()
    group = next(g["id"] for g in detail["ledger_groups"] if g["name"] == "Sundry Creditors")
    party = {"gst_type": "overseas", "country": "Sri Lanka", "state_code": ""}
    made = call(owner, "post", f"companies/{world['company']}/ledgers/",
                {"name": "Ceylon Spice Exports", "group": group, "party": party})  # fmt: skip
    assert made.status_code == 201, made.json()
    ceylon = made.json()["id"]
    with use_tenant(alpha):
        usd = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar"})[0]
        usd.symbol = "$"
        usd.save()
        Ledger.objects.filter(pk=ceylon).update(currency=usd)
    w = {**world, "ceylon": ceylon}
    url = f"companies/{world['company']}/purchase-orders/"
    details = {
        "incoterm": "CIF", "named_place": "Kolkata", "mode": "sea_fcl",
        "port_loading": "Colombo", "port_discharge": "Kolkata", "origin": "sri lanka",
        "latest_shipment": TODAY.isoformat(), "payment": "lc_sight", "partial": "not_allowed",
        "transhipment": "allowed", "insurance_by": "seller",
        "documents": ["packing_list", "commercial_invoice"], "packing": "5 kg cartons",
    }  # fmt: skip
    po = call(buyer, "post", url, order(w, supplier="ceylon", import_details=details))
    assert po.status_code == 201, po.json()
    body = po.json()
    assert (body["currency"], body["currency_symbol"], body["igst_total"]) == ("USD", "$", "0.00")
    assert (body["total"], body["round_off"]) == ("90366.80", "0.00")  # not rounded to 90367
    got = body["import_details"]
    assert got["origin"] == "Sri Lanka"
    assert got["incoterm_label"] == "CIF - Cost, Insurance and Freight"
    assert got["documents"] == ["commercial_invoice", "packing_list"]
    assert got["documents_labels"] == ["Commercial invoice", "Packing list"]
    # The next order to this supplier starts with these details (not the date).
    setup = call(buyer, "get", f"{url}setup/").json()
    row = next(s for s in setup["suppliers"] if s["id"] == ceylon)
    assert (row["overseas"], row["currency"]) == (True, "USD")
    assert row["last_import"]["incoterm"] == "CIF"
    assert row["last_import"]["latest_shipment"] == ""
    bad = call(buyer, "post", url, order(w, supplier="ceylon",
               import_details={"incoterm": "XYZ", "origin": "Atlantis"})).json()  # fmt: skip
    assert set(bad["import_details"]) == {"incoterm", "origin"}
    # A domestic supplier's order has no import details and is in rupees.
    home = call(buyer, "post", url, order(world, import_details=details)).json()
    assert (home["currency"], home["import_details"]) == ("INR", {})


def test_charges_are_service_items_with_gst_and_a_stock_cost_choice(buyer, world, alpha):
    with use_tenant(alpha):
        tea = Item.objects.get(pk=world["tea"])
        more = {"hsn": "0902", "item_group": tea.item_group, "brand": tea.brand}
        more |= {"stock_unit": tea.stock_unit, "item_type": Item.SERVICE, "maintain_stock": False}
        freight = Item.objects.create(item_number="ITEM-81", name="Freight Inward",
                                      purchase_charge=True, add_to_stock="qty", **more)  # fmt: skip
        loading = Item.objects.create(item_number="ITEM-82", name="Loading",
                                      purchase_charge=True, add_to_stock="no", **more)  # fmt: skip
        plain = Item.objects.create(item_number="ITEM-83", name="Consulting", **more)
        for item, rate in ((freight, "5"), (loading, "18"), (plain, "18")):
            ItemGstRate.objects.create(item=item, valid_from=TODAY.replace(day=1), rate=rate)
    url = f"companies/{world['company']}/purchase-orders/"
    tea_only = [{"item": world["tea"], "unit": world["kg"], "qty": "500", "rate": "180"}]
    charges = [
        {"item": freight.pk, "basis": "fixed", "rate": "4500"},
        {"item": loading.pk, "basis": "per_unit", "rate": "2.5", "gst_rate": "18"},
        {"item": freight.pk, "basis": "percent", "rate": "2", "add_to_stock": "value"},
    ]
    po = call(buyer, "post", url, order(world, lines=tea_only, charges=charges))
    assert po.status_code == 201, po.json()
    body = po.json()
    got = [(c["amount"], c["gst_rate"], c["cgst"], c["add_to_stock"]) for c in body["charges"]]
    assert got == [
        ("4500.00", "5", "112.50", "qty"),  # the item's own GST rate and stock cost choice
        ("1250.00", "18", "112.50", "no"),  # 500 kg at 2.50
        ("1800.00", "5", "45.00", "value"),  # 2% of 90,000
    ]
    # Items 90,000 + charges 7,550; GST 4,500 on tea + 540 on charges.
    assert (body["taxable_total"], body["cgst_total"], body["total"]) == (
        "97550.00", "2520.00", "102590.00",
    )  # fmt: skip
    mixed = order(world, charges=[{"item": loading.pk, "basis": "per_unit", "rate": "1"}])
    assert "same unit" in str(call(buyer, "post", url, mixed).json()["charges"])
    bad = order(world, lines=tea_only, charges=[{"item": plain.pk, "basis": "fixed", "rate": "1"}])
    assert "Use as Purchase Charge" in str(call(buyer, "post", url, bad).json()["charges"])
    odd = [{"item": freight.pk, "basis": "fixed", "rate": "1", "gst_rate": "7"}]
    assert "not a GST rate" in str(call(buyer, "post", url, order(world, charges=odd)).json())
