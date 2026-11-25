"""Sales orders (Sidharth, 2026-11-19, previews mockups/sales 4 and 5): drafts, GST,
units, the rate lookup, despatch from a branch or an area and its stock, the
credit limit warning, submit, cancel, close line, mail and what locks."""

import datetime
from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import Role, User
from core import locks
from core.companies import create_company
from core.india import gstin_check_char
from core.models import (
    Brand,
    Item,
    ItemGroup,
    ItemGstRate,
    ItemUnit,
    Ledger,
    PartyAddress,
    PartyItemPrice,
    PartyProduct,
    PriceList,
    PriceListLine,
    SalesPerson,
    Unit,
    WarehouseLocation,
)
from posting import accounts
from posting.service import GLLine, StockLine, Voucher, post
from selling.models import SalesOrder
from tenancy.context import use_tenant

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

HOST = "alpha.localhost"
TODAY = datetime.date.today()


def gstin(state: str, pan: str) -> str:
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
def seller(alpha):
    return client_for(alpha, "seller@x.in", "sales")


def call(client, method, path, data=None):
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/{path}", **kwargs)


def add_party(client, company, name, pan="", state="27", gst_type="regular", side="Sundry Debtors"):
    detail = call(client, "get", f"companies/{company}/").json()
    group = next(g["id"] for g in detail["ledger_groups"] if g["name"] == side)
    party = {"gst_type": gst_type, "state_code": state}
    if gst_type == "overseas":
        party["country"] = "Germany"
    if gst_type == "regular":
        party["gstin"] = gstin(state, pan)
    body = {"name": name, "group": group, "party": party}
    made = call(client, "post", f"companies/{company}/ledgers/", body)
    assert made.status_code == 201, made.json()
    return made.json()["id"]


@pytest.fixture
def world(alpha, owner):
    with use_tenant(alpha):
        company = create_company(name="Apurvam Organics LLP", state_code="27")
        branch = company.branches.get(is_head_office=True)
        pcs, case = Unit.objects.get(name="Packet"), Unit.objects.get(name="Carton")
        kg = Unit.objects.get(name="Kilogram")
        more = {
            "hsn": "0902",
            "item_group": ItemGroup.objects.get_or_create(name="General")[0],
            "brand": Brand.objects.get_or_create(name="General brand")[0],
        }
        tea = Item.objects.create(
            item_number="ITEM-81", name="Green Tea 100 g", stock_unit=pcs, sales_unit=case,
            mrp=Decimal("120"), **more,
        )  # fmt: skip
        ItemUnit.objects.create(item=tea, unit=pcs, factor=1, whole_numbers=True)
        ItemUnit.objects.create(
            item=tea, unit=case, contains_qty=24, contains_unit=pcs, factor=24, whole_numbers=True
        )
        loose = Item.objects.create(item_number="ITEM-82", name="Loose Leaf", stock_unit=kg, **more)
        ItemUnit.objects.create(item=loose, unit=kg, factor=1, whole_numbers=False)
        freight = Item.objects.create(
            item_number="ITEM-83", name="Freight", stock_unit=kg, item_type=Item.SERVICE,
            sales_charge=True, **{**more, "hsn": "9965"},
        )  # fmt: skip
        ItemUnit.objects.create(item=freight, unit=kg, factor=1)
        for item, rate in ((tea, "5"), (loose, "5"), (freight, "18")):
            ItemGstRate.objects.create(item=item, valid_from=TODAY.replace(day=1), rate=rate)
        L = WarehouseLocation
        fg = L.objects.create(branch=branch, kind=L.AREA, name="Finished Goods", purpose="storage")
        rack = L.objects.create(branch=branch, kind=L.RACK, name="FG-R1", parent=fg)
        bin_ = L.objects.create(branch=branch, kind=L.BIN, name="FG-R1-B1", parent=rack)
        store = L.objects.get(branch=branch, is_default=True)
        ravi = SalesPerson.objects.create(name="Ravi", is_salesman=True)
    local = add_party(owner, company.pk, "Organic Harvest Foods", "AAPFO1234F", state="27")
    far = add_party(owner, company.pk, "Bengal Tea Traders", "AAPFB1234F", state="19")
    abroad = add_party(owner, company.pk, "Leaf GmbH", gst_type="overseas", state="")
    maker = add_party(owner, company.pk, "Leaf Supplier", "AAPFL1234F", side="Sundry Creditors")
    return {
        "tenant": alpha, "company": company.pk, "branch": branch.pk, "tea": tea.pk,
        "loose": loose.pk, "freight": freight.pk, "pcs": pcs.pk, "case": case.pk, "kg": kg.pk,
        "local": local, "far": far, "abroad": abroad, "maker": maker, "fg": fg.pk,
        "bin": bin_.pk, "store": store.pk, "ravi": ravi.pk,
    }  # fmt: skip


