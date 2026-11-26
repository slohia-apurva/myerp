"""TDS Check and TDS Adjustment (Sidharth, 2026-11-19, previews 95a-c).

TDS Check (Entry › Accounts › TDS Check) runs a supplier's year again: every submitted
purchase bill of the financial year, in date order, worked out with today's
masters (the TDS Section on the item or ledger, the supplier's PAN and type,
and the section's rates and limits on the bill's date; a section chosen by hand
on a bill stays). Against it stands what the bill deducted and what submitted
TDS Adjustments added or gave back. So a bill entered before its item had a
TDS Section shows as short.

A submitted bill is never changed (design rule 1). A gap is put right by a TDS
Adjustment, dated when it is made: TDS missed is deducted now (Dr the supplier,
Cr "TDS Payable <section>"), TDS deducted in excess is given back (the other
way). Each line names a bill; its amount is the gap the check finds when the
adjustment is saved and again on Submit, so it cannot be typed. Interest for
deducting late (the section's rate a month or part of one, from the bill's
date to the adjustment's) is shown for information, to pay with the challan.

A bill whose lines had no section when billed (the item got its section
later) but owes nothing shows as "Section missing" (Sidharth, 2026-11-20,
previews 98a-c): a TDS Adjustment naming it records the section with ₹0 and
posts nothing ("Set section only"). Any submitted adjustment naming a bill
under a section counts as setting that section on it.

Sidharth: the check is run before each quarter's TDS return. Once a quarter is
marked "Return Filed", its bills cannot be adjusted, an adjustment cannot be
dated in it or cancelled from it, and its bills with TDS cannot be cancelled.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying import tds
from buying.api import _company
from buying.invoices import _text
from buying.models import (
    PurchaseInvoice,
    TdsAdjustment,
    TdsAdjustmentLine,
    TdsReturnFiled,
)
from core import attachments, numbering, tds_sections
from core.api import Signed
from core.companies import visible_companies
from core.models import Company, Ledger, Party
from posting import api as posting_api
from posting import service
from posting.service import GLLine, Voucher, money
from tenancy.context import tenant_atomic

KIND = "tds_adjustment"
ZERO = Decimal("0")
VIEW, CREATE, SUBMIT, CANCEL = (f"accounts.{a}" for a in ("view", "create", "submit", "cancel"))


def _check(request, code: str) -> None:
    if not request.user.can(code):
        raise PermissionDenied("Your role does not allow this.")


def _dmy(day: datetime.date | None) -> str:
    return day.strftime("%d-%m-%Y") if day else ""


# Quarters ---------------------------------------------------------------------


def quarter_start(day: datetime.date) -> datetime.date:
    """April-June, July-September, October-December, January-March."""
    return datetime.date(day.year, (day.month - 1) // 3 * 3 + 1, 1)


def quarter_label(start: datetime.date) -> str:
    end_month = start.month + 2
    end = datetime.date(start.year, end_month, 1)
    return f"{start:%b}-{end:%b} {start.year}"


def filed_quarters(company: Company) -> dict[datetime.date, TdsReturnFiled]:
    return {r.quarter_start: r for r in TdsReturnFiled.objects.filter(company=company)}


def refuse_if_filed(company: Company, day: datetime.date, what: str, key: str = "detail") -> None:
    got = TdsReturnFiled.objects.filter(company=company, quarter_start=quarter_start(day)).first()
    if got is not None:
        raise ValidationError(
            {
                key: [
                    f"The TDS return for {quarter_label(got.quarter_start)} is filed "
                    f"(marked on the TDS Check), so {what} cannot be changed."
                ]
            }
        )


def months_late(due: datetime.date, paid: datetime.date) -> int:
    """Months or part of one, counting the month TDS was due and the month it
    is deducted: 4 September to 19 November is 3. An adjustment dated on the
    bill's own date (entered backdated) deducts on time: no interest (Sidharth,
    2026-11-26)."""
    if paid <= due:
        return 0
    return (paid.year - due.year) * 12 + paid.month - due.month + 1


# The check --------------------------------------------------------------------


@dataclass
class BillRow:
    invoice: PurchaseInvoice
    code: str
    taxable: Decimal = ZERO
    year_so_far: Decimal = ZERO  # the supplier's year in the section, with this bill
    base: Decimal = ZERO
    rate: Decimal = ZERO
    due: Decimal = ZERO
    on_bill: Decimal = ZERO  # TDS the bill deducted under the section
    adjusted: Decimal = ZERO  # by submitted TDS Adjustments (signed)
    on_bill_sections: set[str] = field(default_factory=set)
    # Lines that take the section now but had another (or none) on the bill.
    missed: list[str] = field(default_factory=list)
    why: str = ""
    filed: bool = False
    section_set_by: str = ""  # a submitted TDS Adjustment naming the bill under the section

    @property
    def needs_section(self) -> bool:
        return bool(self.missed) and not self.section_set_by

    @property
    def deducted(self) -> Decimal:
        return self.on_bill + self.adjusted

    @property
    def gap(self) -> Decimal:
        return self.due - self.deducted


def run(
    company: Company, start: datetime.date, end: datetime.date, supplier: int | None = None
) -> dict[tuple[int, str], list[BillRow]]:
    """Every submitted bill from `start` to `end`, checked: by (supplier ledger,
    section), the bills in date order."""
    filed = filed_quarters(company)
    bills = (
        PurchaseInvoice.objects.filter(
            company=company,
            status=PurchaseInvoice.SUBMITTED,
            posting_date__range=(start, end),
        )
        .select_related("company", "supplier__party")
        .prefetch_related("tds_rows")
        .order_by("posting_date", "id")
    )
    if supplier is not None:
        bills = bills.filter(supplier_id=supplier)
    adjusted: dict[tuple[int, str], Decimal] = defaultdict(lambda: ZERO)
    set_by: dict[tuple[int, str], str] = {}
    for ln in (
        TdsAdjustmentLine.objects.filter(
            adjustment__company=company,
            adjustment__status=TdsAdjustment.SUBMITTED,
            invoice__in=bills,
        )
        .select_related("adjustment")
        .order_by("adjustment__adj_date", "adjustment_id")
    ):
        adjusted[(ln.invoice_id, ln.adjustment.section)] += ln.amount
        set_by.setdefault((ln.invoice_id, ln.adjustment.section), ln.adjustment.number)
    running: dict[tuple[int, str], tuple[Decimal, Decimal]] = {}
    out: dict[tuple[int, str], list[BillRow]] = defaultdict(list)
    for inv in bills:
        party = inv.supplier.party
        if party is not None and party.gst_type == Party.OVERSEAS:
            continue
        day = tds.bill_day(inv)
        on_bill = {(r.line_kind, r.line_position): r for r in inv.tds_rows.all()}
        groups: dict[str, list] = defaultdict(list)
        for ln, code, why in tds.lines_now(inv):
            if code:
                groups[code].append((ln, why))
        here: dict[str, BillRow] = {}
        for code, group in groups.items():
            row = BillRow(inv, code, taxable=sum((ln.taxable for ln, _ in group), ZERO))
            for ln, _ in group:
                had = on_bill.get((ln.kind, ln.position))
                row.on_bill_sections.add(had.section if had else "")
                if had is None or had.section != code:
                    row.missed.append(ln.label)
            key = (inv.supplier_id, code)
            so_far, so_far_base = running.get(key, (ZERO, ZERO))
            sec = tds_sections.section_on(code, day)
            if sec is None:
                row.why = f"{code} is not in the TDS sections list on {_dmy(day)}."
            else:
                taxables = [ln.taxable for ln, _ in group]
                bases, notes = tds.work_out(sec, taxables, so_far, so_far_base)
                rate = tds.rate_for(sec, party)
                row.base = sum(bases, ZERO)
                row.rate = rate if row.base else ZERO
                row.due = money(sum((tds.rupees(b * rate / 100) for b in bases if b), ZERO))
                row.why = next((text for text, _ in notes if text), "")
            running[key] = (so_far + row.taxable, so_far_base + row.base)
            row.year_so_far = so_far + row.taxable
            here[code] = row
        for r in inv.tds_rows.all():
            if r.amount and r.section:
                row = here.setdefault(r.section, BillRow(inv, r.section))
                row.on_bill += r.amount
                row.on_bill_sections.add(r.section)
        for (inv_id, code), amount in adjusted.items():
            if inv_id == inv.pk:
                here.setdefault(code, BillRow(inv, code)).adjusted += amount
        for code, row in here.items():
            row.filed = quarter_start(inv.posting_date) in filed
            row.section_set_by = set_by.get((inv.pk, code), "")
            if not row.why and row.due == 0 and row.on_bill:
                row.why = f"No {code} is due on this bill by today's masters."
            out[(inv.supplier_id, code)].append(row)
    return out


def result(due: Decimal, deducted: Decimal, missing: int = 0) -> tuple[str, str]:
    gap = due - deducted
    if gap > 0:
        return "short", "Short"
    if gap < 0:
        return "excess", "Excess"
    if missing:
        return "missing", "Section missing"
    if due == 0:
        return "below", "Below limit"
    return "matches", "Matches"


def _summary(supplier: Ledger, code: str, rows: list[BillRow], day: datetime.date) -> dict:
    due = sum((r.due for r in rows), ZERO)
    deducted = sum((r.deducted for r in rows), ZERO)
    fixable = sum((r.gap for r in rows if not r.filed), ZERO)
    missing = [r for r in rows if r.needs_section]
    key, label = result(due, deducted, len(missing))
    party = supplier.party
    return {
        "supplier": supplier.pk,
        "supplier_name": supplier.name,
        "pan": party.pan if party else "",
        "section": code,
        "section_shown": tds_sections.shown(code, day),
        "bills": len(rows),
        "taxable": money(sum((r.taxable for r in rows), ZERO)),
        "due": money(due),
        "deducted": money(deducted),
        "gap": money(due - deducted),
        "fixable": money(fixable),
        "no_section": len(missing),
        "to_set": sum(1 for r in missing if not r.filed),
        "result": key,
        "result_label": label,
    }


def _bill_out(r: BillRow) -> dict:
    inv = r.invoice
    had = sorted(r.on_bill_sections - {""})
    why = r.why
    if r.gap > 0 and r.missed:
        names = ", ".join(dict.fromkeys(r.missed))
        why = f"Not under {r.code} on the bill when billed: {names}. " + why
    elif r.gap < 0:
        why = "Deducted more than is due. " + why
    elif r.needs_section:
        names = ", ".join(dict.fromkeys(r.missed))
        why = f"{r.code} missing on the bill: {names}. " + why
    if r.section_set_by:
        why = (why + f" {r.code} set by {r.section_set_by}.").strip()
    if r.filed:
        why = (why + " The quarter's TDS return is filed.").strip()
    return {
        "invoice": inv.pk,
        "number": inv.number,
        "kind": inv.kind,
        "posting_date": inv.posting_date,
        "bill_no": inv.bill_no,
        "taxable": money(r.taxable),
        "year_so_far": money(r.year_so_far),
        "on_bill_section": ", ".join(had) if had else "None",
        "section": r.code,
        "base": money(r.base),
        "rate": f"{r.rate.normalize():f}" if r.rate else "0",
        "due": money(r.due),
        "on_bill": money(r.on_bill),
        "adjusted": money(r.adjusted),
        "deducted": money(r.deducted),
        "gap": money(r.gap),
        "filed": r.filed,
        "needs_section": r.needs_section,
        "section_set_by": r.section_set_by,
        "why": why.strip(),
    }


def _year(company: Company, request) -> tuple[datetime.date, datetime.date]:
    value = request.query_params.get("year", "")
    day = datetime.date.today()
    if value:
        try:
            day = datetime.date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError({"year": ["Give a date in the year, as 2026-04-01."]}) from exc
    return tds.year_range(company, day)


def _years(company: Company) -> list[dict]:
    """The financial years from the first submitted bill to this one."""
    first = (
        PurchaseInvoice.objects.filter(company=company, status=PurchaseInvoice.SUBMITTED)
        .order_by("posting_date")
        .values_list("posting_date", flat=True)
        .first()
    )
    start, _ = tds.year_range(company, datetime.date.today())
    begin = tds.year_range(company, first)[0] if first and first < start else start
    out = []
    while begin <= start:
        end = begin.replace(year=begin.year + 1) - datetime.timedelta(days=1)
        out.append({"start": begin, "end": end, "label": f"{begin.year}-{str(end.year)[2:]}"})
        begin = begin.replace(year=begin.year + 1)
    return list(reversed(out))


def _quarters(company: Company, start: datetime.date) -> list[dict]:
    filed = filed_quarters(company)
    out = []
    for n in range(4):
        month = start.month + 3 * n
        q = quarter_start(datetime.date(start.year + (month - 1) // 12, (month - 1) % 12 + 1, 1))
        got = filed.get(q)
        out.append(
            {
                "quarter_start": q,
                "label": quarter_label(q),
                "id": got.pk if got else None,
                "filed_on": got.filed_on if got else None,
                "ack_no": got.ack_no if got else "",
            }
        )
    return out


class CheckView(APIView):
    """GET ?year=<a date in the year>: one row per supplier ledger and section."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        start, end = _year(company, request)
        checked = run(company, start, end)
        ledgers = Ledger.objects.select_related("party").in_bulk({k[0] for k in checked})
        rows = [
            _summary(ledgers[sup], code, bills, start) for (sup, code), bills in checked.items()
        ]
        rows.sort(key=lambda r: (r["result"] not in ("short", "excess"), r["supplier_name"]))
        return Response(
            _text(
                {
                    "start": start,
                    "end": end,
                    "years": _years(company),
                    "quarters": _quarters(company, start),
                    "rows": rows,
                    "checked_at": timezone.now(),
                }
            )
        )


