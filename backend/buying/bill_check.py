"""Bill Check (Sidharth, 2026-11-26, previews 108a/108b/108c): does the
supplier's bill attached to a purchase invoice say what the entry says?

The file is read once (buying/bill_reading.py) and kept as a BillReading; the
comparison is made fresh each time against the entry as it now stands, so
correcting a draft clears its differences. Each row's result is one of:
  same, differs, written (the same invoice number written another way),
  not_read (never counted as a difference), info.
A bill from another supplier GSTIN, or addressed to a GSTIN that is not this
company's, refuses Submit. Other differences warn and ask for a reason, or
refuse, as the Owner set under Admin › Bill Reading.
"""

from __future__ import annotations

import datetime
import difflib
import re
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from buying import bill_reading
from buying.api import SUBMIT, VIEW, _check, _plain
from buying.models import BillCheckSetting, BillReading, PurchaseInvoice
from core.api import Signed
from core.models import Attachment, Branch, Company
from tenancy.context import tenant_atomic

KIND = "purchase_invoice"
SAME, DIFFERS, WRITTEN, NOT_READ, INFO = "same", "differs", "written", "not_read", "info"
RUPEE = Decimal("1")
# Files read as the supplier's bill: its own type first, then untyped PDFs/photos.
BILL_KINDS = ("invoice", "other")


# ---- which file --------------------------------------------------------


def bill_files(inv: PurchaseInvoice) -> list[Attachment]:
    rows = Attachment.objects.filter(
        record_type=KIND, record_id=inv.pk, kind__in=BILL_KINDS
    ).order_by("-added_at", "-id")
    files = [a for a in rows.defer("data") if bill_reading.readable(a.filename)]
    return sorted(files, key=lambda a: a.kind != "invoice")


def _pick(inv: PurchaseInvoice, attachment_id=None) -> Attachment | None:
    files = bill_files(inv)
    if attachment_id is not None:
        for a in files:
            if a.pk == attachment_id:
                return a
        raise ValidationError({"attachment": ["Pick a PDF or photo of the supplier's bill."]})
    return files[0] if files else None


def read(attachment: Attachment, user, again: bool = False) -> BillReading:
    found = BillReading.objects.filter(attachment=attachment).first()
    if found and not again:
        return found
    data = bytes(Attachment.objects.values_list("data", flat=True).get(pk=attachment.pk))
    reading = bill_reading.read(data, attachment.filename, ocr=BillCheckSetting.current().ocr)
    found = found or BillReading(attachment=attachment)
    found.reading, found.read_by = reading, user
    found.seen_reason, found.seen_by, found.seen_at = "", None, None
    found.save()
    return found


# ---- comparing ---------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _near_gstin(a: str, b: str) -> bool:
    """The same GSTIN, allowing one character misread by OCR."""
    return len(a) == len(b) == 15 and sum(x != y for x, y in zip(a, b, strict=True)) <= 1


def _money(value) -> str:
    """Indian grouping: 1,26,568.00."""
    value = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if value < 0 else ""
    whole, cents = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = ",".join(re.findall(r"\d{1,2}", head[::-1]))[::-1]
        whole = f"{head},{tail}"
    return f"{sign}{whole}.{cents}"


def _rate(value) -> str:
    value = Decimal(value)
    return f"{value:.2f}" if value == value.quantize(Decimal("0.01")) else _plain(value)


def _qty(value) -> str:
    value = Decimal(value)
    return f"{value:,.0f}" if value == value.to_integral() else _plain(value)


def _row(key, label, entry, bill, result, group="", note="", source=""):
    return {
        "key": key,
        "label": label,
        "group": group,
        "entry": entry,
        "bill": bill,
        "result": result,
        "note": note,
        "source": source,
    }


MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec"
NUMERIC_DATE = r"(?<!\d)(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4}|\d{2})(?!\d)"


def _dates_in(text: str) -> list[datetime.date]:
    months = {m: n for n, m in enumerate(MONTHS.split(), 1)}
    out = []
    for d, m, y in re.findall(NUMERIC_DATE, text):
        out.append((d, m, y))
    names = "|".join(months)
    pattern = rf"(?<!\d)(\d{{1,2}})\s*[-/. ]\s*({names})[a-z]*\.?\s*[-/., ]\s*(\d{{2,4}})(?!\d)"
    for d, m, y in re.findall(pattern, text, flags=re.IGNORECASE):
        out.append((d, str(months[m.lower()]), y))
    dates = []
    for d, m, y in out:
        year = int(y) + (2000 if len(y) == 2 else 0)
        try:
            dates.append(datetime.date(year, int(m), int(d)))
        except ValueError:
            continue
    return dates


