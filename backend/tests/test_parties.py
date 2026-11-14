"""Customers and suppliers: party details on debtor and creditor ledgers."""

import pytest
from django.test import Client

from accounts.models import Role, User
from core.companies import create_company
from core.india import gstin_check_char
from tenancy.context import use_tenant
from tenancy.models import PinCode, State

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


def gstin(state: str, pan: str = "AAPFU0939F", entity: str = "1") -> str:
    first14 = f"{state}{pan}{entity}Z"
    return first14 + gstin_check_char(first14)


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


def group_id(client, company, name):
    detail = call(client, "get", f"companies/{company}/").json()
    return next(g["id"] for g in detail["ledger_groups"] if g["name"] == name)


def term_id(client, company, name):
    terms = call(client, "get", "credit-terms/").json()
    return next(t["id"] for t in terms if t["name"] == name)


def add_ledger(client, company, group, **extra):
    data = {"name": "Fresh Mart", "group": group_id(client, company, group), **extra}
    return call(client, "post", f"companies/{company}/ledgers/", data)


def test_a_customer_gets_party_details(accountant, company, alpha):
    PinCode.objects.create(pin="560001", city="Bengaluru GPO", state=State.objects.get(code="29"))
    PinCode.objects.create(pin="411028", city="Pune", state=State.objects.get(code="27"))
    with use_tenant(alpha):
        salesman = User.objects.create_user("ravi@x.in", full_name="Ravi").pk
    party = {
        "gst_type": "regular",
        "gstin": gstin("29").lower(),
        "contacts": [
            {"name": "Mr Rao", "designation": "Owner", "phone": "9876543210", "is_primary": True},
            {"name": "Meena", "designation": "Accounts", "email": "accounts@freshmart.in"},
        ],
        "credit_limit": "500000",
        "credit_term": term_id(accountant, company, "30 days"),
        "salesman": salesman,
        "addresses": [
            {
                "label": "Bengaluru office",
                "address": "12 MG Road",
                "pincode": "560001",
                "city": "Bengaluru",
                "state_code": "29",
                "is_billing": True,
            },
            {
                "label": "Pune godown",
                "address": "Hadapsar",
                "pincode": "411028",
                "state_code": "27",
                "gstin": gstin("27"),
                "is_shipping": True,
            },
        ],
    }
    response = add_ledger(accountant, company, "Sundry Debtors", party=party)
    assert response.status_code == 201, response.json()
    saved = response.json()["party"]
    # The PAN and state come from the GSTIN.
    assert saved["pan"] == "AAPFU0939F"
    assert saved["state_code"] == "29"
    assert saved["salesman_name"] == "Ravi"
    assert [a["label"] for a in saved["addresses"]] == ["Bengaluru office", "Pune godown"]
    # City and state come from the PIN list.
    assert [a["city"] for a in saved["addresses"]] == ["Bengaluru GPO", "Pune"]
    assert [(c["name"], c["is_primary"]) for c in saved["contacts"]] == [
        ("Mr Rao", True),
        ("Meena", False),
    ]

    # Not sending party leaves it as it is.
    url = f"ledgers/{response.json()['id']}/"
    again = call(accountant, "patch", url, {"notes": "Key account"}).json()
    assert again["party"]["credit_term_name"] == "30 days"
    assert len(again["party"]["contacts"]) == 2


def test_party_checks(accountant, company):
    def error(**party):
        response = add_ledger(accountant, company, "Sundry Creditors", party=party)
        assert response.status_code == 400
        return str(response.json())

    assert "needs its GSTIN" in error(gst_type="regular")
    assert "different state" in error(gst_type="regular", gstin=gstin("29"), state_code="27")
    assert "must match" in error(gst_type="regular", gstin=gstin("29"), pan="ABCPE1234F")
    assert "registered GST type" in error(gst_type="unregistered", gstin=gstin("27"))
    assert "country" in error(gst_type="overseas")
    assert "Overseas" in error(gst_type="unregistered", country="Germany")
    two_billing = [
        {"label": "A", "address": "x", "state_code": "27", "is_billing": True},
        {"label": "B", "address": "y", "state_code": "27", "is_billing": True},
    ]
    assert "only one default billing" in error(state_code="27", addresses=two_billing)
    two_main = [{"name": "A", "is_primary": True}, {"name": "B", "is_primary": True}]
    assert "only one main contact" in error(state_code="27", contacts=two_main)
    bad_kind = [{"name": "A", "kinds": ["boss"]}]
    assert "boss" in error(state_code="27", contacts=bad_kind)
    bad_email = [{"name": "A", "email": "not-an-email"}]
    assert "email" in error(state_code="27", contacts=bad_email)
    other_pan = [{"label": "A", "address": "x", "gstin": gstin("29", pan="ABCPE1234F")}]
    assert "another PAN" in error(gst_type="regular", gstin=gstin("27"), addresses=other_pan)