def order(w, customer="local", lines=None, **more):
    return {
        "customer": w[customer],
        "branch": w["branch"],
        "order_date": TODAY.isoformat(),
        "delivery_date": (TODAY + datetime.timedelta(days=7)).isoformat(),
        "lines": lines
        if lines is not None
        else [
            {"item": w["tea"], "unit": w["case"], "qty": "25", "rate": "2280"},
            {"item": w["loose"], "unit": w["kg"], "qty": "12.5", "rate": "410.4"},
        ],
        **more,
    }


def url(w):
    return f"companies/{w['company']}/sales-orders/"


def stock_in(w, where: str, qty: str, item="tea", n=1):
    """Goods put into a place, as a goods receipt would post them."""
    with use_tenant(w["tenant"]):
        from core.models import Company

        company = Company.objects.get(pk=w["company"])
        loc = WarehouseLocation.objects.get(pk=w[where])
        adj = accounts.system_ledger(company, accounts.STOCK_ADJUSTMENT)
        grni = accounts.system_ledger(company, accounts.GRNI)
        line = StockLine(Item.objects.get(pk=w[item]), loc, Decimal(qty), Decimal("10"))
        post(
            Voucher(company, loc.branch, TODAY, "test_receipt", n, f"T-{n}"),
            stock=[line],
            gl=lambda v: [GLLine(adj, debit=v[0]), GLLine(grni, credit=v[0])],
        )


def test_a_draft_works_out_gst_and_rounds_the_total(seller, world):
    made = call(seller, "post", url(world), order(world))
    assert made.status_code == 201, made.json()
    so = made.json()
    assert (so["status"], so["number"]) == ("draft", "")
    # 25 Carton × 2280 = 57,000; 12.5 kg × 410.40 = 5,130; both at 5%, same state.
    assert [ln["taxable"] for ln in so["lines"]] == ["57000.00", "5130.00"]
    assert so["cgst_total"] == so["sgst_total"] == "1553.25"
    assert (so["igst_total"], so["interstate"]) == ("0.00", False)
    assert so["total"] == "65237.00" and so["round_off"] == "0.50"
    assert so["despatch_from"] == "Head office" or so["despatch_from"] == so["branch_name"]
    listed = call(seller, "get", url(world)).json()
    assert [o["id"] for o in listed] == [so["id"]]


def test_place_of_supply_and_exports(seller, world):
    far = call(seller, "post", url(world), order(world, "far")).json()
    assert far["interstate"] is True and far["igst_total"] == "3106.50"
    abroad = call(seller, "post", url(world), order(world, "abroad")).json()
    assert abroad["total"] == "62130.00"  # an export: no GST
    # The billing address's state decides it, not the party's own.
    with use_tenant(world["tenant"]):
        party = Ledger.objects.get(pk=world["local"]).party
        PartyAddress.objects.create(
            party=party, label="Kolkata", address="Park St", state_code="19", is_billing=True
        )
        PartyAddress.objects.create(
            party=party, label="Bhiwandi", address="Gala 14", state_code="27", is_shipping=True
        )
    so = call(seller, "post", url(world), order(world)).json()
    assert so["interstate"] is True
    assert (so["bill_address"]["label"], so["ship_address"]["label"]) == ("Kolkata", "Bhiwandi")
    picked = call(seller, "post", url(world), order(world, bill_address="Bhiwandi")).json()
    assert picked["interstate"] is False
    bad = call(seller, "post", url(world), order(world, ship_address="Nowhere"))
    assert "addresses" in str(bad.json()["ship_address"])


def test_only_the_items_own_units_and_sales_items(seller, world):
    bad = [
        {"item": world["tea"], "unit": world["kg"], "qty": "1", "rate": "1"},
        {"item": world["tea"], "unit": world["pcs"], "qty": "1.5", "rate": "1"},
        {"item": world["freight"], "unit": world["kg"], "qty": "1", "rate": "1"},
    ]
    with use_tenant(world["tenant"]):
        Item.objects.filter(pk=world["freight"]).update(allow_sales=False)
    errors = call(seller, "post", url(world), order(world, lines=bad)).json()["lines"]
    assert "Line 1: Pick one of the units of Green Tea 100 g." in errors
    assert any("whole numbers" in e for e in errors)
    assert any("not sold to this customer" in e for e in errors)