class CheckSupplierView(APIView):
    """GET ?ledger=ID&section=194Q&year=<date>: that supplier's bills one by one."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        start, end = _year(company, request)
        q = request.query_params
        supplier = Ledger.objects.select_related("party").filter(
            company=company, pk=int(q.get("ledger", "0") or 0)
        )
        supplier = supplier.first()
        code = q.get("section", "")
        if supplier is None or not code:
            raise ValidationError({"detail": "Name the supplier ledger and the section."})
        rows = run(company, start, end, supplier.pk).get((supplier.pk, code), [])
        sec = tds_sections.section_on(code, start) or tds_sections.section_on(code, end)
        party = supplier.party
        adjustments = TdsAdjustment.objects.filter(
            company=company, supplier=supplier, section=code
        ).exclude(status=TdsAdjustment.CANCELLED)
        return Response(
            _text(
                {
                    "start": start,
                    "end": end,
                    "summary": _summary(supplier, code, rows, start),
                    "section_name": sec.name if sec else "",
                    "limits": tds._limits(sec) if sec else "",
                    "above_limit_only": bool(sec and sec.above_limit_only),
                    "deductee": tds.deductee_label(party),
                    "balance": service.gl_balance(supplier),
                    "bills": [_bill_out(r) for r in rows],
                    "adjustments": [
                        {
                            "id": a.pk,
                            "number": a.number,
                            "status": a.status,
                            "status_label": a.get_status_display(),
                            "adj_date": a.adj_date,
                            "total": a.total,
                        }
                        for a in adjustments
                    ],
                }
            )
        )


# Return Filed ----------------------------------------------------------------


class ReturnSerializer(serializers.Serializer):
    quarter_start = serializers.DateField()
    filed_on = serializers.DateField()
    ack_no = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class ReturnListView(APIView):
    """POST {quarter_start, filed_on, ack_no}: mark a quarter's TDS return filed."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, SUBMIT)
        company = _company(request, pk)
        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        q = data["quarter_start"]
        if q != quarter_start(q):
            raise ValidationError({"quarter_start": ["Give the first day of the quarter."]})
        if data["filed_on"] > datetime.date.today():
            raise ValidationError({"filed_on": ["The return cannot be filed in the future."]})
        if TdsReturnFiled.objects.filter(company=company, quarter_start=q).exists():
            raise ValidationError({"detail": f"{quarter_label(q)} is already marked filed."})
        row = TdsReturnFiled.objects.create(
            company=company,
            quarter_start=q,
            filed_on=data["filed_on"],
            ack_no=data["ack_no"].strip(),
            created_by=request.user,
        )
        return Response(_text({"id": row.pk}), status=status.HTTP_201_CREATED)


