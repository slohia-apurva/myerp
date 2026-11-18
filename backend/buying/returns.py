"""Purchase returns (Sidharth, 2026-11-15, preview 74): goods sent back to the
supplier from one goods receipt.

Each line sends back a quantity of a receipt line from one bin (and batch).
Submit posts (posting.service):
* the goods out of stock, from the receipt's own lots first (FIFO for any
  rest): Cr the item's stock ledger;
* Dr "Goods Received but Bills not Received" for their receipt value;
* any difference between the two (the bill has revalued the lot since) to
  "Purchase Price Difference".
No GST and no supplier entry: the Debit Note against the supplier's bill does
that. If the bill leaves the returned goods out, the return alone settles them.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import _company, _plain
from buying.invoices import _lots, _side, _text, grni_value, open_qty
from buying.models import GoodsReceipt, GoodsReceiptLine, PurchaseReturn, PurchaseReturnLine
from buying.receipts import _factor, can
from core import attachments, numbering
from core.api import Signed
from core.companies import visible_companies
from core.models import Batch, WarehouseLocation
from posting import accounts, service
from posting.models import GLEntry
from posting.service import GLLine, StockLine, Voucher, on_hand
from shipping.models import CourierAccount
from tenancy.context import tenant_atomic

KIND = "purchase_return"
ZERO = Decimal("0")
VIEW, CREATE, SUBMIT, CANCEL = "view", "create", "submit", "cancel"


def _check(request, action: str) -> None:
    from rest_framework.exceptions import PermissionDenied

    if not can(request.user, action):
        raise PermissionDenied("Your role does not allow this.")


def returnable(rl: GoodsReceiptLine) -> Decimal:
    return max(rl.accepted_qty - rl.returned_qty, ZERO)


# Reading ---------------------------------------------------------------------


def _returns(company):
    return PurchaseReturn.objects.filter(company=company).select_related(
        "supplier", "branch", "receipt", "transporter", "created_by", "submitted_by"
    )


def _places(rl: GoodsReceiptLine) -> list[dict]:
    """Where the receipt line's goods were put, with what is there now."""
    factor = _factor(rl.item, rl.unit_id)
    seen, out = set(), []
    for p in rl.putaways.select_related("location__parent", "batch"):
        key = (p.location_id, p.batch_id)
        if key in seen:
            continue
        seen.add(key)
        here = on_hand(rl.item, p.location, p.batch) / factor if factor else ZERO
        out.append(
            {
                "location": p.location_id,
                "location_name": str(p.location),
                "batch": p.batch_id,
                "batch_number": p.batch.number if p.batch else "",
                "on_hand": _plain(here),
            }
        )
    return out


def _line_out(ln: PurchaseReturnLine) -> dict:
    rl = ln.receipt_line
    return {
        "id": ln.pk,
        "receipt_line": rl.pk,
        "item": ln.item_id,
        "item_name": ln.item.name,
        "hsn": ln.item.hsn,
        "unit_name": ln.unit.short_name or ln.unit.name,
        "location": ln.location_id,
        "location_name": str(ln.location),
        "batch": ln.batch_id,
        "batch_number": ln.batch.number if ln.batch else "",
        "received_qty": _plain(rl.accepted_qty),
        "returned_before": _plain(
            rl.returned_qty - (ln.qty if ln.ret.status == "submitted" else 0)
        ),
        "qty": _plain(ln.qty),
        "receipt_rate": _plain(_unit_value(rl)),
        "receipt_value": rl.value,
        "value": ln.value if ln.ret.status == "submitted" else _estimate(rl, ln.qty),
        "stock_value": ln.stock_value,
        "debited_qty": _plain(ln.debited_qty),
        "billed": rl.billed_qty > 0,
    }


def _unit_value(rl: GoodsReceiptLine) -> Decimal:
    return (rl.value / rl.accepted_qty).quantize(Decimal("0.01")) if rl.accepted_qty else ZERO


def _estimate(rl: GoodsReceiptLine, qty: Decimal) -> Decimal:
    return grni_value(rl, qty) if qty else ZERO