def test_overseas_supplier(accountant, company):
    party = {"gst_type": "overseas", "country": "Germany", "state_code": "27"}
    response = add_ledger(accountant, company, "Sundry Creditors", party=party)
    assert response.status_code == 201, response.json()
    assert response.json()["party"]["state_code"] == ""
    assert response.json()["party"]["country"] == "Germany"


def test_a_party_without_details_starts_unregistered_in_the_company_state(accountant, company):
    response = add_ledger(accountant, company, "Sundry Debtors")
    assert response.status_code == 201
    party = response.json()["party"]
    assert (party["gst_type"], party["state_code"]) == ("unregistered", "27")


def test_only_debtors_and_creditors_are_parties(accountant, company):
    response = add_ledger(accountant, company, "Indirect Expenses", party={"gst_type": "consumer"})
    assert "Sundry Debtors or Sundry Creditors" in str(response.json())
    response = add_ledger(accountant, company, "Indirect Expenses")
    assert response.status_code == 201
    assert response.json()["party"] is None


def test_party_changes_are_in_the_ledger_activity(accountant, company):
    created = add_ledger(accountant, company, "Sundry Debtors").json()
    url = f"ledgers/{created['id']}/"
    party = {
        "gst_type": "regular",
        "gstin": gstin("27"),
        "credit_term": term_id(accountant, company, "45 days"),
        "contacts": [{"name": "Mr Rao", "phone": "9876543210", "is_primary": True}],
    }
    assert call(accountant, "patch", url, {"party": party}).status_code == 200
    entries = call(
        accountant, "get", f"audit/?company={company}&type=ledger&id={created['id']}"
    ).json()["entries"]
    assert [e["action"] for e in entries] == ["update", "create"]
    changes = {c["label"]: (c["old"], c["new"]) for c in entries[0]["changes"]}
    assert changes == {
        "GST type": ("Unregistered business", "Registered (regular)"),
        "GSTIN": (None, gstin("27")),
        "PAN": (None, "AAPFU0939F"),
        "Credit terms": (None, "45 days"),
        "Contacts": (None, "Mr Rao, 9876543210 (main)"),
    }
    # The party made with the ledger is part of the ledger's "Added" entry.
    added = {c["label"] for c in entries[1]["changes"]}
    assert {"GST type", "State"} <= added


def test_people_list_for_the_salesman_picker(accountant, alpha):
    people = call(accountant, "get", "people/").json()
    assert {"id", "name"} <= set(people[0])
    with use_tenant(alpha):
        nobody = User.objects.create_user("x@x.in")
        client = Client()
        client.force_login(nobody)
    assert call(client, "get", "people/").status_code == 403


@pytest.fixture
def second(alpha):
    with use_tenant(alpha):
        return create_company(name="Apurva Organics Ltd", state_code="27").pk