class ReturnDetailView(APIView):
    """DELETE: take the mark off a quarter marked filed by mistake (Owners only)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def delete(self, request, pk: int):
        if not request.user.is_owner:
            raise PermissionDenied("Only an Owner can take the mark off.")
        row = TdsReturnFiled.objects.filter(
            pk=pk, company__in=visible_companies(request.user)
        ).first()
        if row is None:
            raise NotFound("No such mark.")
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# TDS Adjustment --------------------------------------------------------------


def _gaps(company: Company, supplier: Ledger, code: str, invoices) -> dict[int, BillRow]:
    """The check's row for each bill, in its own financial year."""
    out: dict[int, BillRow] = {}
    years = {tds.year_range(company, inv.posting_date) for inv in invoices}
    for start, end in years:
        for row in run(company, start, end, supplier.pk).get((supplier.pk, code), []):
            out[row.invoice.pk] = row
    return out


def _lines_for(adj: TdsAdjustment, invoice_ids: list[int]) -> list[TdsAdjustmentLine]:
    invoices = list(
        PurchaseInvoice.objects.filter(
            pk__in=invoice_ids, company=adj.company, supplier=adj.supplier
        ).order_by("posting_date", "id")
    )
    if len(invoices) != len(set(invoice_ids)):
        raise ValidationError({"lines": ["A bill is not this supplier's, or not found."]})
    gaps = _gaps(adj.company, adj.supplier, adj.section, invoices)
    sec = tds_sections.section_on(adj.section, adj.adj_date)
    late = sec.late_interest if sec else ZERO
    lines = []
    for n, inv in enumerate(invoices, start=1):
        row = gaps.get(inv.pk)
        if row is None or (row.gap == 0 and not row.needs_section):
            raise ValidationError(
                {"lines": [f"Bill {inv.number} has no {adj.section} to put right."]}
            )
        if row.filed:
            refuse_if_filed(adj.company, inv.posting_date, f"bill {inv.number}", "lines")
        if adj.adj_date < inv.posting_date:
            raise ValidationError(
                {"adj_date": [f"Bill {inv.number} is dated {_dmy(inv.posting_date)}."]}
            )
        months = months_late(inv.posting_date, adj.adj_date) if row.gap > 0 else 0
        lines.append(
            TdsAdjustmentLine(
                adjustment=adj,
                position=n,
                invoice=inv,
                base=row.base,
                rate=row.rate,
                due=row.due,
                deducted=row.deducted,
                amount=row.gap,
                months=months,
                interest=money(row.gap * late * months / 100) if months else ZERO,
            )
        )
    return lines


