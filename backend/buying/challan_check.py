"""Challan Check (Sidharth, 2026-11-26, preview 109a): the Bill Check's twin on
the Goods Receipt. The supplier's challan (or invoice) in Attachments is read
the same way (buying/bill_reading.py, kept as a BillReading) and compared with
what was received: GSTINs, challan no and date, e-way bill and vehicle no, and
each line's HSN and quantity. No rates or GST: the receipt is about quantities,
and the invoice's Bill Check covers money.

As on the invoice, a challan from another supplier GSTIN or addressed to
another company is always refused on Submit; other differences warn and ask
for a reason, or refuse, as the Owner set under Admin › Bill Reading.
"""

from __future__ import annotations

import re
from decimal import Decimal

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from buying import bill_reading
from buying.bill_check import (
    DIFFERS,
    INFO,
    NOT_READ,
    SAME,
    WRITTEN,
    _day_row,
    _gstin_rows,
    _no_row,
    _norm,
    _qty,
    _row,
    _seen,
    _triples,
    read,
)
from buying.models import BillCheckSetting, BillReading, GoodsReceipt
from core.api import Signed
from core.models import Attachment
from tenancy.context import tenant_atomic

KIND = "goods_receipt"
# The challan first, then the supplier's invoice, then untyped PDFs/photos.
CHALLAN_KINDS = ("challan", "invoice", "other")
EWAY = re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)")
VEHICLE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\s?-?\d{1,2}\s?-?[A-Z]{0,3}\s?-?\d{4}(?![A-Z0-9])")


def challan_files(r: GoodsReceipt) -> list[Attachment]:
    rows = Attachment.objects.filter(
        record_type=KIND, record_id=r.pk, kind__in=CHALLAN_KINDS
    ).order_by("-added_at", "-id")
    files = [a for a in rows.defer("data") if bill_reading.readable(a.filename)]
    return sorted(files, key=lambda a: CHALLAN_KINDS.index(a.kind))


def _pick(r: GoodsReceipt, attachment_id=None) -> Attachment | None:
    files = challan_files(r)
    if attachment_id is not None:
        for a in files:
            if a.pk == attachment_id:
                return a
        raise ValidationError({"attachment": ["Pick a PDF or photo of the supplier's challan."]})
    return files[0] if files else None


# ---- comparing ---------------------------------------------------------


def _eway_row(r: GoodsReceipt, text: str):
    entry = r.eway_bill_no.strip()
    if entry and _norm(entry) in _norm(text):
        return _row("eway", "E-way Bill No", entry, entry, SAME)
    said = [
        re.sub(r"\s", "", m)
        for line in text.splitlines()
        if re.search(r"E\s*-?\s*WAY|EWB", line.upper())
        for m in EWAY.findall(line)
    ]
    if not entry:
        return _row("eway", "E-way Bill No", "—", said[0], INFO) if said else None
    if said:
        return _row("eway", "E-way Bill No", entry, said[0], DIFFERS)
    return _row("eway", "E-way Bill No", entry, "", NOT_READ)


def _vehicle_row(r: GoodsReceipt, text: str):
    entry = r.vehicle_no.strip()
    if entry and _norm(entry) in _norm(text):
        return _row("vehicle", "Vehicle No", entry, entry.upper(), SAME)
    said = [
        re.sub(r"[\s-]", "", m)
        for line in text.upper().splitlines()
        if "VEHICLE" in line or "VEH" in line.split()
        for m in VEHICLE.findall(line)
    ]
    if not entry:
        return _row("vehicle", "Vehicle No", "—", said[0], INFO) if said else None
    if said:
        return _row("vehicle", "Vehicle No", entry, said[0], DIFFERS)
    return _row("vehicle", "Vehicle No", entry, "", NOT_READ)


def _unit_qty(line: str, unit: str) -> Decimal | None:
    """The quantity written just before the unit ("2,786 Pcs")."""
    if not unit:
        return None
    pattern = rf"(\d{{1,3}}(?:,\d{{2,3}})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*{re.escape(unit)}\b"
    m = re.search(pattern, line, re.IGNORECASE)
    if not m:
        return None
    return Decimal(m.group(1).replace(",", ""))


