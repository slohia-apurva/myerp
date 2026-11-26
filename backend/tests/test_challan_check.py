"""Challan Check (Sidharth, 2026-11-26, preview 109a): the supplier's challan
attached to a goods receipt is read like the invoice's bill and compared with
what was received; Submit asks for a reason (or refuses) when they differ."""

import pytest

from audit.models import AuditEntry
from buying.models import BillCheckSetting, BillReading
from core.models import Company
from tenancy.context import use_tenant
from tests.test_bill_check import ELSEWHERE, OURS, SUPPLIER, _bill_pdf, _qr_token
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_orders import HOST, TODAY, buyer, call, owner, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]


def _challan(tea_qty="600", vehicle="WB23C4471", eway="8316 7139 2161"):
    return [
        "Darjeeling Tea Traders",
        f"GSTIN/UIN: {SUPPLIER}",
        f"Delivery Challan No. DTT/1187   Dated {TODAY.strftime('%d-%b-%y')}",
        f"Consignee GSTIN: {OURS}",
        f"Vehicle No: {vehicle}",
        f"E-way Bill No: {eway}",
        f"1 CTC Tea 09024020 {tea_qty} Kg 250.00 {int(tea_qty) * 250:,}.00",
        "2 Tea Box 48191010 30 Pac 20.00 600.00",
    ]


def _draft(store, g, alpha, **more):  # noqa: F811
    with use_tenant(alpha):
        Company.objects.filter(pk=g["company"]).update(gstin=OURS)
    body = receipt(
        g,
        [tea_line(g), box_line(g)],
        challan_date=TODAY.isoformat(),
        eway_bill_no="831671392161",
        **more,
    )
    made = call(store, "post", url(g), body)
    assert made.status_code == 201, made.json()
    return body, made.json()


def _attach(client, rid, data, kind="challan"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("challan.pdf", data, content_type="application/pdf")
    body = {"type": "goods_receipt", "id": rid, "file": upload, "kind": kind}
    done = client.post("/api/v1/attachments/", body, HTTP_HOST=HOST)
    assert done.status_code == 201, done.json()


def test_a_challan_for_more_than_was_received_asks_for_a_reason(store, grn, alpha):  # noqa: F811
    g = grn
    body, r = _draft(store, g, alpha)
    link = f"goods-receipts/{r['id']}/"
    _attach(store, r["id"], _bill_pdf(_challan(tea_qty="605")))
    box = call(store, "get", f"{link}challan-check/").json()
    assert box["checked"] is False and box["file"]["filename"] == "challan.pdf"

    checked = call(store, "post", f"{link}challan-check/", {}).json()
    rows = {x["key"]: x for x in checked["rows"]}
    for key in ("supplier_gstin", "our_gstin", "challan_no", "challan_date", "eway", "vehicle"):
        assert rows[key]["result"] == "same", rows[key]
    assert rows["line1_qty"]["result"] == "differs"
    assert rows["line1_qty"]["note"].lower() == "5 kg more on challan"
    assert rows["line1_qty"]["entry"].lower() == "600 kg received"
    assert rows["line1_hsn"]["result"] == "same"
    assert rows["line2_qty"]["result"] == "same"
    assert rows["line1_order"]["result"] == "info" and "600" in rows["line1_order"]["entry"]
    assert checked["differences"] == 1
    assert "5 kg less" in checked["headline"].lower()
    with use_tenant(alpha):
        assert AuditEntry.objects.filter(
            record_type="goods_receipt", record_id=r["id"], changes__0__field="challan_check"
        ).exists()

    refused = call(store, "patch", link, {**body, "submit": True})
    assert refused.status_code == 400 and refused.json()["bill_check"]["differences"] == 1
    assert call(store, "get", link).json()["status"] == "draft"
    reason = "5 Kg short in the lorry, supplier told"
    done = call(store, "patch", link, {**body, "submit": True, "bill_check_reason": reason})
    assert done.status_code == 200, done.json()
    assert done.json()["status"] == "submitted"
    with use_tenant(alpha):
        assert BillReading.objects.get().seen_reason == reason


def test_a_matching_challan_lets_submit_through(store, grn, alpha):  # noqa: F811
    g = grn
    body, r = _draft(store, g, alpha)
    _attach(store, r["id"], _bill_pdf(_challan()))
    link = f"goods-receipts/{r['id']}/"
    checked = call(store, "post", f"{link}challan-check/", {}).json()
    assert [x["key"] for x in checked["rows"] if x["result"] in ("differs", "written")] == []
    done = call(store, "patch", link, {**body, "submit": True})
    assert done.status_code == 200, done.json()


def test_a_wrong_vehicle_and_eway_bill_show_as_differences(store, grn, alpha):  # noqa: F811
    g = grn
    body, r = _draft(store, g, alpha)
    _attach(store, r["id"], _bill_pdf(_challan(vehicle="WB11E1585", eway="1111 2222 3333")))
    checked = call(store, "post", f"goods-receipts/{r['id']}/challan-check/", {}).json()
    rows = {x["key"]: x for x in checked["rows"]}
    assert (rows["vehicle"]["result"], rows["vehicle"]["bill"]) == ("differs", "WB11E1585")
    assert (rows["eway"]["result"], rows["eway"]["bill"]) == ("differs", "111122223333")


def test_a_challan_for_another_company_is_always_refused(store, owner, grn, alpha):  # noqa: F811
    g = grn
    body, r = _draft(store, g, alpha)
    qr = _qr_token(BuyerGstin=ELSEWHERE, DocNo="DTT/1187")
    _attach(store, r["id"], _bill_pdf(["Tax Invoice"] * 6, qr=qr), kind="invoice")
    link = f"goods-receipts/{r['id']}/"
    checked = call(store, "post", f"{link}challan-check/", {}).json()
    rows = {x["key"]: x for x in checked["rows"]}
    assert rows["our_gstin"]["result"] == "differs" and rows["challan_no"]["result"] == "same"
    refused = call(owner, "patch", link, {**body, "submit": True, "bill_check_reason": "fine"})
    assert refused.status_code == 400 and ELSEWHERE in refused.json()["detail"]


def test_the_owner_setting_refuses_submit_for_others(store, owner, grn, alpha):  # noqa: F811
    assert call(owner, "put", "bill-reading/", {"on_difference": "refuse"}).status_code == 200
    with use_tenant(alpha):
        assert BillCheckSetting.current().on_difference == "refuse"
    g = grn
    body, r = _draft(store, g, alpha)
    _attach(store, r["id"], _bill_pdf(_challan(tea_qty="605")))
    link = f"goods-receipts/{r['id']}/"
    with_reason = {**body, "submit": True, "bill_check_reason": "short"}
    refused = call(store, "patch", link, with_reason)
    assert refused.status_code == 400 and refused.json()["refused"] is True
    assert call(owner, "patch", link, with_reason).status_code == 200


def test_submit_from_the_view_checks_the_challan_too(store, grn, alpha):  # noqa: F811
    g = grn
    body, r = _draft(store, g, alpha)
    _attach(store, r["id"], _bill_pdf(_challan(tea_qty="605")))
    link = f"goods-receipts/{r['id']}/submit/"
    refused = call(store, "post", link, {})
    assert refused.status_code == 400 and refused.json()["bill_check"]["differences"] == 1
    done = call(store, "post", link, {"bill_check_reason": "5 Kg short"})
    assert done.status_code == 200, done.json()
