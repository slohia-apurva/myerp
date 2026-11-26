"""Bill Check (Sidharth, 2026-11-26): the supplier's bill attached to a purchase
invoice is read (e-invoice QR, the PDF's own text, OCR) and compared with the
entry; Submit warns (or refuses) when they differ."""

import base64
import io
import json
import shutil
from decimal import Decimal as D

import pytest
import zxingcpp
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from audit.models import AuditEntry
from buying import bill_reading
from buying.models import BillCheckSetting, BillReading
from core.models import Company
from tenancy.context import use_tenant
from tests.test_goods_receipts import box_line, grn, receipt, store, tea_line, url  # noqa: F401
from tests.test_purchase_invoices import _body, _inv_url, received  # noqa: F401
from tests.test_purchase_orders import HOST, TODAY, buyer, call, gstin, owner, world  # noqa: F401

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

SUPPLIER = gstin("27", "AAPFD1234F")  # Darjeeling Tea Traders, as in the world fixture
OURS = gstin("27", "AABCA1234B")
ELSEWHERE = gstin("19", "AACCA7502N")


def _qr_token(**fields) -> str:
    def part(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    data = {
        "SellerGstin": SUPPLIER,
        "BuyerGstin": OURS,
        "DocNo": "DTT/1201/2026-27",
        "DocTyp": "INV",
        "DocDt": TODAY.strftime("%d/%m/%Y"),
        "TotInvVal": 1000,
        "ItemCnt": 2,
        "MainHsnCode": "09024020",
        "Irn": "9ec7bdc42079a7d384e6112d1dbde5dda614e950f9383595b1e50f521fab7a48",
        "IrnDt": "2026-04-11 12:47:00",
        **fields,
    }
    return f"{part({'alg': 'RS256'})}.{part({'iss': 'NIC', 'data': json.dumps(data)})}.c2ln"


def _qr_picture(text: str):
    made = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode)
    code = memoryview(made.to_image(scale=4))
    return Image.frombytes("L", (code.shape[1], code.shape[0]), bytes(code))


def _bill_pdf(lines: list[str], qr: str | None = None) -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out)
    y = 800
    for text in lines:
        pdf.drawString(40, y, text)
        y -= 18
    if qr:
        pdf.drawImage(ImageReader(_qr_picture(qr)), 400, 650, 150, 150)
    pdf.save()
    return out.getvalue()


def _attach(client, inv_id, data, name="bill.pdf", kind="invoice"):
    upload = SimpleUploadedFile(name, data, content_type="application/pdf")
    body = {"type": "purchase_invoice", "id": inv_id, "file": upload, "kind": kind}
    done = client.post("/api/v1/attachments/", body, HTTP_HOST=HOST)
    assert done.status_code == 201, done.json()
    return done.json()


def _draft(buyer, g, alpha):  # noqa: F811
    with use_tenant(alpha):
        Company.objects.filter(pk=g["company"]).update(gstin=OURS)
    draft = call(buyer, "get", f"{_inv_url(g)}draft-from/?receipt={g['receipt']}").json()
    made = call(buyer, "post", _inv_url(g), _body(g, draft))
    assert made.status_code == 201, made.json()
    return draft, made.json()


def _text_bill(total_words="One Lakh Sixty Six Thousand Three Hundred Eighty Five Only",
               tea_qty="605", tea_amount="1,51,250.00", buyer_gstin=OURS,
               cgst="3,800.00", sgst="3,800.00"):  # fmt: skip
    return [
        "Darjeeling Tea Traders",
        f"GSTIN/UIN: {SUPPLIER}",
        f"Invoice No. DTT/1201   Dated {TODAY.strftime('%d-%b-%y')}",
        f"Buyer GSTIN: {buyer_gstin}",
        f"1 CTC Tea 09024020 {tea_qty} Kg 250.00 {tea_amount}",
        "2 Tea Box 48191010 30 Pac 20.00 600.00",
        f"CGST {cgst}",
        f"SGST {sgst}",
        f"Amount Chargeable (in words) INR {total_words}",
    ]


def test_reading_words_numbers_gstins_and_the_qr():
    assert bill_reading.amounts_in_words(
        "INR One Lakh Twenty Six Thousand Five Hundred Sixty Eight Only\n"
        "Tax: INR Nineteen Thousand Three Hundred Six and Ninety Eight paise Only"
    ) == [D("126568"), D("19306.98")]
    assert bill_reading.numbers("39232990 | 2,786 Pcs | 38.50/Pcs| 1,07,261.00") == [
        D("39232990"), D("2786"), D("38.50"), D("107261.00"),
    ]  # fmt: skip
    assert bill_reading.gstins(f"GSTIN:{SUPPLIER} INVOICE NO: X\nGSTIN: {ELSEWHERE}.") == [
        SUPPLIER,
        ELSEWHERE,
    ]
    pdf = _bill_pdf(["Tax Invoice " * 10], qr=_qr_token())
    read = bill_reading.read(pdf, "bill.pdf")
    assert read["qr"]["doc_no"] == "DTT/1201/2026-27" and read["qr"]["seller_gstin"] == SUPPLIER
    assert read["source"] == "qr+text"
    assert bill_reading.read(b"x", "bill.docx")["error"]