def _return_out(r: PurchaseReturn, lines: bool = True) -> dict:
    data = {
        "id": r.pk,
        "company": r.company_id,
        "number": r.number,
        "status": r.status,
        "status_label": r.get_status_display(),
        "supplier": r.supplier_id,
        "supplier_name": r.supplier.name,
        "branch": r.branch_id,
        "branch_name": r.branch.short_name,
        "receipt": r.receipt_id,
        "receipt_number": r.receipt.number,
        "receipt_date": r.receipt.receipt_date,
        "challan_no": r.receipt.challan_no,
        "return_date": r.return_date,
        "reason": r.reason,
        "reason_label": r.get_reason_display(),
        "transporter": r.transporter_id,
        "transporter_name": r.transporter.name if r.transporter_id else "By Supplier",
        "lr_no": r.lr_no,
        "vehicle_no": r.vehicle_no,
        "eway_bill_no": r.eway_bill_no,
        "notes": r.notes,
        "value": r.value,
        "cancel_reason": r.cancel_reason,
        "created_by_name": r.created_by.display_name if r.created_by else "",
        "created_at": r.created_at,
        "submitted_at": r.submitted_at,
        "submitted_by_name": r.submitted_by.display_name if r.submitted_by else "",
    }
    if lines:
        rows = list(
            r.lines.select_related(
                "item", "unit", "location__parent", "batch", "receipt_line", "ret"
            )
        )
        data["lines"] = [_line_out(ln) for ln in rows]
        if r.status == PurchaseReturn.DRAFT:
            data["value"] = sum((x["value"] for x in data["lines"]), ZERO)
        data["to_debit"] = any(ln.qty > ln.debited_qty and ln.receipt_line.billed_qty > 0
                               for ln in rows) and r.status == PurchaseReturn.SUBMITTED  # fmt: skip
        data["entries"] = _entries(r)
    return _text(data)


def _fresh(r: PurchaseReturn) -> dict:
    return _return_out(_returns(r.company).get(pk=r.pk))


def _entries(r: PurchaseReturn) -> list[dict]:
    if r.status == PurchaseReturn.SUBMITTED:
        rows = GLEntry.objects.filter(
            voucher_type=KIND, voucher_id=r.pk, is_reversal=False
        ).select_related("ledger")
        return [
            {"ledger": e.ledger.name, "why": e.remarks, "debit": e.debit, "credit": e.credit}
            for e in rows
        ]
    if r.status != PurchaseReturn.DRAFT:
        return []
    # A draft shows what Submit would post, at the receipt's cost.
    lines = [ln for ln in r.lines.select_related("item", "receipt_line") if ln.qty]
    if not lines:
        return []
    try:
        grni = accounts.system_ledger(r.company, accounts.GRNI)
        per_ledger: dict[int, list] = {}
        for ln in lines:
            led = accounts.stock_ledger(r.company, ln.item)
            per_ledger.setdefault(led.pk, [led, ZERO])[1] += _estimate(ln.receipt_line, ln.qty)
    except ValidationError as err:
        return [{"ledger": "", "why": _first_message(err), "debit": ZERO, "credit": ZERO}]
    total = sum((v for _led, v in per_ledger.values()), ZERO)
    out = [{"ledger": grni.name, "why": f"Sent back from {r.receipt.number}", "debit": total,
            "credit": ZERO}]  # fmt: skip
    for led, v in per_ledger.values():
        out.append(
            {"ledger": led.name, "why": f"Back to {r.supplier.name}", "debit": ZERO, "credit": v}
        )
    return out


def _first_message(err: ValidationError) -> str:
    detail = err.detail
    while isinstance(detail, dict | list):
        detail = next(iter(detail.values())) if isinstance(detail, dict) else detail[0]
    return str(detail)


# Saving ----------------------------------------------------------------------


class LineSerializer(serializers.Serializer):
    receipt_line = serializers.IntegerField()
    location = serializers.IntegerField()
    batch = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))