def test_the_item_picker_offers_only_the_customers_products(seller, world):
    # The type-to-search picker (search=1) keeps the customer's Products tab: with
    # products listed, only those and items ticked "Offer to all" (Sidharth 2026-11-25).
    items = (
        f"{url(world)}items/?customer={world['local']}&date={TODAY}"
        f"&branch={world['branch']}&search=1"
    )

    def names(q):
        return sorted(i["name"] for i in call(seller, "get", f"{items}&{q}").json())

    assert names("q=") == ["Freight", "Green Tea 100 g", "Loose Leaf"]
    with use_tenant(world["tenant"]):
        party = Ledger.objects.get(pk=world["local"]).party
        PartyProduct.objects.create(party=party, item_id=world["tea"])
    assert names("q=") == ["Green Tea 100 g"]
    assert names("q=loose") == []
    with use_tenant(world["tenant"]):
        Item.objects.filter(pk=world["freight"]).update(offer_to_all=True)
    assert names("q=") == ["Freight", "Green Tea 100 g"]
    # Another customer with no products still sees every item.
    other = items.replace(f"customer={world['local']}", f"customer={world['far']}")
    assert len(call(seller, "get", f"{other}&q=").json()) == 3


def test_the_rate_comes_from_own_price_then_price_list_then_mrp(seller, world):
    q = (
        f"{url(world)}rate/?customer={world['local']}&item={world['tea']}"
        f"&unit={world['case']}&qty=10&date={TODAY}"
    )
    mrp = call(seller, "get", q).json()
    # MRP 120 a packet, 24 to the carton.
    assert (mrp["rate"], mrp["source"]) == ("2880", "mrp")
    assert mrp["source_label"] == "MRP (no price set)"
    with use_tenant(world["tenant"]):
        plist = PriceList.objects.create(name="Distributor 2026", kind=PriceList.SELLING)
        PriceListLine.objects.create(
            price_list=plist, item_id=world["tea"], unit_id=world["case"], rate=2280,
            from_date=TODAY.replace(day=1),
        )  # fmt: skip
        party = Ledger.objects.get(pk=world["local"]).party
        party.price_list = plist
        party.save()
    listed = call(seller, "get", q).json()
    assert (listed["rate"], listed["source_label"]) == ("2280", "Price list: Distributor 2026")
    with use_tenant(world["tenant"]):
        PartyItemPrice.objects.create(
            party=party, side=PriceList.SELLING, item_id=world["tea"], unit_id=world["case"],
            rate=2200, from_date=TODAY.replace(day=1),
        )  # fmt: skip
    own = call(seller, "get", q).json()
    assert (own["rate"], own["source_label"]) == ("2200", "Customer's price")


def test_stock_is_counted_in_the_area_or_the_whole_branch(seller, world):
    stock_in(world, "bin", "420", n=1)  # a bin on a rack in Finished Goods
    stock_in(world, "store", "100", n=2)  # the default store, outside it
    items = f"{url(world)}items/?customer={world['local']}&date={TODAY}&branch={world['branch']}"
    whole = {i["id"]: i for i in call(seller, "get", items).json()}
    assert whole[world["tea"]]["in_stock"] == "520"
    assert whole[world["tea"]]["sales_unit"] == world["case"]
    area = {i["id"]: i for i in call(seller, "get", f"{items}&area={world['fg']}").json()}
    assert area[world["tea"]]["in_stock"] == "420"
    so = call(seller, "post", url(world), order(world, area=world["fg"])).json()
    assert so["despatch_from"].endswith("› Finished Goods")
    assert so["lines"][0]["in_stock"] == "17.5"  # 420 packets = 17.5 cartons
    # An area of another branch, or a rack, is refused.
    with use_tenant(world["tenant"]):
        rack = WarehouseLocation.objects.get(name="FG-R1").pk
    bad = call(seller, "post", url(world), order(world, area=rack))
    assert "Pick an area" in str(bad.json())