class AdjustmentSerializer(serializers.Serializer):
    supplier = serializers.IntegerField()
    section = serializers.CharField(max_length=12)
    adj_date = serializers.DateField()
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
    invoices = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    submit = serializers.BooleanField(required=False, default=False)


def _save(adj: TdsAdjustment, data: dict) -> None:
    supplier = Ledger.objects.filter(pk=data["supplier"], company=adj.company).first()
    if supplier is None:
        raise ValidationError({"supplier": ["Pick a supplier ledger of this company."]})
    adj.supplier = supplier
    adj.section = tds_sections.check_section(data["section"], "section")
    if not adj.section:
        raise ValidationError({"section": ["Pick the TDS section."]})
    adj.adj_date = data["adj_date"]
    adj.remarks = data.get("remarks", "").strip()
    refuse_if_filed(adj.company, adj.adj_date, "an adjustment dated in it", "adj_date")
    lines = _lines_for(adj, data["invoices"])
    adj.branch = lines[-1].invoice.branch
    adj.total = sum((ln.amount for ln in lines), ZERO)
    adj.interest = sum((ln.interest for ln in lines), ZERO)
    adj.save()
    adj.lines.all().delete()
    TdsAdjustmentLine.objects.bulk_create(lines)


def kind_label(total: Decimal) -> str:
    if total > 0:
        return "Deduct short TDS"
    if total < 0:
        return "Give back excess TDS"
    return "Set section only"