def _qr_date(value: str) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def _no_row(key, label, number, qr, text, note=""):
    """A document number (the supplier's invoice or challan no) against the QR's
    or the text's: an exact match, written differently (close), or not read."""
    entry = number or "—"
    if qr and qr.get("doc_no"):
        bill = qr["doc_no"]
        if _norm(bill) == _norm(number):
            return _row(key, label, entry, bill, SAME, source="QR")
        ratio = difflib.SequenceMatcher(None, _norm(bill), _norm(number)).ratio()
        if ratio >= 0.7:
            return _row(key, label, entry, bill, WRITTEN, note=note, source="QR")
        return _row(key, label, entry, bill, DIFFERS, source="QR")
    if not text or not number:
        return _row(key, label, entry, "", NOT_READ)
    if _norm(number) in _norm(text):
        return _row(key, label, entry, number, SAME)
    tokens = {
        t.strip(".,:;|")
        for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9/\-.]{3,}", text)
        if re.search(r"\d", t)
    }
    close = difflib.get_close_matches(number.upper(), [t.upper() for t in tokens], 1, 0.75)
    if close:
        return _row(key, label, entry, close[0], WRITTEN, note=note)
    return _row(key, label, entry, "", NOT_READ)


def _bill_no_row(inv, qr, text):
    note = "GST returns match on the exact number"
    return _no_row("bill_no", "Supplier Invoice No", inv.bill_no, qr, text, note)


def _gstin_rows(inv, qr, text, doc="bill") -> tuple[list[dict], list[str]]:
    party = inv.supplier.party
    supplier = (party.gstin if party else "") or ""
    ours = {g for g in [inv.branch.gstin, inv.company.gstin] if g}
    ours |= {g for g in inv.company.branches.values_list("gstin", flat=True) if g}
    expected = inv.branch.gstin or inv.company.gstin or ""
    rows, refuse = [], []
    if qr:
        seller, buyer, source = qr.get("seller_gstin", ""), qr.get("buyer_gstin", ""), "QR"
    else:
        found = bill_reading.gstins(text)
        seller = next((g for g in found if supplier and _near_gstin(g, supplier)), "")
        buyer = next((g for g in found if any(_near_gstin(g, o) for o in ours)), "")
        others = [g for g in found if g != seller and g != buyer]
        if not seller and others and supplier:
            seller = others.pop(0)  # the first GSTIN on a bill is the seller's
        if not buyer and others:
            buyer = others.pop(0)
        if seller and buyer == "" and seller == expected:
            seller = ""
        source = ""
    if not supplier:
        rows.append(_row("supplier_gstin", "Supplier GSTIN", "—", seller, INFO, source=source))
    elif not seller:
        rows.append(_row("supplier_gstin", "Supplier GSTIN", supplier, "", NOT_READ))
    elif _near_gstin(seller, supplier):
        rows.append(
            _row("supplier_gstin", "Supplier GSTIN", supplier, supplier, SAME, source=source)
        )
    else:
        rows.append(
            _row(
                "supplier_gstin",
                "Supplier GSTIN",
                supplier,
                seller,
                DIFFERS,
                note="A bill from another supplier",
                source=source,
            )
        )
        refuse.append(
            f"The {doc} is from GSTIN {seller}, not {inv.supplier.name} ({supplier}). "
            "Check the supplier or the file."
        )
    if not expected:
        rows.append(_row("our_gstin", "Our GSTIN", "—", buyer, INFO, source=source))
    elif not buyer:
        rows.append(_row("our_gstin", "Our GSTIN", expected, "", NOT_READ))
    elif any(_near_gstin(buyer, o) for o in ours):
        rows.append(_row("our_gstin", "Our GSTIN", expected, buyer, SAME, source=source))
    else:
        rows.append(
            _row(
                "our_gstin",
                "Our GSTIN",
                expected,
                buyer,
                DIFFERS,
                note="Addressed to another company",
                source=source,
            )
        )
        refuse.append(
            f"The {doc} is addressed to GSTIN {buyer}, not {inv.company.name} ({expected}). "
            + _whose(buyer)
        )
    return rows, refuse


OTHER_COMPANY = "It may belong to another company."


