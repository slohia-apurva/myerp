"""Debit notes to suppliers (Sidharth, 2026-11-15, preview 75): goods sent back
on purchase returns, debited against the supplier's bill that billed them, at
that bill's rate and GST.

Submit posts (posting.service):
* Dr the supplier, against the bill: what we owe falls by the note's total;
* Cr "Goods Received but Bills not Received" for the returned goods' receipt
  value (the return put it there);
* Cr Input CGST / SGST / IGST: the input tax is reversed;
* the difference between the bill's value and the receipt value to "Purchase
  Price Difference"; the rupee rounding to Round Off.
No stock moves: the return took the goods out.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import CANCEL, CREATE, SUBMIT, VIEW, _check, _company, _plain
from buying.invoices import _gst, _side, _text, grni_value
from buying.models import (
    DebitNote,
    DebitNoteLine,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseReturn,
    PurchaseReturnLine,
)
from core import attachments, numbering
from core.api import Signed
from core.companies import visible_companies
from posting import accounts, service
from posting.models import GLEntry
from posting.service import GLLine, Voucher, money
from tenancy.context import tenant_atomic

KIND = "debit_note"
ZERO = Decimal("0")
RUPEE = Decimal("1")


# What is left to debit -------------------------------------------------------


def _debited_on(invoice_line: PurchaseInvoiceLine, exclude=None) -> Decimal:
    rows = DebitNoteLine.objects.filter(invoice_line=invoice_line, note__status=DebitNote.SUBMITTED)
    if exclude is not None:
        rows = rows.exclude(note=exclude)
    return rows.aggregate(q=Sum("qty"))["q"] or ZERO


def _over(rl: GoodsReceiptLine) -> Decimal:
    """Goods both billed and sent back, not yet settled by a debit note."""
    return max(rl.billed_qty + rl.returned_qty - rl.accepted_qty, ZERO) - rl.debited_qty


def _left(il: PurchaseInvoiceLine, rln: PurchaseReturnLine, note=None) -> Decimal:
    rl = il.receipt_line
    return max(
        min(rln.qty - rln.debited_qty, il.qty - _debited_on(il, note), _over(rl)),
        ZERO,
    )


# Reading ---------------------------------------------------------------------


def _notes(company):
    return DebitNote.objects.filter(company=company).select_related(
        "supplier__party", "branch", "invoice", "created_by", "submitted_by"
    )


def _line_out(ln: DebitNoteLine, note: DebitNote) -> dict:
    left = _left(ln.invoice_line, ln.return_line, note)
    if note.status == DebitNote.SUBMITTED:
        left += ln.qty
    return {
        "id": ln.pk,
        "invoice_line": ln.invoice_line_id,
        "return_line": ln.return_line_id,
        "return_number": ln.return_line.ret.number,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "hsn": ln.item.hsn,
        "unit_name": ln.unit.short_name or ln.unit.name,
        "billed_qty": _plain(ln.invoice_line.qty),
        "left_qty": _plain(left),
        "qty": _plain(ln.qty),
        "rate": _plain(ln.rate),
        "taxable": ln.taxable,
        "gst_rate": _plain(ln.gst_rate),
        "cgst": ln.cgst,
        "sgst": ln.sgst,
        "igst": ln.igst,
        "amount": ln.amount,
    }


def _dues_after(note: DebitNote) -> list[dict]:
    """The bill's due dates less its debit notes (this one included), taken
    off the latest due first."""
    inv = note.invoice
    others = (
        DebitNote.objects.filter(invoice=inv, status=DebitNote.SUBMITTED)
        .exclude(pk=note.pk)
        .aggregate(t=Sum("total"))["t"]
        or ZERO
    )
    less = others + (note.total if note.status != DebitNote.CANCELLED else ZERO)
    rows = [{"due_date": d.due_date, "bill": d.amount, "less": ZERO} for d in inv.dues.all()]
    for row in reversed(rows):
        take = min(row["bill"], less)
        row["less"] = take
        less -= take
    for row in rows:
        row["now_due"] = row["bill"] - row["less"]
    return rows


def _note_out(note: DebitNote, lines: bool = True) -> dict:
    inv = note.invoice
    data = {
        "id": note.pk,
        "company": note.company_id,
        "number": note.number,
        "status": note.status,
        "status_label": note.get_status_display(),
        "supplier": note.supplier_id,
        "supplier_name": note.supplier.name,
        "supplier_gstin": note.supplier.party.gstin if note.supplier.party else "",
        "branch": note.branch_id,
        "branch_name": note.branch.name,
        "invoice": inv.pk,
        "invoice_number": inv.number,
        "bill_no": inv.bill_no,
        "bill_date": inv.bill_date,
        "note_date": note.note_date,
        "reason": note.reason,
        "reason_label": note.get_reason_display(),
        "supplier_note_no": note.supplier_note_no,
        "supplier_note_date": note.supplier_note_date,
        "interstate": note.interstate,
        "taxable_total": note.taxable_total,
        "cgst_total": note.cgst_total,
        "sgst_total": note.sgst_total,
        "igst_total": note.igst_total,
        "round_off": note.round_off,
        "total": note.total,
        "notes": note.notes,
        "cancel_reason": note.cancel_reason,
        "created_by_name": note.created_by.display_name if note.created_by else "",
        "created_at": note.created_at,
        "submitted_at": note.submitted_at,
        "submitted_by_name": note.submitted_by.display_name if note.submitted_by else "",
    }
    if lines:
        rows = note.lines.select_related(
            "item", "unit", "invoice_line__receipt_line", "return_line__ret"
        )
        data["lines"] = [_line_out(ln, note) for ln in rows]
        data["returns"] = sorted({x["return_number"] for x in data["lines"]})
        data["dues_after"] = _dues_after(note)
        data["entries"] = _entries(note)
    return _text(data)


def _fresh(note: DebitNote) -> dict:
    return _note_out(_notes(note.company).get(pk=note.pk))


def _entries(note: DebitNote) -> list[dict]:
    if note.status == DebitNote.SUBMITTED:
        rows = GLEntry.objects.filter(
            voucher_type=KIND, voucher_id=note.pk, is_reversal=False
        ).select_related("ledger")
        return [
            {"ledger": e.ledger.name, "why": e.remarks, "debit": e.debit, "credit": e.credit}
            for e in rows
        ]
    if note.status != DebitNote.DRAFT or not note.lines.exists():
        return []
    gl, _values = _plan(note, preview=True)
    return [
        {"ledger": g.ledger.name, "why": g.remarks, "debit": g.debit, "credit": g.credit}
        for g in gl
    ]


# Saving ----------------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    invoice_line = serializers.IntegerField()
    return_line = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))


class NoteSerializer(serializers.Serializer):
    invoice = serializers.IntegerField()
    note_date = serializers.DateField()
    reason = serializers.ChoiceField(choices=DebitNote.REASONS, default="returned")
    supplier_note_no = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )
    supplier_note_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _save(note: DebitNote, data: dict) -> None:
    company = note.company
    inv = (
        PurchaseInvoice.objects.filter(
            pk=data["invoice"], company=company, status=PurchaseInvoice.SUBMITTED
        )
        .select_related("supplier", "branch")
        .first()
    )
    if inv is None:
        raise ValidationError({"invoice": ["Pick a submitted purchase invoice of this company."]})
    rows, errors = [], []
    for n, line in enumerate(data.get("lines") or [], start=1):
        if not line["qty"]:
            continue
        il = (
            inv.lines.select_related("receipt_line", "item", "unit")
            .filter(pk=line["invoice_line"])
            .first()
        )
        if il is None:
            errors.append(f"Line {n}: pick a line of {inv.number}.")
            continue
        rln = (
            PurchaseReturnLine.objects.select_related("ret")
            .filter(
                pk=line["return_line"],
                ret__status=PurchaseReturn.SUBMITTED,
                receipt_line=il.receipt_line,
            )
            .first()
        )
        if rln is None:
            errors.append(f"Line {n}: pick a submitted return of {il.item.name} from that receipt.")
            continue
        left = _left(il, rln, note if note.pk else None)
        if line["qty"] > left:
            errors.append(
                f"Line {n}: only {_plain(left)} {il.unit.short_name} of {il.item.name} "
                "was sent back and is still to be debited."
            )
            continue
        taxable = money(line["qty"] * il.rate)
        cgst, sgst, igst = _gst(taxable, il.gst_rate, inv.interstate)
        rows.append(
            DebitNoteLine(
                position=len(rows) + 1,
                invoice_line=il,
                return_line=rln,
                item=il.item,
                unit=il.unit,
                qty=line["qty"],
                rate=il.rate,
                taxable=taxable,
                gst_rate=il.gst_rate,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                amount=taxable + cgst + sgst + igst,
            )
        )
    if errors:
        raise ValidationError({"lines": errors})
    note.invoice, note.supplier, note.branch = inv, inv.supplier, inv.branch
    note.interstate = inv.interstate
    note.note_date = data["note_date"]
    note.reason = data.get("reason") or "returned"
    note.supplier_note_no = data.get("supplier_note_no", "").strip()
    note.supplier_note_date = data.get("supplier_note_date")
    note.notes = data.get("notes", "").strip()
    note.taxable_total = sum((r.taxable for r in rows), ZERO)
    note.cgst_total = sum((r.cgst for r in rows), ZERO)
    note.sgst_total = sum((r.sgst for r in rows), ZERO)
    note.igst_total = sum((r.igst for r in rows), ZERO)
    exact = note.taxable_total + note.cgst_total + note.sgst_total + note.igst_total
    note.total = exact.quantize(RUPEE, rounding=ROUND_HALF_UP)
    note.round_off = note.total - exact
    note.save()
    note.lines.all().delete()
    for r in rows:
        r.note = note
    DebitNoteLine.objects.bulk_create(rows)


# Posting ---------------------------------------------------------------------


def _plan(note: DebitNote, preview: bool = False, work=None):
    """The GL lines, and each line's receipt value back into "Goods Received
    but Bills not Received" (worked out in turn, so the line that settles a
    receipt line takes exactly what is left)."""
    company = note.company
    lines = list(
        note.lines.select_related("item", "invoice_line__receipt_line", "return_line__ret")
    )
    if work is None:
        work = {}
        for ln in lines:
            rl = ln.invoice_line.receipt_line
            work.setdefault(rl.pk, GoodsReceiptLine.objects.get(pk=rl.pk))
    values = {}
    for ln in lines:
        rl = work[ln.invoice_line.receipt_line_id]
        value = grni_value(rl, ln.qty, sign=1)
        values[ln.pk] = value
        rl.debited_qty += ln.qty
        rl.debited_value += value

    def ledger(code):
        if preview:
            from core.models import Ledger
            from posting.accounts import SYSTEM_LEDGERS

            found = Ledger.objects.filter(company=company, system_code=code).first()
            return found or Ledger(company=company, name=SYSTEM_LEDGERS[code][0])
        return accounts.system_ledger(company, code)

    grni = sum(values.values(), ZERO)
    returns = ", ".join(sorted({ln.return_line.ret.number for ln in lines}))
    inv = note.invoice
    gl = [
        GLLine(
            note.supplier,
            debit=note.total,
            remarks=f"Against bill {inv.bill_no}: reduces what we owe".strip(),
        ),
        GLLine(ledger(accounts.GRNI), credit=grni, remarks=f"Clears goods sent back on {returns}"),
    ]
    for code, value in (
        (accounts.INPUT_CGST, note.cgst_total),
        (accounts.INPUT_SGST, note.sgst_total),
        (accounts.INPUT_IGST, note.igst_total),
    ):
        if value:
            gl.append(GLLine(ledger(code), credit=value, remarks="Input GST reversed"))
    if grni != note.taxable_total:
        gl.append(
            _side(
                ledger(accounts.PRICE_DIFFERENCE),
                grni - note.taxable_total,
                "Bill value differs from the receipt value",
            )
        )
    if note.round_off:
        gl.append(_side(ledger(accounts.ROUND_OFF), -note.round_off, ""))
    return gl, values


def _submit(note: DebitNote, user) -> None:
    if not user.can(SUBMIT):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    attachments.require_file(note, KIND)
    lines = list(note.lines.select_related("item", "invoice_line", "return_line"))
    if not lines:
        raise ValidationError({"lines": ["Give the quantity to debit on at least one line."]})
    if note.note_date < (note.invoice.posting_date or note.note_date):
        raise ValidationError(
            {"note_date": [f"The bill was posted on {note.invoice.posting_date:%d-%m-%Y}."]}
        )
    work = {}
    for ln in lines:
        rl_id = ln.invoice_line.receipt_line_id
        if rl_id not in work:
            work[rl_id] = GoodsReceiptLine.objects.select_for_update().get(pk=rl_id)
        rln = PurchaseReturnLine.objects.select_for_update().get(pk=ln.return_line_id)
        ln.return_line = rln
    for ln in lines:
        left = _left(ln.invoice_line, ln.return_line, note)
        if ln.qty > left:
            raise ValidationError(
                {"lines": [f"{ln.item.name}: only {_plain(left)} is still to be debited."]}
            )
    note.number = numbering.next_document_number(note.company, KIND, note.note_date, note.branch)
    note.save(update_fields=["number"])
    gl, values = _plan(note, work=work)
    voucher = Voucher(note.company, note.branch, note.note_date, KIND, note.pk, note.number, user)
    service.post(voucher, gl=gl)
    for ln in lines:
        ln.receipt_value = values[ln.pk]
        ln.save(update_fields=["receipt_value"])
        PurchaseReturnLine.objects.filter(pk=ln.return_line_id).update(
            debited_qty=ln.return_line.debited_qty + ln.qty
        )
        ln.return_line.debited_qty += ln.qty
    for rl in work.values():
        rl.save(update_fields=["debited_qty", "debited_value"])
    note.status = DebitNote.SUBMITTED
    note.submitted_at = timezone.now()
    note.submitted_by = user
    note.save()


def _cancel(note: DebitNote, user, reason: str) -> None:
    if note.status == DebitNote.SUBMITTED:
        service.cancel(KIND, note.pk, user)
        for ln in note.lines.select_related("invoice_line"):
            rl = GoodsReceiptLine.objects.select_for_update().get(
                pk=ln.invoice_line.receipt_line_id
            )
            rl.debited_qty -= ln.qty
            rl.debited_value -= ln.receipt_value
            rl.save(update_fields=["debited_qty", "debited_value"])
            rln = PurchaseReturnLine.objects.select_for_update().get(pk=ln.return_line_id)
            rln.debited_qty -= ln.qty
            rln.save(update_fields=["debited_qty"])
    note.status = DebitNote.CANCELLED
    note.cancel_reason = reason[:200]
    note.save()


def invoice_debited(inv: PurchaseInvoice) -> str:
    """Why an invoice cannot be cancelled: the debit notes against it."""
    numbers = DebitNote.objects.filter(invoice=inv, status=DebitNote.SUBMITTED).values_list(
        "number", flat=True
    )
    return ", ".join(numbers)


# A new note from an invoice or a return --------------------------------------


def _pairs(invoice_lines, return_lines) -> list[dict]:
    out = []
    used: dict[int, Decimal] = {}
    for il in invoice_lines:
        rl = il.receipt_line
        for rln in return_lines:
            if rln.receipt_line_id != rl.pk:
                continue
            left = _left(il, rln) - used.get(rl.pk, ZERO)
            if left <= 0:
                continue
            used[rl.pk] = used.get(rl.pk, ZERO) + left
            out.append(
                {
                    "invoice_line": il.pk,
                    "return_line": rln.pk,
                    "return_number": rln.ret.number,
                    "item": il.item_id,
                    "item_name": il.item.name,
                    "hsn": il.item.hsn,
                    "unit_name": il.unit.short_name or il.unit.name,
                    "billed_qty": _plain(il.qty),
                    "left_qty": _plain(left),
                    "qty": _plain(left),
                    "rate": _plain(il.rate),
                    "gst_rate": _plain(il.gst_rate),
                }
            )
    return out


def _submitted_return_lines(**where):
    return list(
        PurchaseReturnLine.objects.select_related("ret")
        .filter(ret__status=PurchaseReturn.SUBMITTED, **where)
        .order_by("ret__return_date", "ret_id", "position")
    )


def _draft_for(inv: PurchaseInvoice, lines: list[dict]) -> dict:
    if not lines:
        raise ValidationError(
            {
                "detail": "Nothing billed on this invoice has been sent back and not yet "
                "debited. Make a Purchase Return from the goods receipt first."
            }
        )
    return _text(
        {
            "invoice": inv.pk,
            "invoice_number": inv.number,
            "bill_no": inv.bill_no,
            "bill_date": inv.bill_date,
            "supplier": inv.supplier_id,
            "supplier_name": inv.supplier.name,
            "branch": inv.branch_id,
            "interstate": inv.interstate,
            "lines": lines,
        }
    )


def _draft_from_invoice(inv: PurchaseInvoice) -> dict:
    ils = list(inv.lines.select_related("receipt_line", "item", "unit"))
    rls = _submitted_return_lines(receipt_line__in=[il.receipt_line_id for il in ils])
    return _draft_for(inv, _pairs(ils, rls))


def _draft_from_return(r: PurchaseReturn) -> dict:
    rls = _submitted_return_lines(ret=r)
    ils = list(
        PurchaseInvoiceLine.objects.select_related("receipt_line", "item", "unit", "invoice")
        .filter(
            receipt_line__in=[x.receipt_line_id for x in rls],
            invoice__status=PurchaseInvoice.SUBMITTED,
        )
        .order_by("invoice__posting_date", "invoice_id", "position")
    )
    by_invoice: dict[int, list] = {}
    for il in ils:
        by_invoice.setdefault(il.invoice_id, []).append(il)
    for group in by_invoice.values():
        if lines := _pairs(group, rls):
            return _draft_for(group[0].invoice, lines)
    raise ValidationError(
        {
            "detail": "These goods are not billed yet: once the supplier's bill is entered, "
            "make the Debit Note from it. If the bill leaves them out, no Debit Note is needed."
        }
    )


# Views -----------------------------------------------------------------------


def _note(request, pk: int, lock: bool = False) -> DebitNote:
    rows = DebitNote.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    note = rows.select_related("company", "invoice").first()
    if note is None or "purchase" not in note.company.modules:
        raise NotFound("No such debit note.")
    return note


class NoteListView(APIView):
    """GET ?view=submitted|draft|cancelled|all&q=text. POST makes a draft (or,
    with "submit": true, submits it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = _notes(company)
        view = request.query_params.get("view", "submitted")
        if view in (DebitNote.DRAFT, DebitNote.SUBMITTED, DebitNote.CANCELLED):
            rows = rows.filter(status=view)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(supplier__name__icontains=word)
                | Q(invoice__number__icontains=word)
                | Q(invoice__bill_no__icontains=word)
            ).distinct()
        return Response([_note_out(n, lines=False) for n in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        note = DebitNote(company=company, created_by=request.user, note_date=data["note_date"])
        _save(note, data)
        if data.get("submit"):
            _check(request, SUBMIT)
            if refused := attachments.refuse_submit(note, KIND):
                return refused
            _submit(note, request.user)
        return Response(_fresh(note), status=status.HTTP_201_CREATED)


class NoteDetailView(APIView):
    """GET one note; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(_fresh(_note(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        note = _note(request, pk, lock=True)
        if note.status != DebitNote.DRAFT:
            raise ValidationError(
                {
                    "detail": "A submitted debit note cannot be changed. "
                    "Cancel it and make a new one."
                }
            )
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(note, data)
        if data.get("submit"):
            _check(request, SUBMIT)
            if refused := attachments.refuse_submit(note, KIND):
                return refused
            _submit(note, request.user)
        return Response(_fresh(note))


class NoteCancelView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CANCEL)
        note = _note(request, pk, lock=True)
        if note.status == DebitNote.CANCELLED:
            raise ValidationError({"detail": "This debit note is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(note, request.user, reason)
        return Response(_fresh(note))


class NoteDraftFromView(APIView):
    """GET ?invoice=ID or ?return=ID: a new note's lines, for "Create ▾ › Debit Note"."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        q = request.query_params
        if (v := q.get("invoice", "")).isdigit():
            inv = PurchaseInvoice.objects.filter(
                pk=int(v), company=company, status=PurchaseInvoice.SUBMITTED
            ).first()
            if inv is None:
                raise ValidationError({"invoice": ["Pick a submitted purchase invoice."]})
            return Response(_draft_from_invoice(inv))
        if (v := q.get("return", "")).isdigit():
            r = PurchaseReturn.objects.filter(
                pk=int(v), company=company, status=PurchaseReturn.SUBMITTED
            ).first()
            if r is None:
                raise ValidationError({"return": ["Pick a submitted purchase return."]})
            return Response(_draft_from_return(r))
        raise ValidationError({"detail": "Name the invoice or the return."})
