"""Reading a supplier's bill from its file, for free, on our own server
(Sidharth, 2026-11-26: "qr code or normal ocr", "if free").

1. The e-invoice QR code: a signed token from the GST portal (NIC) carrying
   the supplier's and buyer's GSTIN, invoice number and date, total, main HSN
   and IRN. Exact when present.
2. The page's own text: a PDF made by a computer carries it.
3. OCR (Tesseract) for scans and photos.

Nothing here touches the database: `read(data, filename)` gives a plain dict
that is stored with the attachment (BillReading) and compared with the entry
by buying/bill_check.py. Any part that cannot be read is left out, never
guessed.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
from decimal import Decimal, InvalidOperation

MAX_PAGES = 3
DPI = 300
TEXT_CAP = 30000
GSTIN = re.compile(r"(?<![A-Z0-9])\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z](?![A-Z0-9])")
PDF = ".pdf"
IMAGES = {".jpg", ".jpeg", ".png", ".webp"}


def readable(filename: str) -> bool:
    return os.path.splitext(filename.lower())[1] in IMAGES | {PDF}


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _pages(data: bytes, filename: str) -> list[tuple[object, str]]:
    """(picture, text layer) for each of the first pages."""
    ext = os.path.splitext(filename.lower())[1]
    if ext == PDF:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        out = []
        for n in range(min(len(pdf), MAX_PAGES)):
            page = pdf[n]
            text = page.get_textpage().get_text_range() or ""
            out.append((page.render(scale=DPI / 72).to_pil(), text))
        return out
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    return [(img.convert("RGB"), "")]


def _jwt_payload(token: str) -> dict | None:
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        data = body.get("data")
        return json.loads(data) if isinstance(data, str) else data
    except (ValueError, TypeError, AttributeError):
        return None


def read_qr(images: list) -> dict | None:
    """The signed e-invoice QR (not the e-way bill's plain QR), as its fields."""
    import zxingcpp

    for img in images:
        for code in zxingcpp.read_barcodes(img):
            fields = _jwt_payload(code.text)
            if fields and fields.get("SellerGstin"):
                return {
                    "seller_gstin": str(fields.get("SellerGstin", "")).upper(),
                    "buyer_gstin": str(fields.get("BuyerGstin", "")).upper(),
                    "doc_no": str(fields.get("DocNo", "")),
                    "doc_type": str(fields.get("DocTyp", "")),
                    "doc_date": str(fields.get("DocDt", "")),
                    "total": str(fields.get("TotInvVal", "")),
                    "item_count": fields.get("ItemCnt"),
                    "main_hsn": str(fields.get("MainHsnCode", "")),
                    "irn": str(fields.get("Irn", "")),
                    "irn_date": str(fields.get("IrnDt", "")),
                }
    return None


def _ocr(img) -> str:
    import pytesseract

    return pytesseract.image_to_string(img, config="--psm 6")


def read(data: bytes, filename: str, ocr: bool = True) -> dict:
    """What the file says: {"qr": {...} | None, "text": str, "source": ...,
    "error": str}. "source" names what was read: "qr", "text" (the PDF's own
    text), "ocr", or both joined with "+"."""
    out = {"qr": None, "text": "", "source": "", "error": ""}
    if not readable(filename):
        out["error"] = "Only PDFs and photos (JPG, PNG, WEBP) can be read."
        return out
    try:
        pages = _pages(data, filename)
    except Exception:  # a damaged or locked file
        out["error"] = "This file could not be opened."
        return out
    sources = []
    out["qr"] = read_qr([img for img, _ in pages])
    if out["qr"]:
        sources.append("qr")
    layer = "\n".join(text for _, text in pages)
    if len(layer.strip()) > 80:
        out["text"] = layer
        sources.append("text")
    elif ocr and ocr_available():
        out["text"] = "\n".join(_ocr(img) for img, _ in pages)
        sources.append("ocr")
    elif not out["qr"]:
        out["error"] = "This bill has no e-invoice QR code and OCR is switched off."
    out["text"] = out["text"][:TEXT_CAP]
    out["source"] = "+".join(sources)
    return out


# ---- making sense of the text -------------------------------------------

NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w.,])\d+(?:\.\d+)?")


def numbers(line: str) -> list[Decimal]:
    out = []
    for m in NUMBER.finditer(line):
        try:
            out.append(Decimal(m.group().replace(",", "")))
        except InvalidOperation:
            continue
    return out


def gstins(text: str) -> list[str]:
    seen: list[str] = []
    for g in GSTIN.findall(text.upper()):
        if g not in seen:
            seen.append(g)
    return seen


_UNITS = {
    w: n
    for n, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_TENS = {
    w: 10 * n
    for n, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split())
    if w != "_"
}
_SCALES = {
    "hundred": 100,
    "thousand": 1000,
    "lakh": 100000,
    "lakhs": 100000,
    "lac": 100000,
    "lacs": 100000,
    "crore": 10000000,
    "crores": 10000000,
    "million": 1000000,
}


def _words_value(words: list[str]) -> Decimal | None:
    total = current = 0
    seen = False
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        elif w in _SCALES:
            total += (current or 1) * _SCALES[w]
            current = 0
        else:
            continue
        seen = True
    return Decimal(total + current) if seen else None


def amounts_in_words(text: str) -> list[Decimal]:
    """Rupee amounts written in words ("INR One Lakh Twenty Six Thousand ...
    Only"), paise included: the run of number words just before "only"."""
    allowed = set(_UNITS) | set(_TENS) | set(_SCALES) | {"and", "paise", "paisa"}
    out = []
    words = re.sub(r"[^a-z ]", " ", text.lower().replace("-", " ")).split()
    for n, w in enumerate(words):
        if w != "only":
            continue
        run: list[str] = []
        k = n - 1
        while k >= 0 and words[k] in allowed:
            run.insert(0, words[k])
            k -= 1
        rupees, paise = run, []
        if "paise" in run or "paisa" in run:
            head = run[: run.index("paise" if "paise" in run else "paisa")]
            if "and" in head:
                cut = len(head) - 1 - head[::-1].index("and")
                rupees, paise = head[:cut], head[cut + 1 :]
            else:
                rupees = head
        value = _words_value([x for x in rupees if x != "and"])
        if value is None:
            continue
        cents = _words_value(paise) if paise else None
        if cents is not None and cents < 100:
            value += cents / 100
        out.append(value)
    return out
