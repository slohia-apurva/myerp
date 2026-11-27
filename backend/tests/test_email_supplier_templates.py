"""One "Email Supplier" button: the templates offered for an order fill the
words of each mail, and the activity names the template used."""

import pytest
from django.core import mail as outbox

from audit.models import AuditEntry
from core.models import MailTemplate
from tenancy.context import use_tenant
from tests.test_goods_receipts import grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_orders import buyer, call, owner, world  # noqa: F401
from tests.test_supplier_mail import _mailbox, _secrets_key, short  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def test_templates_offered_and_used(buyer, short, alpha):  # noqa: F811
    po = short["po"]
    offered = call(buyer, "get", f"purchase-orders/{po}/mail-templates/").json()
    assert [t["used_for"] for t in offered] == ["purchase_order", "short_excess", "reminder"]

    with use_tenant(alpha):
        firm = MailTemplate.objects.create(
            name="Second Reminder (firm)",
            used_for="reminder",
            subject="2nd Reminder {PO No} for {Our Company}",
            opening="Order {PO No} to {Supplier} is still pending.",
            closing="Reply today, {Contact Name}.",
            attach=False,
        )
    offered = call(buyer, "get", f"purchase-orders/{po}/mail-templates/").json()
    names = [t["name"] for t in offered if t["used_for"] == "reminder"]
    assert names == ["Reminder for Pending Supply", "Second Reminder (firm)"]  # default first

    link = f"purchase-orders/{po}/reminder/"
    draft = call(buyer, "get", f"{link}?template={firm.pk}").json()
    assert draft["subject"].startswith(f"2nd Reminder {short['po_number']} for ")
    assert draft["intro"].startswith(f"Order {short['po_number']} to ")
    assert draft["closing"] == "Reply today, Anil Gurung." and draft["attach_default"] is False

    se = call(buyer, "get", f"purchase-orders/{po}/supplier-mail/").json()
    assert (
        se["subject_pattern"] == f"{{Short or Excess}} Supply against PO No : {short['po_number']}"
    )
    assert short["receipt_number"] in se["intros"][str(short["receipt"])]
    pm = call(buyer, "get", f"purchase-orders/{po}/mail/").json()
    assert pm["subject"] == f"Purchase Order No : {short['po_number']}"
    assert "Kindly confirm" in pm["message"]
    wrong = call(buyer, "get", f"purchase-orders/{po}/mail/?template={firm.pk}")
    assert wrong.status_code == 400

    _mailbox(alpha, short["company"])
    body = {"to": ["sales@dtt.in"], "subject": draft["subject"], "intro": draft["intro"],
            "closing": draft["closing"], "lines": [ln["id"] for ln in draft["lines"]],
            "template": firm.pk}  # fmt: skip
    assert call(buyer, "post", link, body).status_code == 200
    assert outbox.outbox[-1].subject == draft["subject"]
    with use_tenant(alpha):
        logged = AuditEntry.objects.filter(record_type="purchase_order", record_id=po)
        assert any("(Second Reminder (firm))" in c["new"] for e in logged for c in e.changes)