class ReturnSerializer(serializers.Serializer):
    receipt = serializers.IntegerField()
    return_date = serializers.DateField()
    reason = serializers.ChoiceField(choices=PurchaseReturn.REASONS, default="damaged")
    transporter = serializers.IntegerField(required=False, allow_null=True)
    lr_no = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    vehicle_no = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    eway_bill_no = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True, required=False, default=list)
    submit = serializers.BooleanField(required=False, default=False)


def _save(r: PurchaseReturn, data: dict) -> None:
    company = r.company
    receipt = GoodsReceipt.objects.filter(
        pk=data["receipt"], company=company, status=GoodsReceipt.SUBMITTED
    ).first()
    if receipt is None:
        raise ValidationError({"receipt": ["Pick a submitted goods receipt of this company."]})
    transporter = None
    if data.get("transporter"):
        transporter = CourierAccount.objects.filter(pk=data["transporter"], company=company).first()
        if transporter is None:
            raise ValidationError({"transporter": ["Pick a transporter from the list."]})
    rows, errors, wanted = [], [], {}
    for n, line in enumerate(data.get("lines") or [], start=1):
        if not line["qty"]:
            continue  # lines left at 0 are not going back
        rl = receipt.lines.select_related("item", "unit").filter(pk=line["receipt_line"]).first()
        if rl is None:
            errors.append(f"Line {n}: pick a line of {receipt.number}.")
            continue
        loc = WarehouseLocation.objects.filter(pk=line["location"], branch=receipt.branch).first()
        if loc is None:
            errors.append(f"Line {n}: pick a bin of {receipt.branch}.")
            continue
        batch = None
        if line.get("batch"):
            batch = Batch.objects.filter(pk=line["batch"], item=rl.item).first()
            if batch is None:
                errors.append(f"Line {n}: pick a batch of {rl.item.name}.")
                continue
        wanted[rl.pk] = wanted.get(rl.pk, ZERO) + line["qty"]
        if wanted[rl.pk] > returnable(rl):
            errors.append(
                f"Line {n}: only {_plain(returnable(rl))} {rl.unit.short_name} of "
                f"{rl.item.name} on {receipt.number} can still go back."
            )
            continue
        rows.append(
            PurchaseReturnLine(
                position=len(rows) + 1,
                receipt_line=rl,
                item=rl.item,
                unit=rl.unit,
                location=loc,
                batch=batch,
                qty=line["qty"],
            )
        )
    if errors:
        raise ValidationError({"lines": errors})
    r.receipt, r.supplier, r.branch = receipt, receipt.supplier, receipt.branch
    r.return_date = data["return_date"]
    r.reason = data.get("reason") or "damaged"
    r.transporter = transporter
    r.lr_no = data.get("lr_no", "").strip()
    r.vehicle_no = data.get("vehicle_no", "").strip().upper()
    r.eway_bill_no = data.get("eway_bill_no", "").strip()
    r.notes = data.get("notes", "").strip()
    r.save()
    r.lines.all().delete()
    for x in rows:
        x.ret = r
    PurchaseReturnLine.objects.bulk_create(rows)


# Posting ---------------------------------------------------------------------