def _whose(gstin: str) -> str:
    """Name our own other company when the GSTIN is one of the group's (a bill
    raised to Apurva Organics Ltd instead of the LLP, 2026-11-28)."""
    company = Company.objects.filter(gstin=gstin).first()
    if company is None:
        branch = Branch.objects.filter(gstin=gstin).select_related("company").first()
        company = branch.company if branch else None
    return f"That is {company.name}'s GSTIN." if company else OTHER_COMPANY


def _day_row(key, label, day, qr, text):
    entry = day.strftime("%d %b %Y") if day else "—"
    if qr and _qr_date(qr.get("doc_date", "")):
        d = _qr_date(qr["doc_date"])
        result = SAME if d == day else DIFFERS
        return _row(key, label, entry, d.strftime("%d %b %Y"), result, source="QR")
    if day and day in _dates_in(text or ""):
        return _row(key, label, entry, entry, SAME)
    return _row(key, label, entry, "", NOT_READ)


def _date_row(inv, qr, text):
    return _day_row("bill_date", "Supplier Invoice Date", inv.bill_date, qr, text)


def _triples(text: str) -> list[dict]:
    """Lines of the bill reading quantity × rate = amount, read off one text line."""
    out = []
    for n, line in enumerate(text.splitlines()):
        nums = bill_reading.numbers(line)
        best = None
        for i, a in enumerate(nums):
            for j in range(i + 1, len(nums)):
                for k in range(j + 1, len(nums)):
                    q, r, amt = a, nums[j], nums[k]
                    if q <= 0 or r <= 0 or 1 in (q, r) or amt < 1:
                        continue
                    if amt != amt.quantize(Decimal("0.01")):
                        continue
                    if abs(q * r - amt) <= max(Decimal("1"), amt * Decimal("0.0005")):
                        if best is None or amt > best["amount"]:
                            best = {"line": n, "qty": q, "rate": r, "amount": amt, "text": line}
        if best:
            out.append(best)
    return out


def _line_rows(inv, text) -> tuple[list[dict], dict | None, Decimal | None]:
    """Rows for each entry line, the shortage headline, and the bill's goods
    value when every line was read."""
    lines = list(
        inv.lines.select_related("item", "unit", "receipt_line__receipt").order_by("position")
    )
    if not lines or not text:
        return [], None, None
    found = _triples(text)
    used: set[int] = set()
    rows, short, bill_goods, all_read = [], None, Decimal("0"), True
    for n, ln in enumerate(lines, start=1):
        group = f"Line {n} · {ln.item.name} · {ln.item.item_number}"
        unit = ln.unit.short_name or ln.unit.name
        hsn = ln.item.hsn or ""
        candidates = [t for t in found if t["line"] not in used]

        def score(t, ln=ln, hsn=hsn):
            s = 0
            if t["qty"] == ln.qty:
                s += 4
            if abs(t["rate"] - ln.rate) <= Decimal("0.005"):
                s += 3
            if hsn and hsn[:4] in t["text"].replace(" ", ""):
                s += 2
            return s

        candidates = [t for t in candidates if score(t) >= 3]
        if not candidates:
            all_read = False
            rows.append(_row(f"line{n}", "Quantity, Rate, Amount", "", "", NOT_READ, group=group))
            continue
        t = max(candidates, key=score)
        same_rate = [c for c in candidates if abs(c["rate"] - ln.rate) <= Decimal("0.005")]
        if t["qty"] != ln.qty and len(same_rate) > 1:
            # One entry line billed as several bill lines (lots, bags): add them up.
            together = sum((c["qty"] for c in same_rate), Decimal("0"))
            if together == ln.qty:
                used.update(c["line"] for c in same_rate)
                t = {
                    "line": same_rate[0]["line"],
                    "qty": together,
                    "rate": ln.rate,
                    "amount": sum((c["amount"] for c in same_rate), Decimal("0")),
                    "text": " ".join(c["text"] for c in same_rate),
                }
        used.add(t["line"])
        bill_goods += t["amount"]
        hsn_bill = next(
            (h for h in re.findall(r"\b\d{4,8}\b", t["text"]) if hsn and h[:4] == hsn[:4]), ""
        )
        if hsn_bill:
            same_heading = hsn_bill.startswith(hsn) or hsn.startswith(hsn_bill)
            rows.append(
                _row(
                    f"line{n}_hsn",
                    "HSN",
                    hsn,
                    hsn_bill,
                    SAME if same_heading else DIFFERS,
                    group=group,
                )
            )
        diff = t["qty"] - ln.qty
        rows.append(
            _row(
                f"line{n}_qty",
                "Quantity",
                f"{_qty(ln.qty)} {unit}",
                f"{_qty(t['qty'])} {unit}",
                SAME if diff == 0 else DIFFERS,
                group=group,
                note=""
                if diff == 0
                else f"{_qty(abs(diff))} {unit} {'more' if diff > 0 else 'less'} on bill",
            )
        )
        rate_diff = t["rate"] - ln.rate
        rows.append(
            _row(
                f"line{n}_rate",
                "Rate",
                _rate(ln.rate),
                _rate(t["rate"]),
                SAME if abs(rate_diff) <= Decimal("0.005") else DIFFERS,
                group=group,
            )
        )
        rows.append(_money_row(f"line{n}_taxable", "Taxable", ln.taxable, t["amount"], group))
        if diff > 0 and short is None:
            rl = ln.receipt_line
            short = {
                "qty": _qty(diff),
                "unit": unit,
                "billed": _qty(t["qty"]),
                "entered": _qty(ln.qty),
                "receipt": rl.receipt.number if rl else "",
                "item": ln.item.name,
            }
    return rows, short, (bill_goods if all_read and found else None)