def _plan(adj: TdsAdjustment, preview: bool = False) -> list[GLLine]:
    """Nothing when the adjustment only sets the section (₹0)."""
    if adj.total == 0:
        return []
    payable = tds.tds_ledger(adj.company, adj.section, preview)
    bills = ", ".join(ln.invoice.number for ln in adj.lines.select_related("invoice"))
    amount = abs(adj.total)
    if adj.total > 0:
        return [
            GLLine(adj.supplier, debit=amount, remarks=f"TDS {adj.section} missed on {bills}"),
            GLLine(payable, credit=amount, remarks=f"Deducted late on {bills}"),
        ]
    return [
        GLLine(payable, debit=amount, remarks=f"Excess TDS given back on {bills}"),
        GLLine(adj.supplier, credit=amount, remarks=f"TDS {adj.section} given back on {bills}"),
    ]


def _submit(adj: TdsAdjustment, user) -> None:
    if not user.can(SUBMIT):
        raise PermissionDenied("Your role may save drafts but not submit them.")
    attachments.require_file(adj, KIND)
    # The gaps again, as they stand now: another adjustment may have put them right.
    lines = _lines_for(adj, list(adj.lines.values_list("invoice_id", flat=True)))
    adj.total = sum((ln.amount for ln in lines), ZERO)
    adj.interest = sum((ln.interest for ln in lines), ZERO)
    adj.lines.all().delete()
    TdsAdjustmentLine.objects.bulk_create(lines)
    adj.number = numbering.next_document_number(adj.company, KIND, adj.adj_date, adj.branch)
    adj.save()
    voucher = Voucher(adj.company, adj.branch, adj.adj_date, KIND, adj.pk, adj.number, user)
    if plan := _plan(adj):
        service.post(voucher, gl=plan)
    adj.status = TdsAdjustment.SUBMITTED
    adj.submitted_at = timezone.now()
    adj.submitted_by = user
    adj.save()