def test_a_party_is_shared_by_the_group(accountant, company, second, alpha):
    """One party, a ledger in each company: details shared, balances,
    credit limit and salesman per company (decision 0020)."""
    with use_tenant(alpha):
        ravi = User.objects.create_user("ravi@x.in", full_name="Ravi").pk
        meena = User.objects.create_user("meena@x.in", full_name="Meena").pk
    party = {
        "gst_type": "regular",
        "gstin": gstin("29"),
        "credit_limit": "100000",
        "salesman": ravi,
    }
    first = add_ledger(accountant, company, "Sundry Debtors", party=party, also_in=[second])
    assert first.status_code == 201, first.json()
    shared = first.json()["party"]
    assert [c["name"] for c in shared["companies"]] == [
        "Apurva Organics Ltd",
        "Apurvam Organics LLP",
    ]
    other_id = next(c["ledger"] for c in shared["companies"] if c["id"] == second)
    other = call(accountant, "get", f"companies/{second}/ledgers/").json()
    other = next(x for x in other if x["id"] == other_id)
    assert other["group_name"] == "Sundry Debtors"
    assert other["party"]["gstin"] == gstin("29")
    assert other["party"]["credit_limit"] == "0.00"  # per company
    assert other["party"]["salesman"] is None  # per company
    assert shared["salesman_name"] == "Ravi"

    # A change made in one company shows in the other.
    change = {"party": {"contacts": [{"name": "Mr Rao", "is_primary": True}]}}
    assert call(accountant, "patch", f"ledgers/{other_id}/", change).status_code == 200
    again = call(accountant, "get", f"companies/{company}/ledgers/").json()
    again = next(x for x in again if x["id"] == first.json()["id"])
    assert again["party"]["contacts"][0]["name"] == "Mr Rao"
    assert again["party"]["credit_limit"] == "100000.00"

    # Each company has its own salesman.
    assert (
        call(
            accountant, "patch", f"ledgers/{other_id}/", {"party": {"salesman": meena}}
        ).status_code
        == 200
    )
    names = {}
    for firm in (company, second):
        for x in call(accountant, "get", f"companies/{firm}/ledgers/").json():
            if x["party"]:
                names[firm] = x["party"]["salesman_name"]
    assert names == {company: "Ravi", second: "Meena"}


def test_pick_an_existing_party(accountant, company, second):
    made = add_ledger(accountant, company, "Sundry Debtors", party={"gst_type": "consumer"})
    party_id = made.json()["party"]["id"]
    choices = call(accountant, "get", f"parties/?not_in={second}").json()
    assert [p["id"] for p in choices] == [party_id]
    assert call(accountant, "get", f"parties/?not_in={company}").json() == []

    # The same name without picking it is refused.
    again = add_ledger(accountant, second, "Sundry Debtors")
    assert "Existing customer or supplier" in str(again.json())
    linked = add_ledger(accountant, second, "Sundry Debtors", party_id=party_id)
    assert linked.status_code == 201, linked.json()
    assert linked.json()["party"]["id"] == party_id
    assert linked.json()["party"]["gst_type"] == "consumer"
    # Only once per company.
    twice = add_ledger(accountant, second, "Sundry Debtors", name="Fresh Mart 2", party_id=party_id)
    assert "already has the customer ledger" in str(twice.json())


def test_customers_and_vendors_are_numbered(accountant, company, second):
    """Numbers are given on Save, run on across the group, and one party can
    be both a customer and a vendor (decision 0021)."""
    one = add_ledger(accountant, company, "Sundry Debtors", name="Alpha Stores")
    two = add_ledger(accountant, company, "Sundry Debtors", name="Beta Stores")
    assert one.json()["party"]["customer_number"] == "CUST-00001"
    assert one.json()["party"]["vendor_number"] == ""
    assert two.json()["party"]["customer_number"] == "CUST-00002"
    vendor = add_ledger(accountant, company, "Sundry Creditors", name="Gamma Foods")
    assert vendor.json()["party"]["vendor_number"] == "VEND-00001"
    assert vendor.json()["party"]["customer_number"] == ""

    # Linked in another company: same party, same number, no new one.
    linked = add_ledger(
        accountant, second, "Sundry Debtors", name="Alpha Stores",
        party_id=one.json()["party"]["id"],
    )  # fmt: skip
    assert linked.json()["party"]["customer_number"] == "CUST-00001"

    # Beta is a customer of the first company and a vendor of the second.
    both = add_ledger(
        accountant, second, "Sundry Creditors", name="Beta Stores",
        party_id=two.json()["party"]["id"],
    )  # fmt: skip
    assert both.status_code == 201, both.json()
    assert both.json()["party"]["customer_number"] == "CUST-00002"
    assert both.json()["party"]["vendor_number"] == "VEND-00002"


