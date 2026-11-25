"""Minimum Order Value (Sidharth, 2026-11-25, previews mockups/sales/20a-20c): a
sales order whose items come to less than the customer's minimum, before GST,
is numbered but put On Hold on Submit, makes no pick list, mails the customer
and the salesman with its PDF and tells the salesman; it goes ahead when it is
changed and submitted again at the minimum, or when the hold is released."""

from decimal import Decimal

import pytest
from django.core import mail as outbox

from core import secrets
from core.models import Ledger, MailAccount, Notification, PartyContact, SalesPerson
from selling.models import PickList, SalesOrder
from tenancy.context import use_tenant
from tests.test_sales_orders import (  # noqa: F401  (fixtures)
    call,
    order,
    owner,
    seller,
    url,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture(autouse=True)
def _secrets_key(settings):
    from cryptography.fernet import Fernet

    settings.MYERP_SECRETS_KEY = Fernet.generate_key().decode()


@pytest.fixture
def held(world, alpha, seller):  # noqa: F811
    """The customer's minimum is ₹ 25,000; a salesman with a sign-in and a mail
    address; a contact ticked to get mail; the company's mailbox set up."""
    from accounts.models import User

    with use_tenant(alpha):
        ledger = Ledger.objects.get(pk=world["local"])
        ledger.min_order_value = Decimal("25000")
        rahul_user = User.objects.get(email="seller@x.in")
        rahul = SalesPerson.objects.create(
            name="Rahul", is_salesman=True, email="rahul@x.in", user=rahul_user
        )
        ledger.salesman = rahul
        ledger.save()
        anita = PartyContact.objects.create(
            party_id=ledger.party_id, name="Anita Roy", email="purchase@ohf.in"
        )
        MailAccount.objects.create(
            company_id=world["company"], address="sales@x.in", from_name="Sales",
            password=secrets.lock("app-password"),
        )  # fmt: skip
    return {**world, "anita": anita.pk}


def small(w, cartons="3"):
    """3 cartons at 2,280: ₹ 6,840 before GST, below the minimum."""
    return [{"item": w["tea"], "unit": w["case"], "qty": cartons, "rate": "2280"}]


def test_the_minimum_is_kept_per_company_on_the_customer(owner, world):  # noqa: F811
    link = f"ledgers/{world['local']}/"
    done = call(owner, "patch", link, {"party": {"min_order_value": "25000"}})
    assert done.status_code == 200, done.json()
    assert done.json()["party"]["min_order_value"] == "25000.00"
    cleared = call(owner, "patch", link, {"party": {"min_order_value": None}})
    assert cleared.json()["party"]["min_order_value"] == "0.00"


def test_below_the_minimum_is_numbered_but_held_and_mailed(seller, held, alpha):  # noqa: F811
    w = held
    body = order(w, lines=small(w), submit=True, mail_to=[w["anita"]], customer_po_no="PO-778")
    made = call(seller, "post", url(w), body)
    assert made.status_code == 201, made.json()
    so = made.json()
    assert so["status"] == "on_hold" and so["number"]
    assert so["pick_lists"] == [] and so["purchase_orders"] == []
    assert (so["hold"]["value"], so["hold"]["minimum"]) == ("6840.00", "25000.00")
    assert so["hold"]["mailed_to"] == ["purchase@ohf.in", "rahul@x.in"]
    m = outbox.outbox[-1]
    assert m.to == ["purchase@ohf.in", "rahul@x.in"] and m.cc == ["seller@x.in"]
    assert so["number"] in m.subject and "Minimum Order Value" in m.subject
    assert "Dear Anita Roy" in m.body and "short by ₹ 18,160.00" in m.body
    assert "PO-778" in m.body
    [(name, data, kind)] = m.attachments
    assert kind == "application/pdf" and data.startswith(b"%PDF")
    with use_tenant(alpha):
        note = Notification.objects.get(user__email="seller@x.in")
        assert note.title == f"Sales order {so['number']} is On Hold"
        assert "\n\n" in note.body and "• " in note.body
        assert Notification.objects.filter(user__email="owner@x.in").exists()
    # Listed under Open and On Hold, not as a pick list.
    assert [o["id"] for o in call(seller, "get", url(w) + "?view=hold").json()] == [so["id"]]
    assert so["id"] in [o["id"] for o in call(seller, "get", url(w) + "?view=open").json()]


def test_at_or_above_the_minimum_goes_ahead(seller, held, alpha):  # noqa: F811
    w = held
    made = call(seller, "post", url(w), order(w, lines=small(w, "11"), submit=True)).json()
    assert made["status"] == "ordered" and not made["hold"]  # 25,080
    assert len(made["pick_lists"]) == 1
    assert not outbox.outbox


def test_charges_and_gst_do_not_count(seller, held):  # noqa: F811
    w = held
    charges = [{"item": w["freight"], "basis": "fixed", "rate": "20000"}]
    made = call(seller, "post", url(w), order(w, lines=small(w), charges=charges, submit=True))
    assert made.status_code == 201, made.json()
    assert made.json()["status"] == "on_hold"


def test_not_mailed_still_holds_and_says_why(seller, held, alpha):  # noqa: F811
    w = held
    with use_tenant(alpha):
        MailAccount.objects.all().delete()
    so = call(seller, "post", url(w), order(w, lines=small(w), submit=True)).json()
    assert so["status"] == "on_hold"
    assert so["hold"]["mailed_to"] == [] and "not set up" in so["hold"]["mail_error"]
    # "Email Customer" offers the hold mail, to send by hand.
    draft = call(seller, "get", f"sales-orders/{so['id']}/mail/").json()
    assert "Minimum Order Value" in draft["subject"]
    assert "below your minimum order value of ₹ 25,000.00" in draft["message"]
    assert [t["email"] for t in draft["to"]] == ["purchase@ohf.in", "rahul@x.in"]


def test_edit_and_submit_again_at_the_minimum_ends_the_hold(seller, held):  # noqa: F811
    w = held
    so = call(seller, "post", url(w), order(w, lines=small(w), submit=True)).json()
    number = so["number"]
    # Saved without submitting: still on hold.
    kept = call(seller, "patch", f"sales-orders/{so['id']}/", order(w, lines=small(w, "5")))
    assert kept.status_code == 200, kept.json()
    assert kept.json()["status"] == "on_hold"
    # Still short on Submit: held again, mailed again.
    again = call(seller, "post", f"sales-orders/{so['id']}/submit/").json()
    assert again["status"] == "on_hold" and again["hold"]["value"] == "11400.00"
    assert len(outbox.outbox) == 2
    done = call(
        seller, "patch", f"sales-orders/{so['id']}/", order(w, lines=small(w, "12"), submit=True)
    ).json()
    assert (done["status"], done["number"]) == ("ordered", number)
    assert done["hold"]["ended"] == "Submitted again at or above the minimum"
    assert len(done["pick_lists"]) == 1


def test_release_hold_needs_the_cancel_right(seller, owner, held, alpha):  # noqa: F811
    w = held
    so = call(seller, "post", url(w), order(w, lines=small(w), submit=True)).json()
    # The Sales role may submit but not cancel orders, so it may not release them.
    assert call(seller, "post", f"sales-orders/{so['id']}/release/").status_code == 403
    done = call(owner, "post", f"sales-orders/{so['id']}/release/")
    assert done.status_code == 200, done.json()
    assert done.json()["status"] == "ordered" and len(done.json()["pick_lists"]) == 1
    assert "Released" in done.json()["hold"]["ended"]
    again = call(owner, "post", f"sales-orders/{so['id']}/release/")
    assert again.status_code == 400


def test_a_held_order_is_not_reserved_and_can_be_cancelled(seller, owner, held, alpha):  # noqa: F811
    from buying.planning import reserved
    from core.models import Branch

    w = held
    so = call(seller, "post", url(w), order(w, lines=small(w), submit=True)).json()
    with use_tenant(alpha):
        assert not PickList.objects.exists()
        assert SalesOrder.objects.get(pk=so["id"]).status == SalesOrder.ON_HOLD
        assert not reserved(Branch.objects.get(pk=w["branch"]), [w["tea"]]).get(w["tea"])
    gone = call(owner, "post", f"sales-orders/{so['id']}/cancel/", {"reason": "Customer left"})
    assert gone.status_code == 200 and gone.json()["status"] == "cancelled"


def test_the_pdf_says_on_hold(seller, held, alpha):  # noqa: F811
    from reportlab import rl_config

    from buying.po_pdf import order_pdf
    from selling.api import _fresh

    w = held
    so = call(seller, "post", url(w), order(w, lines=small(w), submit=True)).json()
    rl_config.pageCompression = 0
    try:
        with use_tenant(alpha):
            data = order_pdf(_fresh(SalesOrder.objects.get(pk=so["id"])))
    finally:
        rl_config.pageCompression = 1
    assert b"ON HOLD" in data
