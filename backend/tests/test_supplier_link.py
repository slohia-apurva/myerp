"""The supplier's link in a mailed order: accept or report an issue without signing in."""

import re
from datetime import timedelta

import pytest
from django.core import mail as outbox
from django.test import Client
from django.utils import timezone

from audit.models import AuditEntry
from buying.models import PurchaseOrder, SupplierLink
from core.models import Notification, PartyContact
from tenancy.context import use_tenant
from tests.test_goods_receipts import grn, store, url  # noqa: F401
from tests.test_purchase_orders import HOST, buyer, call, owner, world  # noqa: F401
from tests.test_supplier_mail import _mailbox, _secrets_key, short  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _public(method, token, data=None, path=""):
    # A stranger's browser: not signed in, CSRF checks on.
    client = Client(enforce_csrf_checks=True)
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return getattr(client, method)(f"/api/v1/public/po/{token}/{path}", **kwargs)


@pytest.fixture
def mailed(buyer, owner, short, alpha):  # noqa: F811
    _mailbox(alpha, short["company"])
    body = {"to": ["sales@dtt.in"], "subject": "PO", "message": "Please find attached."}
    res = call(buyer, "post", f"purchase-orders/{short['po']}/mail/", body)
    assert res.status_code == 200, res.json()
    m = outbox.outbox[-1]
    found = re.search(r"#/po-reply/([\w-]+)", m.body)
    assert found and "View and Accept Order" in m.alternatives[0][0]
    return {**short, "token": found.group(1)}


def test_the_supplier_accepts_and_we_are_told(buyer, mailed, alpha):  # noqa: F811
    token = mailed["token"]
    with use_tenant(alpha):
        assert not SupplierLink.objects.filter(token_hash=token).exists()  # only the hash is kept
        assert PurchaseOrder.objects.get(pk=mailed["po"]).supplier_status == "sent"

    page = _public("get", token)
    assert page.status_code == 200, page.json()
    data = page.json()
    assert data["state"] == "open" and data["number"] == mailed["po_number"]
    assert data["lines"] and "notes" not in data and "supplier_response" not in data
    assert _public("get", token, path="pdf/").content.startswith(b"%PDF")
    assert _public("get", "not-a-real-code").status_code == 404

    refused = _public("post", token, {"kind": "issue", "name": "Anil"})
    assert refused.status_code == 400 and "comment" in refused.json()
    refused = _public("post", token, {"kind": "accepted", "name": " "})
    assert "name" in refused.json()
    res = _public("post", token, {"kind": "accepted", "name": "Anil Gurung",
                                  "dispatch_date": "2099-01-05"})  # fmt: skip
    assert res.status_code == 200, res.json()
    assert res.json()["supplier_status"] == "accepted" and res.json()["replies"][0]["name"]
    res = _public("post", token, {"kind": "issue", "name": "Anil Gurung", "comment": "Late"})
    assert res.status_code == 200 and res.json()["supplier_status"] == "issue"

    with use_tenant(alpha):
        told = Notification.objects.filter(user__email="buyer@x.in").values_list("title", flat=True)
        assert f"Supplier accepted {mailed['po_number']}" in told
        assert f"Supplier issue on {mailed['po_number']}" in told
        assert Notification.objects.filter(user__email="owner@x.in").count() >= 2
        logged = AuditEntry.objects.filter(record_type="purchase_order", record_id=mailed["po"])
        assert logged.filter(user_name="Anil Gurung (supplier)").count() == 2

    order = call(buyer, "get", f"purchase-orders/{mailed['po']}/").json()
    box = order["supplier_response"]
    assert [r["kind"] for r in box["rows"]] == ["mailed", "accepted", "issue"]
    assert box["rows"][0]["opened_at"] and box["dispatch_date"] == "2099-01-05"
    listed = call(buyer, "get", f"companies/{mailed['company']}/purchase-orders/?view=all").json()
    assert {o["supplier_status"] for o in listed if o["id"] == mailed["po"]} == {"issue"}


def test_a_cancelled_order_or_an_old_link_takes_no_replies(mailed, alpha):  # noqa: F811
    token = mailed["token"]
    with use_tenant(alpha):
        SupplierLink.objects.update(expires_at=timezone.now() - timedelta(days=1))
    assert _public("get", token).json()["state"] == "expired"
    res = _public("post", token, {"kind": "accepted", "name": "Anil"})
    assert res.status_code == 400 and "expired" in str(res.json())

    with use_tenant(alpha):
        SupplierLink.objects.update(expires_at=timezone.now() + timedelta(days=1))
        PurchaseOrder.objects.filter(pk=mailed["po"]).update(status=PurchaseOrder.CANCELLED)
    page = _public("get", token).json()
    assert page["state"] == "cancelled" and "lines" not in page
    assert _public("post", token, {"kind": "accepted", "name": "Anil"}).status_code == 400
    assert _public("get", token, path="pdf/").status_code == 404


def test_a_complete_order_takes_only_comments(mailed, alpha):  # noqa: F811
    with use_tenant(alpha):
        PurchaseOrder.objects.filter(pk=mailed["po"]).update(status=PurchaseOrder.RECEIVED)
        assert PartyContact.objects.filter(email="sales@dtt.in").exists()
    token = mailed["token"]
    assert _public("get", token).json()["state"] == "done"
    assert _public("post", token, {"kind": "accepted", "name": "Anil"}).status_code == 400
    res = _public("post", token, {"kind": "comment", "name": "Anil", "comment": "Thanks"})
    assert res.status_code == 200 and res.json()["supplier_status"] == "opened"


def test_an_order_never_mailed_whose_goods_came_needs_no_reply(buyer, short, alpha):  # noqa: F811
    # Goods came against an order nobody mailed: "Not required", not "Not sent".
    listed = call(buyer, "get", f"companies/{short['company']}/purchase-orders/?view=all").json()
    row = next(o for o in listed if o["id"] == short["po"])
    assert row["status"] == "part_received" and row["supplier_status"] == ""
    assert row["supplier_status_label"] == "Not required"
    # Still open and unmailed: "Not sent".
    with use_tenant(alpha):
        po = PurchaseOrder.objects.get(pk=short["po"])
        po.status = PurchaseOrder.ORDERED
        assert po.supplier_status_label() == "Not sent"
        po.supplier_status = "sent"
        po.status = PurchaseOrder.RECEIVED
        assert po.supplier_status_label() == "Sent"