def test_a_number_can_be_changed_but_stays_unique(accountant, company):
    one = add_ledger(accountant, company, "Sundry Debtors", name="Alpha Stores").json()
    two = add_ledger(accountant, company, "Sundry Debtors", name="Beta Stores").json()
    url = f"ledgers/{one['id']}/"
    ok = call(accountant, "patch", url, {"party": {"customer_number": "c-77"}})
    assert ok.json()["party"]["customer_number"] == "C-77"
    clash = call(
        accountant, "patch", f"ledgers/{two['id']}/",
        {"party": {"customer_number": "C-77"}},
    )  # fmt: skip
    assert clash.status_code == 400
    assert "already the number of" in str(clash.json())
    # Blank keeps the number; the next automatic one skips taken numbers.
    blank = call(accountant, "patch", url, {"party": {"customer_number": ""}})
    assert blank.json()["party"]["customer_number"] == "C-77"
    call(accountant, "patch", url, {"party": {"customer_number": "CUST-00003"}})
    three = add_ledger(accountant, company, "Sundry Debtors", name="Delta Stores").json()
    assert three["party"]["customer_number"] == "CUST-00004"


def test_ledgers_are_found_by_customer_number(accountant, company):
    add_ledger(accountant, company, "Sundry Debtors", name="Alpha Stores")
    add_ledger(accountant, company, "Sundry Debtors", name="Beta Stores")
    found = call(accountant, "get", f"companies/{company}/ledgers/?q=00002").json()
    assert [row["name"] for row in found] == ["Beta Stores"]


def test_contact_types(accountant, company):
    contacts = [
        {"name": "Mr Rao", "is_primary": True},
        {"name": "Meena", "kinds": ["accounts", "purchase"]},
        {"name": "Dev", "kinds": ["shipping"]},
        {"name": "Isha"},
    ]
    party = {"gst_type": "unregistered", "state_code": "27", "contacts": contacts}
    response = add_ledger(accountant, company, "Sundry Debtors", party=party)
    assert response.status_code == 201, response.json()
    saved = response.json()["party"]["contacts"]
    assert [(c["name"], c["is_primary"], c["kinds"]) for c in saved] == [
        ("Mr Rao", True, []),
        ("Meena", False, ["accounts", "purchase"]),
        ("Dev", False, ["shipping"]),
        ("Isha", False, []),
    ]
    # The same type twice is a slip, not a second type.
    twice = [{"name": "A", "kinds": ["sales", "sales"]}]
    again = add_ledger(accountant, company, "Sundry Debtors", party={**party, "contacts": twice})
    assert again.status_code == 400


def test_one_firm_both_customer_and_supplier_in_one_company(accountant, company, second):
    """A firm both buys from and sells to the company: one ledger under Sundry
    Debtors and one under Sundry Creditors, sharing the party (GSTIN,
    addresses); never two on the same side (Sidharth, 2026-11-11)."""
    party = {"gst_type": "regular", "gstin": gstin("29")}
    sells = add_ledger(accountant, company, "Sundry Debtors", name="ABC Foods", party=party)
    assert sells.status_code == 201, sells.json()
    party_id = sells.json()["party"]["id"]

    # Offered when adding a supplier ledger, not when adding another customer one.
    suppliers = call(accountant, "get", f"parties/?not_in={company}&side=supplier").json()
    customers = call(accountant, "get", f"parties/?not_in={company}&side=customer").json()
    assert [p["id"] for p in suppliers] == [party_id] and customers == []

    # Typing the GSTIN again for a new party is refused, pointing to the firm.
    again = add_ledger(
        accountant, company, "Sundry Creditors", name="ABC Foods (Supplier)", party=party
    )
    assert "Existing customer or supplier" in str(again.json())

    buys = add_ledger(
        accountant, company, "Sundry Creditors", name="ABC Foods (Supplier)", party_id=party_id
    )
    assert buys.status_code == 201, buys.json()
    shared = buys.json()["party"]
    assert shared["id"] == party_id and shared["gstin"] == gstin("29")
    assert shared["customer_number"] and shared["vendor_number"]
    assert sorted(c["side"] for c in shared["companies"]) == ["customer", "supplier"]

    # Not a second supplier ledger, and the names must differ.
    twice = add_ledger(accountant, company, "Sundry Creditors", name="ABC 2", party_id=party_id)
    assert "already has the supplier ledger" in str(twice.json())

    # "Also add to" gives the other company its supplier ledger by the party's name.
    patch = call(accountant, "patch", f"ledgers/{buys.json()['id']}/", {"also_in": [second]})
    assert patch.status_code == 200, patch.json()
    other = call(accountant, "get", f"companies/{second}/ledgers/").json()
    assert [(x["name"], x["group_name"]) for x in other if x["party"]] == [
        ("ABC Foods", "Sundry Creditors")
    ]


