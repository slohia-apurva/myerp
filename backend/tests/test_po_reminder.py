"""Send Reminder: a mail chasing what is still to come on an open order."""

import pytest
from django.core import mail as outbox

from audit.models import AuditEntry
from buying.models import PurchaseOrder
from tenancy.context import use_tenant
from tests.test_goods_receipts import grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_orders import buyer, call, owner, world  # noqa: F401
from tests.test_supplier_mail import _mailbox, _secrets_key, short  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def test_the_reminder_lists_pending_lines_and_is_logged(buyer, short, alpha):  # noqa: F811
    link = f"purchase-orders/{short['po']}/reminder/"
    draft = call(buyer, "get", link).json()
    assert draft["mail_ready"] is False and draft["count"] == 0 and draft["last"] is None
    assert draft["to"] == [{"name": "Anil Gurung", "email": "sales@dtt.in"}]
    assert draft["subject"] == f"Reminder: Pending Supply against PO No : {short['po_number']}"
    pending = sorted(ln["pending"] for ln in draft["lines"])
    assert pending == ["200", "30"] and all(ln["item_code"] for ln in draft["lines"])

    body = {
        "to": ["sales@dtt.in"],
        "cc": ["owner@x.in", "sales@dtt.in"],
        "subject": draft["subject"],
        "intro": draft["intro"],
        "closing": draft["closing"],
        "lines": [ln["id"] for ln in draft["lines"]],
        "attach_order": True,
    }
    res = call(buyer, "post", link, body)
    assert res.status_code == 400 and "Mail Account" in str(res.json())
    _mailbox(alpha, short["company"])
    assert "Tick at least one" in str(call(buyer, "post", link, {**body, "lines": []}).json())

    res = call(buyer, "post", link, body)
    assert res.status_code == 200, res.json()
    assert res.json()["cc"] == ["owner@x.in"]
    m = outbox.outbox[-1]
    assert m.subject.startswith("Reminder: Pending Supply") and "Dear Anil Gurung," in m.body
    assert "200 kg" in m.body and "Expected Delivery" in m.body
    assert "Pending" in m.alternatives[0][0] and m.attachments[0][1].startswith(b"%PDF")
    with use_tenant(alpha):
        logged = AuditEntry.objects.filter(record_type="purchase_order", record_id=short["po"])
        assert any(c["field"] == "po_reminder" and "pending" in c["new"]
                   for e in logged for c in e.changes)  # fmt: skip

    again = call(buyer, "get", link).json()
    assert again["count"] == 1 and again["last"]["to"] == ["sales@dtt.in"]


def test_only_open_orders_and_purchasers(store, buyer, short, alpha):  # noqa: F811
    link = f"purchase-orders/{short['po']}/reminder/"
    assert call(store, "get", link).status_code == 403
    with use_tenant(alpha):
        PurchaseOrder.objects.filter(pk=short["po"]).update(status=PurchaseOrder.CLOSED)
    assert call(buyer, "get", link).status_code == 400