def _found_lines(text: str, ln, unit: str) -> list[dict]:
    """Challan lines for this receipt line: rows reading qty × rate = amount (scored
    as on the invoice, the order's rate standing in), else a line naming the item's
    code or HSN with a quantity in its unit."""
    hsn = ln.item.hsn or ""
    rate = ln.order_line.rate

    def score(t):
        s = 0
        if t["qty"] == ln.received_qty:
            s += 4
        if abs(t["rate"] - rate) <= Decimal("0.005"):
            s += 3
        if hsn and hsn[:4] in t["text"].replace(" ", ""):
            s += 2
        return s

    found = [dict(t, score=score(t)) for t in _triples(text)]
    found = [t for t in found if t["score"] >= 3]
    if found:
        return found
    out = []
    code = _norm(ln.item.item_number)
    for n, line in enumerate(text.splitlines()):
        flat = line.replace(" ", "")
        named = (code and code in _norm(line)) or (hsn and hsn[:4] in flat)
        q = _unit_qty(line, unit) if named else None
        if q:
            out.append({"line": n, "qty": q, "rate": rate, "text": line, "score": 3})
    return out


def _line_rows(r: GoodsReceipt, text: str) -> tuple[list[dict], list[dict]]:
    lines = list(r.lines.select_related("item", "unit", "order_line__order").order_by("position"))
    rows, gaps, used = [], [], set()
    for n, ln in enumerate(lines, start=1):
        group = f"Line {n} · {ln.item.name} · {ln.item.item_number}"
        unit = ln.unit.short_name or ln.unit.name
        hsn = ln.item.hsn or ""
        found = [t for t in _found_lines(text, ln, unit) if t["line"] not in used] if text else []
        received = f"{_qty(ln.received_qty)} {unit} received"
        if not found:
            rows.append(_row(f"line{n}_qty", "Quantity", received, "", NOT_READ, group=group))
        else:
            t = max(found, key=lambda c: c["score"])
            if t["qty"] != ln.received_qty and len(found) > 1:
                # One receipt line sent as several challan lines (lots, bags): add them up.
                together = sum((c["qty"] for c in found), Decimal("0"))
                if together == ln.received_qty:
                    used.update(c["line"] for c in found)
                    t = {"line": found[0]["line"], "qty": together,
                         "text": " ".join(c["text"] for c in found)}  # fmt: skip
            used.add(t["line"])
            hsn_said = next(
                (h for h in re.findall(r"\b\d{4,8}\b", t["text"]) if hsn and h[:4] == hsn[:4]),
                "",
            )
            if hsn_said:
                same = hsn_said.startswith(hsn) or hsn.startswith(hsn_said)
                rows.append(
                    _row(f"line{n}_hsn", "HSN", hsn, hsn_said, SAME if same else DIFFERS, group)
                )
            diff = t["qty"] - ln.received_qty
            note = (
                ""
                if diff == 0
                else f"{_qty(abs(diff))} {unit} {'more' if diff > 0 else 'less'} on challan"
            )
            rows.append(
                _row(
                    f"line{n}_qty",
                    "Quantity",
                    received,
                    f"{_qty(t['qty'])} {unit}",
                    SAME if diff == 0 else DIFFERS,
                    group=group,
                    note=note,
                )
            )
            if diff:
                gaps.append(
                    {
                        "item": ln.item.name,
                        "unit": unit,
                        "challan": t["qty"],
                        "received": ln.received_qty,
                        "diff": diff,
                    }  # fmt: skip
                )
        ol = ln.order_line
        rows.append(
            _row(
                f"line{n}_order",
                "On the Order",
                f"{_qty(ol.qty)} {unit} ({ol.order.number})" if ol.order.number else "",
                "",
                INFO,
                group=group,
                note="Shown for reference",
            )
        )
    return rows, gaps


def _headline(gaps: list[dict]) -> str:
    said = []
    for g in gaps:
        challan, received = _qty(g["challan"]), _qty(g["received"])
        n, unit = _qty(abs(g["diff"])), g["unit"]
        if g["diff"] > 0:
            said.append(
                f"The challan says {challan} {unit} of {g['item']}; this receipt has {received}"
                f" {unit} received ({n} {unit} less). If the {n} {unit} never came, enter"
                f' "Received" as {challan} and send {n} back with a Purchase Return, or ask'
                f" the supplier to bill {received}."
            )
        else:
            said.append(
                f"The challan says {challan} {unit} of {g['item']}; this receipt has {received}"
                f" {unit} received ({n} {unit} more than the challan)."
            )
    return " ".join(said)


def compare(r: GoodsReceipt, reading: dict) -> dict:
    qr = reading.get("qr")
    text = reading.get("text", "")
    rows, refuse = _gstin_rows(r, qr, text, doc="challan")
    rows.append(_no_row("challan_no", "Challan No", r.challan_no, qr, text))
    rows.append(_day_row("challan_date", "Challan Date", r.challan_date, qr, text))
    rows += [x for x in (_eway_row(r, text), _vehicle_row(r, text)) if x]
    line_rows, gaps = _line_rows(r, text)
    rows += line_rows
    differences = [x for x in rows if x["result"] in (DIFFERS, WRITTEN)]
    return {
        "rows": rows,
        "differences": len(differences),
        "refuse": refuse,
        "headline": _headline(gaps),
    }