def _items(alpha):
    from core.models import Item, Unit

    with use_tenant(alpha):
        unit = Unit.objects.get(name="Packet")
        names = ["Tea A", "Tea B", "Tea C", "Tea D"]
        return [
            Item.objects.create(item_number=f"ITEM-9{i}", name=n, stock_unit=unit).pk
            for i, n in enumerate(names)
        ]


def test_products_list_limits_what_a_party_is_offered(accountant, company, alpha):
    from core.models import Item, Party
    from core.parties import items_for_party

    a, b, c, d = _items(alpha)
    party = {"gst_type": "unregistered", "state_code": "27"}
    made = add_ledger(accountant, company, "Sundry Debtors", party=party)
    assert made.status_code == 201, made.json()
    ledger_url = f"ledgers/{made.json()['id']}/"

    def names(side="customer"):
        with use_tenant(alpha):
            p = Party.objects.get(pk=made.json()["party"]["id"])
            return sorted(items_for_party(p, side).values_list("name", flat=True))

    # No list: any item.
    assert names() == ["Tea A", "Tea B", "Tea C", "Tea D"]

    products = [{"item": a}, {"item": b}]
    saved = call(accountant, "patch", ledger_url, {"party": {"products": products}})
    assert saved.status_code == 200, saved.json()
    rows = saved.json()["party"]["products"]
    assert [r["item_name"] for r in rows] == ["Tea A", "Tea B"]
    assert names() == ["Tea A", "Tea B"]

    # Items ticked "Offer to all" stay on offer; disabled or not-for-sale ones stay off.
    with use_tenant(alpha):
        Item.objects.filter(pk=c).update(offer_to_all=True)
        Item.objects.filter(pk=b).update(allow_sales=False)
    assert names() == ["Tea A", "Tea C"]
    assert names("supplier") == ["Tea A", "Tea B", "Tea C"]
    with use_tenant(alpha):
        Item.objects.filter(pk=a).update(is_active=False)
    assert names() == ["Tea C"]

    # The same item twice, or a disabled item newly added, is refused.
    twice = call(accountant, "patch", ledger_url, {"party": {"products": [{"item": d}] * 2}})
    assert twice.status_code == 400
    # (Tea A is already listed, so it may stay; a new disabled item may not be added.)
    kept = call(accountant, "patch", ledger_url, {"party": {"products": [{"item": a}]}})
    assert kept.status_code == 200, kept.json()
    off = call(accountant, "patch", ledger_url, {"party": {"products": [{"item": a}, {"item": b}]}})
    assert off.status_code == 200
    with use_tenant(alpha):
        Item.objects.filter(pk=d).update(is_active=False)
    added = call(
        accountant, "patch", ledger_url, {"party": {"products": [{"item": a}, {"item": d}]}}
    )
    assert added.status_code == 400

    # An empty list sent clears it: any item again.
    cleared = call(accountant, "patch", ledger_url, {"party": {"products": []}})
    assert cleared.status_code == 200, cleared.json()
    assert names() == ["Tea C"]