def test_credit_limit_warns_but_does_not_stop(seller, world):
    with use_tenant(world["tenant"]):
        Ledger.objects.filter(pk=world["local"]).update(
            credit_limit=Decimal("100000"), opening_amount=Decimal("50000"), opening_side="dr"
        )
    so = call(seller, "post", url(world), order(world, submit=True))
    assert so.status_code == 201, so.json()
    body = so.json()
    assert body["status"] == "ordered"
    assert "Outstanding ₹50000.00 of credit limit ₹100000.00" in body["credit_warning"]
    asked = call(seller, "get", f"{url(world)}credit/?customer={world['local']}&total=100").json()
    assert asked["warning"] == ""
    setup = call(seller, "get", f"{url(world)}setup/").json()
    row = next(c for c in setup["customers"] if c["id"] == world["local"])
    assert (row["outstanding"], row["credit_limit"]) == ("50000.00", "100000.00")


def test_submit_numbers_cancel_and_close_line(seller, owner, world):
    so = call(seller, "post", url(world), order(world)).json()
    done = call(seller, "post", f"sales-orders/{so['id']}/submit/", {}).json()
    assert done["status"] == "ordered" and "/SO/" in done["number"]
    again = call(seller, "patch", f"sales-orders/{so['id']}/", order(world))
    assert "cannot be changed" in str(again.json())
    line = done["lines"][0]["id"]
    close = f"sales-orders/{so['id']}/lines/{line}/close/"
    assert "Say why" in str(call(seller, "post", close, {}).json())
    closed = call(seller, "post", close, {"reason": "Customer took less"}).json()
    assert closed["lines"][0]["pending_qty"] == "0"
    reopened = call(seller, "post", close, {"reopen": True}).json()
    assert reopened["lines"][0]["pending_qty"] == "25"
    cancel = f"sales-orders/{so['id']}/cancel/"
    assert call(seller, "post", cancel, {"reason": "x"}).status_code == 403  # Sales has no cancel
    gone = call(owner, "post", cancel, {"reason": "Order withdrawn"}).json()
    assert gone["status"] == "cancelled"


def test_delivery_date_customer_and_branch_are_checked(seller, world):
    no_date = call(seller, "post", url(world), order(world, delivery_date=None))
    assert "delivery_date" in no_date.json()
    early = (TODAY - datetime.timedelta(days=1)).isoformat()
    assert "before the order date" in str(
        call(seller, "post", url(world), order(world, delivery_date=early)).json()
    )
    supplier = call(seller, "post", url(world), order(world, "maker"))
    assert "Pick a customer" in str(supplier.json())
    empty = call(seller, "post", url(world), order(world, lines=[])).json()
    refused = call(seller, "post", f"sales-orders/{empty['id']}/submit/", {})
    assert "at least one item" in str(refused.json())


def test_charges_salesman_and_contacts(seller, world):
    body = order(
        world,
        salesman=world["ravi"],
        charges=[{"item": world["freight"], "basis": "fixed", "rate": "2500"}],
    )
    so = call(seller, "post", url(world), body).json()
    assert so["salesman_name"] == "Ravi"
    assert so["charges"][0]["amount"] == "2500.00"
    assert so["taxable_total"] == "64630.00"  # items 62,130 + freight 2,500
    wrong = order(world, charges=[{"item": world["tea"], "basis": "fixed", "rate": "1"}])
    assert "Use as Sales Charge" in str(call(seller, "post", url(world), wrong).json())
    with use_tenant(world["tenant"]):
        SalesPerson.objects.filter(pk=world["ravi"]).update(is_salesman=False)
    fresh = call(seller, "post", url(world), order(world, salesman=world["ravi"]))
    assert "not an active salesman" in str(fresh.json())


def test_pdf_and_mail_draft(seller, world):
    so = call(seller, "post", url(world), order(world, submit=True, customer_po_no="OHF/884"))
    so = so.json()
    pdf = seller.get(f"/api/v1/sales-orders/{so['id']}/pdf/", HTTP_HOST=HOST)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    draft = call(seller, "get", f"sales-orders/{so['id']}/mail/").json()
    assert draft["subject"].startswith("Order Confirmation No")
    assert "OHF/884" in draft["message"]


def test_a_submitted_order_locks_its_customer_and_items(seller, world):
    call(seller, "post", url(world), order(world, submit=True))
    with use_tenant(world["tenant"]):
        assert locks.uses("ledger", Ledger.objects.get(pk=world["local"]))
        assert locks.uses("item", Item.objects.get(pk=world["tea"]))
        assert SalesOrder.objects.count() == 1