def _submit(r: PurchaseReturn, user) -> None:
    if not can(user, SUBMIT):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Your role may save drafts but not submit them.")
    attachments.require_file(r, KIND)
    lines = list(r.lines.select_related("item", "unit", "location", "batch"))
    if not lines:
        raise ValidationError({"lines": ["Give the quantity going back on at least one line."]})
    if r.return_date < r.receipt.receipt_date:
        raise ValidationError(
            {"return_date": [f"The goods came in on {r.receipt.receipt_date:%d-%m-%Y}."]}
        )
    # Lock the receipt lines; work out each line's receipt value in turn, as
    # if each were its own document, so the last to close a line takes the rest.
    work: dict[int, GoodsReceiptLine] = {}
    for ln in lines:
        if ln.receipt_line_id not in work:
            work[ln.receipt_line_id] = GoodsReceiptLine.objects.select_for_update().get(
                pk=ln.receipt_line_id
            )
    grni: dict[int, Decimal] = {}
    for ln in lines:
        rl = work[ln.receipt_line_id]
        if ln.qty > returnable(rl):
            raise ValidationError(
                {"lines": [f"{ln.item.name}: only {_plain(returnable(rl))} can still go back."]}
            )
        value = grni_value(rl, ln.qty)
        grni[ln.pk] = value
        rl.returned_qty += ln.qty
        rl.returned_value += value
    r.number = numbering.next_document_number(r.company, KIND, r.return_date, r.branch)
    r.save(update_fields=["number"])

    stock = [
        StockLine(
            ln.item,
            ln.location,
            -ln.qty * _factor(ln.item, ln.unit_id),
            batch=ln.batch,
            lots=[lot.pk for lot in _lots(work[ln.receipt_line_id])],
        )
        for ln in lines
    ]
    company = r.company

    def gl(values):
        out, per_ledger, total_stock = [], {}, ZERO
        for ln, v in zip(lines, values, strict=True):
            led = accounts.stock_ledger(company, ln.item)
            per_ledger.setdefault(led.pk, [led, ZERO])[1] += -v
            total_stock += -v
        total_grni = sum(grni.values(), ZERO)
        out.append(
            GLLine(
                accounts.system_ledger(company, accounts.GRNI),
                debit=total_grni,
                remarks=f"Sent back from {r.receipt.number}",
            )
        )
        for led, v in per_ledger.values():
            out.append(GLLine(led, credit=v, remarks=f"Back to {r.supplier.name}"))
        if total_stock != total_grni:
            out.append(
                _side(
                    accounts.system_ledger(company, accounts.PRICE_DIFFERENCE),
                    total_stock - total_grni,
                    "Stock value differs from the receipt value",
                )
            )
        return out

    voucher = Voucher(company, r.branch, r.return_date, KIND, r.pk, r.number, user)
    done = service.post(voucher, stock=stock, gl=gl)
    for ln, v in zip(lines, done.stock_values, strict=True):
        ln.value, ln.stock_value = grni[ln.pk], -v
        ln.save(update_fields=["value", "stock_value"])
    for rl in work.values():
        rl.save(update_fields=["returned_qty", "returned_value"])
    r.value = sum(grni.values(), ZERO)
    r.status = PurchaseReturn.SUBMITTED
    r.submitted_at = timezone.now()
    r.submitted_by = user
    r.save()


def _cancel(r: PurchaseReturn, user, reason: str) -> None:
    if r.status == PurchaseReturn.SUBMITTED:
        notes = debit_notes_of(r)
        if notes:
            raise ValidationError(
                {"detail": f"Debit note {notes} settles this return; cancel it first."}
            )
        service.cancel(KIND, r.pk, user)
        for ln in r.lines.all():
            rl = GoodsReceiptLine.objects.select_for_update().get(pk=ln.receipt_line_id)
            rl.returned_qty -= ln.qty
            rl.returned_value -= ln.value
            rl.save(update_fields=["returned_qty", "returned_value"])
    r.status = PurchaseReturn.CANCELLED
    r.cancel_reason = reason[:200]
    r.save()


def debit_notes_of(r: PurchaseReturn) -> str:
    from buying.models import DebitNote

    numbers = (
        DebitNote.objects.filter(lines__return_line__ret=r, status=DebitNote.SUBMITTED)
        .values_list("number", flat=True)
        .distinct()
    )
    return ", ".join(numbers)


def receipt_returned(receipt: GoodsReceipt) -> str:
    """Why a receipt cannot be cancelled: the returns made from it."""
    numbers = PurchaseReturn.objects.filter(
        receipt=receipt, status=PurchaseReturn.SUBMITTED
    ).values_list("number", flat=True)
    return ", ".join(numbers)