def _money_row(key, label, entry, bill, group="", source=""):
    entry, bill = Decimal(entry), Decimal(bill)
    diff = bill - entry
    more = "more" if diff > 0 else "less"
    note = "" if abs(diff) < RUPEE else f"₹{_money(abs(diff))} {more} on bill"
    return _row(
        key,
        label,
        _money(entry),
        _money(bill),
        SAME if abs(diff) < RUPEE else DIFFERS,
        group=group,
        note=note,
        source=source,
    )


def _tax_on_bill(text: str, names: tuple[str, ...]) -> Decimal | None:
    """The first amount with paise on a line naming the tax (CGST, SGST…)."""
    for line in text.splitlines():
        upper = line.upper()
        if any(n in upper for n in names):
            amounts = [x for x in bill_reading.numbers(line) if x != x.to_integral() and x > 1]
            if amounts:
                return max(amounts)
    return None


def compare(inv: PurchaseInvoice, reading: dict) -> dict:
    qr = reading.get("qr")
    text = reading.get("text", "")
    gstin_rows, refuse = _gstin_rows(inv, qr, text)
    rows = list(gstin_rows)
    rows.append(_bill_no_row(inv, qr, text))
    rows.append(_date_row(inv, qr, text))
    if qr and qr.get("irn"):
        irn = qr["irn"]
        rows.append(_row("irn", "IRN", "", f"{irn[:8]}…{irn[-8:]}", INFO, source="QR"))
    line_rows, short, bill_goods = (
        _line_rows(inv, text) if inv.kind == PurchaseInvoice.REGULAR else ([], None, None)
    )
    rows += line_rows
    totals = "Totals"
    several = len({r["group"] for r in line_rows}) > 1
    if bill_goods is not None and several and not inv.charges.exists():
        rows.append(_money_row("taxable", "Taxable", inv.taxable_total, bill_goods, totals))
    entry_gst = inv.cgst_total + inv.sgst_total + inv.igst_total
    if text:
        if inv.igst_total:
            igst = _tax_on_bill(text, ("IGST",))
            if igst is not None:
                rows.append(_money_row("gst", "IGST", entry_gst, igst, totals))
        else:
            cgst = _tax_on_bill(text, ("CGST",))
            sgst = _tax_on_bill(text, ("SGST", "UTGST"))
            if cgst is not None and sgst is not None:
                rows.append(_money_row("gst", "CGST + SGST", entry_gst, cgst + sgst, totals))
    bill_total, source = None, ""
    if qr and qr.get("total"):
        try:
            bill_total, source = Decimal(qr["total"]), "QR"
        except ArithmeticError:
            bill_total = None
    if bill_total is None and text:
        words = bill_reading.amounts_in_words(text)
        if words:
            bill_total = max(words)
    if bill_total is not None:
        rows.append(_money_row("total", "Bill Total", inv.total, bill_total, totals, source))
    else:
        rows.append(_row("total", "Bill Total", _money(inv.total), "", NOT_READ, group=totals))
    differences = [r for r in rows if r["result"] in (DIFFERS, WRITTEN)]
    headline = ""
    if short:
        headline = (
            f"The supplier billed {short['billed']} {short['unit']} of {short['item']} but this "
            f"entry has {short['entered']} {short['unit']}"
            + (f" from Goods Receipt {short['receipt']}" if short["receipt"] else "")
            + f" ({short['qty']} {short['unit']} short)."
        )
    total_row = next(r for r in rows if r["key"] == "total")
    if total_row["result"] == DIFFERS:
        headline += (
            f" Supplier's bill total ₹{total_row['bill']} is"
            f" {total_row['note'].replace(' on bill', '')}"
            f" than this entry (₹{total_row['entry']})."
        )
    keys = {r["key"]: r["result"] for r in gstin_rows}
    return {
        "rows": rows,
        "differences": len(differences),
        "refuse": refuse,
        # Only "addressed to another company" may be overridden, and only by an
        # Owner with a reason (Sidharth, 2026-11-28): the supplier raised the
        # e-invoice to the wrong GSTIN and will not correct it in time. A bill
        # from another supplier is always refused.
        "owner_may_override": bool(refuse) and keys.get("supplier_gstin") != DIFFERS,
        "headline": headline.strip(),
        "short": short,
    }