def test_a_party_in_use_reports_its_locked_fields(accountant, company):
    from core import locks

    made = add_ledger(
        accountant,
        company,
        "Sundry Debtors",
        party={"gst_type": "unregistered", "state_code": "27"},
    )
    assert made.status_code == 201, made.json()
    assert made.json()["party"]["lock"] == {"in_use": [], "locked": []}
    url = f"ledgers/{made.json()['id']}/"
    fn = lambda record: "12 sales invoices"  # noqa: E731
    locks.register("party", fn)
    try:
        rows = call(accountant, "get", f"companies/{company}/ledgers/").json()
        got = next(r for r in rows if r["id"] == made.json()["id"])
        assert got["party"]["lock"]["in_use"] == ["12 sales invoices"]
        assert set(got["party"]["lock"]["locked"]) == {"gst_type", "gstin", "pan", "state_code"}
        refused = call(accountant, "patch", url, {"party": {"gst_type": "consumer"}})
        assert refused.status_code == 400
        # Credit terms, the credit limit and the name stay open, and so does Disabled.
        open_ = call(
            accountant, "patch", url, {"party": {"credit_limit": "500"}, "is_active": False}
        )
        assert open_.status_code == 200, open_.json()
        assert open_.json()["is_active"] is False
    finally:
        locks._USES["party"].remove(fn)


def test_an_indian_address_takes_its_place_from_the_pin_list(accountant, company):
    PinCode.objects.create(pin="560001", city="Bengaluru GPO", state=State.objects.get(code="29"))

    def save(address, **extra):
        party = {
            "gst_type": "unregistered",
            "state_code": "29",
            "addresses": [{"label": "Shop", "address": "1 Road", **address}],
        }
        return add_ledger(accountant, company, "Sundry Debtors", party=party, **extra)

    # A PIN that is not in the list, or none at all, is refused for a new Indian address.
    assert "Pick the PIN code" in str(save({"pincode": "999999"}).json())
    assert "Pick the PIN code" in str(save({}).json())
    ok = save({"pincode": "560001", "city": "Typed", "state_code": "27"})
    assert ok.status_code == 201, ok.json()
    address = ok.json()["party"]["addresses"][0]
    assert (address["city"], address["state_code"]) == ("Bengaluru GPO", "29")

    # An overseas address is typed freely, and a saved legacy address keeps its place.
    abroad = {
        "gst_type": "overseas",
        "country": "Oman",
        "addresses": [{"label": "Muscat", "address": "x", "country": "Oman", "city": "Muscat"}],
    }
    assert (
        add_ledger(accountant, company, "Sundry Debtors", party=abroad, name="Gulf").status_code
        == 201
    )


def test_a_customer_has_a_preferred_transporter_of_its_own_company(accountant, company, alpha):
    from shipping.models import CourierAccount

    with use_tenant(alpha):
        other = create_company(name="Second Co", state_code="27").pk
        mine = CourierAccount.objects.create(company_id=company, name="Delhivery B2B")
        theirs = CourierAccount.objects.create(company_id=other, name="Blue Dart")

    def party(transporter, group="Sundry Debtors", **extra):
        body = {
            "gst_type": "unregistered",
            "state_code": "27",
            "preferred_transporter": transporter,
        }
        return add_ledger(accountant, company, group, party=body, **extra)

    ok = party(mine.pk)
    assert ok.status_code == 201, ok.json()
    saved = ok.json()["party"]
    assert saved["preferred_transporter"] == mine.pk
    assert saved["preferred_transporter_name"] == "Delhivery B2B"

    # Another company's transporter, and a supplier's, are refused.
    assert "of this company" in str(party(theirs.pk, name="Other Mart").json())
    refused = party(mine.pk, group="Sundry Creditors", name="Supplier Ltd")
    assert "Only a customer" in str(refused.json())

    # The transporter says who prefers it, and counts as in use.
    with use_tenant(alpha):
        assert mine.preferred_by.count() == 1
    listed = call(accountant, "get", f"companies/{company}/courier-accounts/").json()
    row = next(a for a in listed if a["id"] == mine.pk)
    assert row["preferred_by"] == 1 and row["lock"]["in_use"] == ["1 customer"]

    # A disabled transporter stays on the customer that has it but is not offered to others.
    with use_tenant(alpha):
        CourierAccount.objects.filter(pk=mine.pk).update(is_active=False)
    ledger = ok.json()["id"]
    keep = call(
        accountant,
        "patch",
        f"ledgers/{ledger}/",
        {"party": {"preferred_transporter": mine.pk, "gst_type": "unregistered"}},
    )
    assert keep.status_code == 200, keep.json()
    assert "disabled" in str(party(mine.pk, name="Another Mart").json())