def _draft_from(receipt: GoodsReceipt) -> dict:
    """A new return's form: every line of the receipt, one row per bin and
    batch it was put in, at 0 to fill in."""
    lines = []
    for rl in receipt.lines.select_related("item", "unit").filter(accepted_qty__gt=0):
        for place in _places(rl):
            lines.append(
                {
                    "receipt_line": rl.pk,
                    "item": rl.item_id,
                    "item_name": rl.item.name,
                    "hsn": rl.item.hsn,
                    "unit_name": rl.unit.short_name or rl.unit.name,
                    "received_qty": _plain(rl.accepted_qty),
                    "returned_before": _plain(rl.returned_qty),
                    "returnable": _plain(returnable(rl)),
                    "receipt_rate": _plain(_unit_value(rl)),
                    "receipt_value": rl.value,
                    "billed": rl.billed_qty > 0,
                    "open": _plain(open_qty(rl)),
                    "qty": "0",
                    **place,
                }
            )
    return _text(
        {
            "receipt": receipt.pk,
            "receipt_number": receipt.number,
            "receipt_date": receipt.receipt_date,
            "challan_no": receipt.challan_no,
            "supplier": receipt.supplier_id,
            "supplier_name": receipt.supplier.name,
            "branch": receipt.branch_id,
            "branch_name": receipt.branch.short_name,
            "transporter": receipt.transporter_id,
            "vehicle_no": receipt.vehicle_no,
            "lines": lines,
        }
    )


# Views -----------------------------------------------------------------------


def _return(request, pk: int, lock: bool = False) -> PurchaseReturn:
    rows = PurchaseReturn.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    r = rows.select_related("company", "receipt").first()
    if r is None or "purchase" not in r.company.modules:
        raise NotFound("No such purchase return.")
    return r


class ReturnListView(APIView):
    """GET ?view=submitted|draft|cancelled|all&q=text. POST makes a draft (or,
    with "submit": true, submits it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = _returns(company)
        view = request.query_params.get("view", "submitted")
        if view in (PurchaseReturn.DRAFT, PurchaseReturn.SUBMITTED, PurchaseReturn.CANCELLED):
            rows = rows.filter(status=view)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(supplier__name__icontains=word)
                | Q(receipt__number__icontains=word)
                | Q(lines__item__name__icontains=word)
            ).distinct()
        return Response([_return_out(r, lines=False) for r in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        r = PurchaseReturn(company=company, created_by=request.user)
        _save(r, data)
        if data.get("submit"):
            if refused := attachments.refuse_submit(r, KIND):
                return refused
            _submit(r, request.user)
        return Response(_fresh(r), status=status.HTTP_201_CREATED)


class ReturnDetailView(APIView):
    """GET one return; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(_fresh(_return(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        r = _return(request, pk, lock=True)
        if r.status != PurchaseReturn.DRAFT:
            raise ValidationError(
                {"detail": "A submitted return cannot be changed. Cancel it and make a new one."}
            )
        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        _save(r, data)
        if data.get("submit"):
            if refused := attachments.refuse_submit(r, KIND):
                return refused
            _submit(r, request.user)
        return Response(_fresh(r))


class ReturnCancelView(APIView):
    """POST {reason}: the goods come back into stock and the entries are reversed."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CANCEL)
        r = _return(request, pk, lock=True)
        if r.status == PurchaseReturn.CANCELLED:
            raise ValidationError({"detail": "This return is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(r, request.user, reason)
        return Response(_fresh(r))


class ReturnDraftFromView(APIView):
    """GET ?receipt=ID: a new return's lines, for "Create ▾ › Purchase Return"."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        value = request.query_params.get("receipt", "")
        if not value.isdigit():
            raise ValidationError({"receipt": ["Name the goods receipt."]})
        receipt = GoodsReceipt.objects.filter(
            pk=int(value), company=company, status=GoodsReceipt.SUBMITTED
        ).first()
        if receipt is None:
            raise ValidationError({"receipt": ["Pick a submitted goods receipt."]})
        return Response(_draft_from(receipt))


class ReturnableView(APIView):
    """GET: submitted goods receipts with something that can still go back, for
    the picker on a new return."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = (
            GoodsReceipt.objects.filter(company=company, status=GoodsReceipt.SUBMITTED)
            .select_related("supplier")
            .order_by("-receipt_date", "-id")
        )
        out = []
        for r in rows[:500]:
            if any(returnable(rl) > 0 for rl in r.lines.all()):
                out.append(
                    {
                        "id": r.pk,
                        "number": r.number,
                        "receipt_date": r.receipt_date,
                        "supplier_name": r.supplier.name,
                        "challan_no": r.challan_no,
                    }
                )
        return Response(out)