# ---- the box, the API and Submit ----------------------------------------


def _summary(rows: list[dict]) -> str:
    names = {"line": "quantity", "taxable": "taxable", "gst": "GST", "total": "total"}
    said = []
    for r in rows:
        if r["result"] == DIFFERS:
            key = r["key"]
            if key.endswith("_qty"):
                word = "quantity"
            elif key.endswith("_rate"):
                word = "rate"
            elif key.endswith("_hsn"):
                word = "HSN"
            elif key.endswith("_taxable"):
                word = "taxable"
            else:
                word = names.get(key, r["label"])
            if word not in said:
                said.append(word)
        elif r["result"] == WRITTEN and "invoice no written differently" not in said:
            said.append("invoice no written differently")
    return ", ".join(said)


def payload(inv: PurchaseInvoice, attachment: Attachment | None, found: BillReading | None) -> dict:
    files = [{"id": a.pk, "filename": a.filename, "kind": a.kind} for a in bill_files(inv)]
    out = {"files": files, "file": None, "checked": False, "can_read": bool(files)}
    if attachment is None:
        return out
    out["file"] = {"id": attachment.pk, "filename": attachment.filename}
    if found is None:
        return out
    reading = found.reading or {}
    out.update(
        {
            "checked": True,
            "source": reading.get("source", ""),
            "error": reading.get("error", ""),
            "read_at": found.read_at,
            "read_by_name": found.read_by.display_name if found.read_by_id else "",
            "seen_reason": found.seen_reason,
            "seen_by_name": found.seen_by.display_name if found.seen_by_id else "",
            "seen_at": found.seen_at,
            "on_difference": BillCheckSetting.current().on_difference,
        }
    )
    if reading.get("error") and not reading.get("qr") and not reading.get("text"):
        out.update({"rows": [], "differences": 0, "refuse": [], "headline": "", "summary": ""})
        return out
    result = compare(inv, reading)
    result["summary"] = _summary(result["rows"])
    out.update(result)
    return out


def _log(user, inv: PurchaseInvoice, text: str) -> None:
    AuditEntry.objects.create(
        user=user,
        user_name=user.display_name[:150],
        company_id=inv.company_id,
        record_type=KIND,
        record_id=inv.pk,
        record_name=str(inv)[:200],
        action=AuditEntry.UPDATE,
        changes=[{"field": "bill_check", "label": "Bill Check", "old": None, "new": text[:500]}],
    )


def _result_text(p: dict) -> str:
    if p.get("error") and not p.get("rows"):
        return p["error"]
    if p.get("refuse"):
        return " ".join(p["refuse"])
    if not p.get("differences"):
        return "matches the entry"
    return f"{p['differences']} difference{'s' if p['differences'] != 1 else ''} ({p['summary']})"


def _invoice(request, pk: int) -> PurchaseInvoice:
    from buying.invoices import _invoice as find

    return find(request, pk)