def _cancel(adj: TdsAdjustment, user, reason: str) -> None:
    if adj.status == TdsAdjustment.SUBMITTED:
        refuse_if_filed(adj.company, adj.adj_date, "this adjustment")
        for ln in adj.lines.select_related("invoice"):
            day, number = ln.invoice.posting_date, ln.invoice.number
            refuse_if_filed(adj.company, day, f"the TDS of bill {number}")
        if adj.total:
            service.cancel(KIND, adj.pk, user)
    adj.status = TdsAdjustment.CANCELLED
    adj.cancel_reason = reason[:200]
    adj.save()


def covering(inv: PurchaseInvoice) -> str:
    """Submitted TDS Adjustments naming the bill: it cannot be cancelled before them."""
    rows = TdsAdjustment.objects.filter(
        lines__invoice=inv, status=TdsAdjustment.SUBMITTED
    ).values_list("number", flat=True)
    return ", ".join(sorted(set(rows)))


def _adjustments(company: Company):
    return TdsAdjustment.objects.filter(company=company).select_related(
        "supplier", "branch", "created_by", "submitted_by", "company"
    )


def _out(adj: TdsAdjustment, lines: bool = True) -> dict:
    sec = tds_sections.section_on(adj.section, adj.adj_date)
    data = {
        "id": adj.pk,
        "company": adj.company_id,
        "number": adj.number,
        "status": adj.status,
        "status_label": adj.get_status_display(),
        "supplier": adj.supplier_id,
        "supplier_name": adj.supplier.name,
        "branch_name": adj.branch.name,
        "adj_date": adj.adj_date,
        "section": adj.section,
        "section_shown": tds_sections.shown(adj.section, adj.adj_date),
        "kind_label": kind_label(adj.total),
        "remarks": adj.remarks,
        "total": adj.total,
        "interest": adj.interest,
        "late_interest": f"{sec.late_interest.normalize():f}" if sec else "",
        "cancel_reason": adj.cancel_reason,
        "created_by_name": adj.created_by.display_name if adj.created_by else "",
        "created_at": adj.created_at,
        "submitted_at": adj.submitted_at,
        "submitted_by_name": adj.submitted_by.display_name if adj.submitted_by else "",
    }
    if lines:
        data["lines"] = [_line_out(ln) for ln in adj.lines.select_related("invoice")]
    return _text(data)