def test_a_short_bill_is_shown_and_submit_needs_a_reason(buyer, received, alpha):  # noqa: F811
    g = received
    draft, inv = _draft(buyer, g, alpha)
    link = f"purchase-invoices/{inv['id']}/"
    # Entry: tea 600 Kg @ 250, box 30 @ 20, freight; the bill says 605 Kg of tea.
    _attach(buyer, inv["id"], _bill_pdf(_text_bill()))
    box = call(buyer, "get", f"{link}bill-check/").json()
    assert box["checked"] is False and box["file"]["filename"] == "bill.pdf"

    checked = call(buyer, "post", f"{link}bill-check/", {}).json()
    assert checked["checked"] and checked["source"] == "text"
    rows = {r["key"]: r for r in checked["rows"]}
    assert rows["supplier_gstin"]["result"] == "same"
    assert rows["our_gstin"]["result"] == "same"
    assert rows["bill_no"]["result"] == "same"
    assert rows["bill_date"]["result"] == "same"
    qty = rows["line1_qty"]
    assert (qty["entry"].lower(), qty["bill"].lower()) == ("600 kg", "605 kg")
    assert rows["line1_qty"]["result"] == "differs"
    assert qty["note"].lower() == "5 kg more on bill"
    assert rows["line1_rate"]["result"] == "same"
    assert rows["line2_qty"]["result"] == "same"
    assert rows["total"]["result"] == "differs"
    assert "5 kg short" in checked["headline"].lower()
    with use_tenant(alpha):
        assert AuditEntry.objects.filter(
            record_type="purchase_invoice", record_id=inv["id"], changes__0__field="bill_check"
        ).exists()

    # Submit stops with the differences; the draft is kept.
    total = inv["total"]
    refused = call(buyer, "patch", link, _body(g, draft, bill_total=total, submit=True))
    assert refused.status_code == 400 and refused.json()["bill_check"]["differences"] >= 2
    assert call(buyer, "get", link).json()["status"] == "draft"
    # With a reason it goes ahead, and the reason is kept.
    reason = "5 Kg short, DN to follow"
    body = _body(g, draft, bill_total=total, submit=True, bill_check_reason=reason)
    done = call(buyer, "patch", link, body)
    assert done.status_code == 200, done.json()
    assert done.json()["status"] == "submitted"
    with use_tenant(alpha):
        assert BillReading.objects.get().seen_reason == "5 Kg short, DN to follow"
        assert AuditEntry.objects.filter(
            record_id=inv["id"], changes__0__new__icontains="DN to follow"
        ).exists()


def test_a_matching_bill_lets_submit_through(buyer, received, alpha):  # noqa: F811
    g = received
    draft, inv = _draft(buyer, g, alpha)
    assert inv["total"] == "165642.00"
    bill = _text_bill(
        total_words="One Lakh Sixty Five Thousand Six Hundred Forty Two Only",
        tea_qty="600",
        tea_amount="1,50,000.00",
        cgst=inv["cgst_total"],
        sgst=inv["sgst_total"],
    )
    _attach(buyer, inv["id"], _bill_pdf(bill))
    link = f"purchase-invoices/{inv['id']}/"
    checked = call(buyer, "post", f"{link}bill-check/", {}).json()
    assert [r["key"] for r in checked["rows"] if r["result"] == "differs"] == []
    done = call(buyer, "patch", link, _body(g, draft, bill_total=inv["total"], submit=True))
    assert done.status_code == 200, done.json()


def test_a_bill_for_another_company_is_always_refused(buyer, owner, received, alpha):  # noqa: F811
    g = received
    draft, inv = _draft(buyer, g, alpha)
    _attach(buyer, inv["id"], _bill_pdf(["Tax Invoice"] * 6, qr=_qr_token(BuyerGstin=ELSEWHERE)))
    link = f"purchase-invoices/{inv['id']}/"
    checked = call(buyer, "post", f"{link}bill-check/", {}).json()
    assert checked["source"].startswith("qr")
    rows = {r["key"]: r for r in checked["rows"]}
    assert rows["our_gstin"]["result"] == "differs" and rows["our_gstin"]["source"] == "QR"
    assert rows["bill_no"]["result"] == "written"  # DTT/1201 against DTT/1201/2026-27
    assert rows["irn"]["result"] == "info"
    body = _body(g, draft, bill_total=inv["total"], submit=True, bill_check_reason="It is fine")
    refused = call(owner, "patch", link, body)
    assert refused.status_code == 400 and ELSEWHERE in refused.json()["detail"]


def test_the_owner_can_refuse_submit_on_any_difference(buyer, owner, received, alpha):  # noqa: F811
    assert call(buyer, "put", "bill-reading/", {"on_difference": "refuse"}).status_code == 403
    made = call(owner, "put", "bill-reading/", {"on_difference": "refuse", "ocr": True})
    assert made.status_code == 200 and made.json()["on_difference"] == "refuse"
    with use_tenant(alpha):
        assert BillCheckSetting.current().on_difference == "refuse"
    g = received
    draft, inv = _draft(buyer, g, alpha)
    _attach(buyer, inv["id"], _bill_pdf(_text_bill()))
    link = f"purchase-invoices/{inv['id']}/"
    body = _body(g, draft, bill_total=inv["total"], submit=True, bill_check_reason="short")
    refused = call(buyer, "patch", link, body)
    assert refused.status_code == 400 and refused.json()["refused"] is True
    assert call(owner, "patch", link, body).status_code == 200


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_a_photo_is_read_by_ocr():
    img = Image.new("RGB", (1400, 500), "white")
    draw = ImageDraw.Draw(img)
    from PIL import ImageFont

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 34)
    except OSError:
        font = ImageFont.load_default(size=34)
    for n, text in enumerate(
        [f"GSTIN: {SUPPLIER}", "Invoice No: DTT/1201", "Total INR One Thousand Only"]
    ):
        draw.text((40, 40 + n * 80), text, fill="black", font=font)
    out = io.BytesIO()
    img.save(out, "PNG")
    read = bill_reading.read(out.getvalue(), "photo.png")
    assert read["source"] == "ocr"
    assert SUPPLIER in bill_reading.gstins(read["text"])
    assert D("1000") in bill_reading.amounts_in_words(read["text"])