class BillCheckView(APIView):
    """GET the Bill Check box (cheap: no reading). POST {attachment?, again?}
    reads the bill (once per file unless "again") and compares."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        inv = _invoice(request, pk)
        attachment = _pick(inv)
        found = BillReading.objects.filter(attachment=attachment).first() if attachment else None
        return Response(payload(inv, attachment, found))

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, VIEW)
        inv = _invoice(request, pk)
        raw = request.data.get("attachment")
        try:
            wanted = int(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            raise ValidationError({"attachment": ["Pick a file."]}) from None
        attachment = _pick(inv, wanted)
        if attachment is None:
            raise ValidationError(
                {"detail": "Attach the supplier's bill (a PDF or photo) to check it."}
            )
        again = bool(request.data.get("again"))
        fresh = again or not BillReading.objects.filter(attachment=attachment).exists()
        found = read(attachment, request.user, again=again)
        out = payload(inv, attachment, found)
        if fresh:
            _log(request.user, inv, f"Bill Check of {attachment.filename}: {_result_text(out)}")
        return Response(out)


class BillCheckSeenView(APIView):
    """POST {reason}: the differences are known and accepted (kept in Activity)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        inv = _invoice(request, pk)
        reason = str(request.data.get("reason", "")).strip()[:300]
        if not reason:
            raise ValidationError({"reason": ["Say why the differences are all right."]})
        attachment = _pick(inv)
        found = BillReading.objects.filter(attachment=attachment).first() if attachment else None
        if found is None:
            raise NotFound("Check the bill first.")
        _seen(found, request.user, reason)
        _log(request.user, inv, f"Bill Check differences marked as seen: {reason}")
        return Response(payload(inv, attachment, found))


def _seen(found: BillReading, user, reason: str) -> None:
    found.seen_reason, found.seen_by, found.seen_at = reason, user, timezone.now()
    found.save(update_fields=["seen_reason", "seen_by", "seen_at"])


def refuse_submit(inv: PurchaseInvoice, user, reason: str = "") -> Response | None:
    """Before Submit: read the bill if not read yet and compare. Answers 400
    with the Bill Check (without raising, so the saved draft is kept) when the
    bill is from another supplier or addressed to another company, or when it
    differs and no reason is given (or the Owner set "Refuse Submit" and the
    person is not an Owner). None lets Submit go on."""
    attachment = _pick(inv)
    if attachment is None:
        return None
    found = read(attachment, user)
    p = payload(inv, attachment, found)
    reason = (reason or "").strip()[:300]
    if p.get("refuse"):
        override = bool(p.get("owner_may_override")) and user.is_owner
        if reason and override:
            _seen(found, user, reason)
            _log(user, inv, f"Submitted anyway by an Owner: {_result_text(p)} Reason: {reason}")
            return None
        return Response(
            {
                "bill_check": p,
                "detail": " ".join(p["refuse"]),
                "id": inv.pk,
                "override": override,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not p.get("differences") or found.seen_reason:
        return None
    refused = BillCheckSetting.current().on_difference == BillCheckSetting.REFUSE
    if reason and (not refused or user.is_owner):
        _seen(found, user, reason)
        _log(user, inv, f"Submitted with {_result_text(p)}. Reason: {reason}")
        return None
    detail = "The supplier's bill does not match this entry."
    if refused and not user.is_owner:
        detail += " Correct the entry first: only an Owner may submit it as it is."
    return Response(
        {"bill_check": p, "detail": detail, "id": inv.pk, "refused": refused and not user.is_owner},
        status=status.HTTP_400_BAD_REQUEST,
    )


class BillReadingSettingView(APIView):
    """GET the Owner's Bill Reading settings; PUT {ocr, on_difference} (Owner only)."""

    permission_classes = [Signed]

    def _out(self, s: BillCheckSetting) -> dict:
        return {
            "ocr": s.ocr,
            "on_difference": s.on_difference,
            "choices": [
                {"value": v, "label": label} for v, label in BillCheckSetting.ON_DIFFERENCE
            ],
            "ocr_available": bill_reading.ocr_available(),
            "changed_by_name": s.changed_by.display_name if s.changed_by_id else "",
            "changed_at": s.changed_at if s.pk else None,
        }

    def get(self, request):
        return Response(self._out(BillCheckSetting.current()))

    @tenant_atomic()
    def put(self, request):
        if not request.user.is_owner:
            raise PermissionDenied("Only an Owner can change Bill Reading.")
        s = BillCheckSetting.current()
        on_difference = request.data.get("on_difference", s.on_difference)
        if on_difference not in dict(BillCheckSetting.ON_DIFFERENCE):
            raise ValidationError({"on_difference": ["Pick a choice from the list."]})
        s.ocr = bool(request.data.get("ocr", s.ocr))
        s.on_difference = on_difference
        s.changed_by = request.user
        s.save()
        return Response(self._out(s))