def _line_out(ln: TdsAdjustmentLine) -> dict:
    return {
        "invoice": ln.invoice_id,
        "number": ln.invoice.number,
        "posting_date": ln.invoice.posting_date,
        "bill_no": ln.invoice.bill_no,
        "base": ln.base,
        "rate": f"{ln.rate.normalize():f}" if ln.rate else "0",
        "due": ln.due,
        "deducted": ln.deducted,
        "amount": ln.amount,
        "months": ln.months,
        "interest": ln.interest,
    }


def _fresh(adj: TdsAdjustment) -> dict:
    return _out(_adjustments(adj.company).get(pk=adj.pk))


def _adjustment(request, pk: int, lock: bool = False) -> TdsAdjustment:
    rows = TdsAdjustment.objects.filter(pk=pk, company__in=visible_companies(request.user))
    if lock:
        rows = rows.select_for_update(of=("self",))
    adj = rows.select_related("company", "supplier").first()
    if adj is None or "purchase" not in adj.company.modules:
        raise NotFound("No such TDS adjustment.")
    return adj


def _apply(request, adj: TdsAdjustment):
    serializer = AdjustmentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    _save(adj, data)
    if data.get("submit"):
        _check(request, SUBMIT)
        if refused := attachments.refuse_submit(adj, KIND):
            return refused
        _submit(adj, request.user)
    return None


class AdjustmentListView(APIView):
    """GET ?view=submitted|draft|cancelled|all. POST makes a draft (with
    "submit": true, submits it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        rows = _adjustments(company)
        view = request.query_params.get("view", "submitted")
        if view in (TdsAdjustment.DRAFT, TdsAdjustment.SUBMITTED, TdsAdjustment.CANCELLED):
            rows = rows.filter(status=view)
        for word in request.query_params.get("q", "").split():
            rows = rows.filter(
                Q(number__icontains=word)
                | Q(supplier__name__icontains=word)
                | Q(section__icontains=word)
            )
        return Response([_out(a, lines=False) for a in rows[:1000]])

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CREATE)
        company = _company(request, pk)
        adj = TdsAdjustment(company=company, created_by=request.user)
        if refused := _apply(request, adj):
            return refused
        return Response(_fresh(adj), status=status.HTTP_201_CREATED)


class AdjustmentDetailView(APIView):
    """GET one adjustment; PATCH a draft (with "submit": true, also submit it)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        return Response(_fresh(_adjustment(request, pk)))

    @tenant_atomic()
    def patch(self, request, pk: int):
        _check(request, CREATE)
        adj = _adjustment(request, pk, lock=True)
        if adj.status != TdsAdjustment.DRAFT:
            raise ValidationError(
                {"detail": "A submitted TDS adjustment cannot be changed. Cancel it instead."}
            )
        if refused := _apply(request, adj):
            return refused
        return Response(_fresh(adj))