def _summary(rows: list[dict]) -> str:
    said = []
    for x in rows:
        if x["result"] == DIFFERS:
            key = x["key"]
            word = (
                "quantity"
                if key.endswith("_qty")
                else "HSN"
                if key.endswith("_hsn")
                else x["label"]
            )
        elif x["result"] == WRITTEN:
            word = "challan no written differently"
        else:
            continue
        if word not in said:
            said.append(word)
    return ", ".join(said)


def payload(r: GoodsReceipt, attachment: Attachment | None, found: BillReading | None) -> dict:
    files = [{"id": a.pk, "filename": a.filename, "kind": a.kind} for a in challan_files(r)]
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
    result = compare(r, reading)
    result["summary"] = _summary(result["rows"])
    out.update(result)
    return out


def _log(user, r: GoodsReceipt, text: str) -> None:
    AuditEntry.objects.create(
        user=user,
        user_name=user.display_name[:150],
        company_id=r.company_id,
        record_type=KIND,
        record_id=r.pk,
        record_name=str(r)[:200],
        action=AuditEntry.UPDATE,
        changes=[
            {"field": "challan_check", "label": "Challan Check", "old": None, "new": text[:500]}
        ],
    )


def _result_text(p: dict) -> str:
    if p.get("error") and not p.get("rows"):
        return p["error"]
    if p.get("refuse"):
        return " ".join(p["refuse"])
    if not p.get("differences"):
        return "matches the receipt"
    return f"{p['differences']} difference{'s' if p['differences'] != 1 else ''} ({p['summary']})"


def _receipt(request, pk: int) -> GoodsReceipt:
    from buying.receipts import _receipt as find

    return find(request, pk)


def _check(request, action: str) -> None:
    from buying.receipts import _check as check

    check(request, action)


class ChallanCheckView(APIView):
    """GET the Challan Check box (cheap: no reading). POST {attachment?, again?}
    reads the challan (once per file unless "again") and compares."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, "view")
        r = _receipt(request, pk)
        attachment = _pick(r)
        found = BillReading.objects.filter(attachment=attachment).first() if attachment else None
        return Response(payload(r, attachment, found))

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "view")
        r = _receipt(request, pk)
        raw = request.data.get("attachment")
        try:
            wanted = int(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            raise ValidationError({"attachment": ["Pick a file."]}) from None
        attachment = _pick(r, wanted)
        if attachment is None:
            raise ValidationError(
                {"detail": "Attach the supplier's challan (a PDF or photo) to check it."}
            )
        again = bool(request.data.get("again"))
        fresh = again or not BillReading.objects.filter(attachment=attachment).exists()
        found = read(attachment, request.user, again=again)
        out = payload(r, attachment, found)
        if fresh:
            _log(request.user, r, f"Challan Check of {attachment.filename}: {_result_text(out)}")
        return Response(out)


class ChallanCheckSeenView(APIView):
    """POST {reason}: the differences are known and accepted (kept in Activity)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, "submit")
        r = _receipt(request, pk)
        reason = str(request.data.get("reason", "")).strip()[:300]
        if not reason:
            raise ValidationError({"reason": ["Say why the differences are all right."]})
        attachment = _pick(r)
        found = BillReading.objects.filter(attachment=attachment).first() if attachment else None
        if found is None:
            raise NotFound("Check the challan first.")
        _seen(found, request.user, reason)
        _log(request.user, r, f"Challan Check differences marked as seen: {reason}")
        return Response(payload(r, attachment, found))


def refuse_submit(r: GoodsReceipt, user, reason: str = "") -> Response | None:
    """Before Submit, as on the invoice (bill_check.refuse_submit): a 400 with the
    Challan Check, without raising so the saved draft is kept, or None."""
    attachment = _pick(r)
    if attachment is None:
        return None
    found = read(attachment, user)
    p = payload(r, attachment, found)
    reason = (reason or "").strip()[:300]
    if p.get("refuse"):
        return Response(
            {"bill_check": p, "detail": " ".join(p["refuse"]), "id": r.pk},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not p.get("differences") or found.seen_reason:
        return None
    refused = BillCheckSetting.current().on_difference == BillCheckSetting.REFUSE
    if reason and (not refused or user.is_owner):
        _seen(found, user, reason)
        _log(user, r, f"Submitted with {_result_text(p)}. Reason: {reason}")
        return None
    detail = "The supplier's challan does not match this receipt."
    if refused and not user.is_owner:
        detail += " Correct the receipt first: only an Owner may submit it as it is."
    return Response(
        {"bill_check": p, "detail": detail, "id": r.pk, "refused": refused and not user.is_owner},
        status=status.HTTP_400_BAD_REQUEST,
    )
