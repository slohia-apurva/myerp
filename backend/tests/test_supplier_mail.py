"""Email Supplier: one mail about short, missing and excess lines of an order."""

import pytest
from django.core import mail as outbox

from audit.models import AuditEntry
from core import secrets
from core.models import Ledger, MailAccount, PartyContact
from tenancy.context import use_tenant
from tests.test_goods_receipts import grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_orders import buyer, call, owner, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


@pytest.fixture(autouse=True)
def _secrets_key(settings):
    from cryptography.fernet import Fernet

    settings.MYERP_SECRETS_KEY = Fernet.generate_key().decode()


@pytest.fixture
def short(grn, store, alpha):  # noqa: F811
    puts = [{"location": grn["bin1"], "batch_number": "B1", "qty": "400"}]
    done = call(
        store, "post", url(grn), receipt(grn, [tea_line(grn, "400", puts=puts)], submit=True)
    )
    assert done.status_code == 201, done.json()
    with use_tenant(alpha):
        party = Ledger.objects.get(pk=grn["local"]).party_id
        PartyContact.objects.create(party_id=party, name="Anil Gurung", email="sales@dtt.in")
    return {**grn, "receipt": done.json()["id"], "receipt_number": done.json()["number"]}


def _mailbox(alpha, company):
    with use_tenant(alpha):
        MailAccount.objects.create(
            company_id=company, address="purchase@x.in", from_name="Purchase",
            password=secrets.lock("app-password"),
        )  # fmt: skip


def test_the_draft_lists_what_differs_and_sends_one_mail(buyer, short, alpha):  # noqa: F811
    link = f"purchase-orders/{short['po']}/supplier-mail/"
    draft = call(buyer, "get", f"{link}?grn={short['receipt']}").json()
    assert draft["mail_ready"] is False
    assert draft["to"] == [{"name": "Anil Gurung", "email": "sales@dtt.in"}]
    assert draft["cc"][0]["email"] == "buyer@x.in"
    kinds = {ln["item_name"]: (ln["kind"], ln["difference"]) for ln in draft["lines"]}
    assert set(kinds.values()) == {("short", "200"), ("not_received", "30")}
    assert short["receipt_number"] in draft["intro"] and "DTT/1187" in draft["intro"]

    body = {
        "to": ["sales@dtt.in"],
        "cc": ["owner@x.in", "sales@dtt.in"],
        "subject": f"Short Supply against PO No : {short['po_number']}",
        "intro": draft["intro"],
        "closing": draft["short_ask"],
        "lines": [ln["id"] for ln in draft["lines"]],
        "grn": short["receipt"],
    }
    res = call(buyer, "post", link, body)
    assert res.status_code == 400 and "Mail Account" in str(res.json())
    _mailbox(alpha, short["company"])
    assert "Tick at least one" in str(call(buyer, "post", link, {**body, "lines": []}).json())
    assert "not an email" in str(call(buyer, "post", link, {**body, "to": ["nope"]}).json())

    res = call(buyer, "post", link, body)
    assert res.status_code == 200, res.json()
    assert res.json()["cc"] == ["owner@x.in"]  # the supplier is not copied twice
    m = outbox.outbox[-1]
    assert m.to == ["sales@dtt.in"] and m.cc == ["owner@x.in"] and m.reply_to == ["buyer@x.in"]
    assert m.from_email == "Purchase <purchase@x.in>" and m.subject.startswith("Short Supply")
    assert "Dear Anil Gurung," in m.body and "200 kg" in m.body and "Not received" in m.body
    html = m.alternatives[0][0]
    assert "<table" in html and "Difference" in html and "Short" in html
    name, data, kind = m.attachments[0]
    assert kind == "application/pdf" and data.startswith(b"%PDF") and name.endswith(".pdf")
    with use_tenant(alpha):
        logged = AuditEntry.objects.filter(record_type="purchase_order", record_id=short["po"])
        assert any(c["field"] == "supplier_mail" and "sales@dtt.in" in c["new"]
                   for e in logged for c in e.changes)  # fmt: skip


def test_storekeepers_cannot_mail_suppliers(store, short):  # noqa: F811
    assert call(store, "get", f"purchase-orders/{short['po']}/supplier-mail/").status_code == 403