class AdjustmentCancelView(APIView):
    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, CANCEL)
        adj = _adjustment(request, pk, lock=True)
        if adj.status == TdsAdjustment.CANCELLED:
            raise ValidationError({"detail": "This TDS adjustment is already cancelled."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": ["Say why it is cancelled."]})
        _cancel(adj, request.user, reason)
        return Response(_fresh(adj))


class AdjustmentPostingView(APIView):
    """GET: the "Ledger Posting" section."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        adj = _adjustment(request, pk)
        if adj.status != TdsAdjustment.DRAFT:
            out = posting_api.posted(KIND, adj.pk)
            if adj.total == 0:
                out["note"] = "Nothing posted: this adjustment only sets the TDS section."
            return Response(out)
        if not adj.lines.exists():
            return Response(posting_api.preview([]))
        if adj.total == 0:
            note = "Nothing to post: this adjustment only sets the TDS section."
            return Response(posting_api.preview([], note))
        rows = []
        for g in _plan(adj, preview=True):
            row = posting_api.ledger_row(g.ledger, g.debit, g.credit)
            if g.ledger.pk is None:
                row["ledger_name"] = f"{g.ledger.name} (made on Submit)"
            rows.append(row)
        return Response(posting_api.preview(rows))


class AdjustmentDraftFromView(APIView):
    """GET ?ledger=ID&section=194Q&year=<date>: a new adjustment's bills, from
    the TDS Check: every bill of the year with a gap, in a quarter not filed."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        start, end = _year(company, request)
        q = request.query_params
        supplier = Ledger.objects.filter(company=company, pk=int(q.get("ledger", "0") or 0))
        supplier = supplier.first()
        code = q.get("section", "")
        if supplier is None or not code:
            raise ValidationError({"detail": "Name the supplier ledger and the section."})
        rows = run(company, start, end, supplier.pk).get((supplier.pk, code), [])
        invoices = [r.invoice.pk for r in rows if (r.gap or r.needs_section) and not r.filed]
        if not invoices:
            raise ValidationError(
                {"detail": f"{supplier.name} has no {code} to put right in an open quarter."}
            )
        return Response(
            {
                "supplier": supplier.pk,
                "supplier_name": supplier.name,
                "section": code,
                "invoices": invoices,
            }
        )


class AdjustmentPreviewView(APIView):
    """POST {supplier, section, adj_date, invoices}: the lines as Save would make
    them, without saving (the form shows them before the first Save)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        supplier = Ledger.objects.filter(pk=data["supplier"], company=company).first()
        if supplier is None:
            raise ValidationError({"supplier": ["Pick a supplier ledger of this company."]})
        adj = TdsAdjustment(
            company=company, supplier=supplier, section=data["section"], adj_date=data["adj_date"]
        )
        lines = _lines_for(adj, data["invoices"])
        sec = tds_sections.section_on(adj.section, adj.adj_date)
        return Response(
            _text(
                {
                    "late_interest": f"{sec.late_interest.normalize():f}" if sec else "",
                    "lines": [_line_out(ln) for ln in lines],
                    "total": sum((ln.amount for ln in lines), ZERO),
                    "kind_label": kind_label(sum((ln.amount for ln in lines), ZERO)),
                    "interest": sum((ln.interest for ln in lines), ZERO),
                }
            )
        )


def tds_in_quarter(inv: PurchaseInvoice) -> None:
    """A bill that deducted TDS in a quarter whose return is filed is not cancelled."""
    if inv.tds_total and inv.posting_date:
        refuse_if_filed(inv.company, inv.posting_date, f"the TDS of bill {inv.number}")
