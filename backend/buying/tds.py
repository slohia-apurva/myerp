"""TDS on purchase bills (Sidharth, 2026-11-16, previews 86a/86b).

Every purchase bill (against goods receipts, without goods receipt, and
supplementary bills) works out TDS line by line:

* The line's section comes from its item or ledger ("TDS Section"); else, for
  goods, 194Q when the company ticks "Deduct TDS on purchase of goods"; else,
  for a service or a ledger, the supplier's "Default TDS Section". The person
  may change or clear it on the bill (`by_hand`).
* The section's rates and limits are the central dated list's row in force on
  the bill's date (tenancy.TdsSection). TDS is on the amount before GST.
* Limits: a bill whose lines in the section pass the one-bill limit, or a year
  (this supplier, this company, the financial year) that passes the year limit,
  deducts. When the year first passes the limit, the earlier bills that did not
  deduct are caught up on this bill. 194Q deducts only on the part above its limit.
* Rate: the deductee type (the supplier's, else read from its PAN) picks the
  individual/HUF or the other rate; no PAN means the higher no-PAN rate.
  TDS is rounded to the rupee.
* Submit credits "TDS Payable <section>" (one ledger per section, under Duties
  and Taxes, made the first time) and credits the supplier with the bill total
  less TDS; due dates split that net amount. A debit note takes TDS back in
  proportion to the lines it debits.

A supplier abroad has no TDS here (those payments go under section 195, later).
"""

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import CREATE, VIEW, _check
from buying.models import DebitNote, PurchaseInvoice, PurchaseInvoiceTds
from core import tds_sections
from core.api import Signed
from core.models import Company, Item, Ledger, LedgerGroup, Party, fiscal_year_start
from core.tds_sections import check_section, section_on
from posting.service import GLLine
from tenancy.context import tenant_atomic
from tenancy.models import TdsSection

ZERO = Decimal("0")


def rupees(value: Decimal) -> Decimal:
    """TDS is rounded to the nearest rupee."""
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _plain(value: Decimal) -> str:
    """₹ in Indian style without paise when whole: 1,00,000."""
    value = Decimal(value)
    whole = int(value)
    digits = str(abs(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    paise = value - whole
    text = ("-" if whole < 0 else "") + digits
    return text + (f"{abs(paise):.2f}"[1:] if paise else "")


def goods_section(day: datetime.date) -> TdsSection | None:
    return (
        TdsSection.objects.filter(for_goods=True, valid_from__lte=day, is_active=True)
        .order_by("-valid_from")
        .first()
    )


# The supplier -----------------------------------------------------------------

PAN_TYPES = {"C": Party.COMPANY, "F": Party.FIRM, "P": Party.INDIVIDUAL, "H": Party.INDIVIDUAL}


def deductee_type(party: Party | None) -> str:
    if party is None:
        return Party.OTHERS
    if party.deductee_type:
        return party.deductee_type
    if len(party.pan or "") == 10:
        return PAN_TYPES.get(party.pan[3].upper(), Party.OTHERS)
    return Party.OTHERS


def deductee_label(party: Party | None) -> str:
    kind = dict(Party.DEDUCTEE_TYPES)[deductee_type(party)]
    if party is None or not party.pan:
        return f"{kind} (no PAN: higher rate)"
    if party.deductee_type:
        return f"{kind} (PAN {party.pan})"
    return f"{kind} (from PAN {party.pan})"


def rate_for(section: TdsSection, party: Party | None) -> Decimal:
    if deductee_type(party) == Party.INDIVIDUAL:
        rate = section.rate_individual
    else:
        rate = section.rate_other
    if party is None or not party.pan:
        rate = max(rate, section.rate_no_pan)
    return rate


# One bill ---------------------------------------------------------------------


@dataclass
class Line:
    kind: str
    position: int
    label: str
    taxable: Decimal
    default: str  # the section the line's item or ledger (or the supplier) gives
    why: str


def bill_day(inv) -> datetime.date:
    return inv.posting_date or inv.bill_date or datetime.date.today()


def _default(inv: PurchaseInvoice, item: Item | None, ledger: Ledger | None, day) -> tuple:
    if item is not None and item.tds_section:
        return item.tds_section, "From the item."
    if ledger is not None and ledger.tds_section:
        return ledger.tds_section, "From the ledger."
    if item is not None and item.item_type == Item.GOODS:
        goods = goods_section(day)
        if goods is not None and inv.company.deduct_194q:
            return goods.code, "Goods: the company deducts TDS on purchase of goods."
        return "", "Goods: no TDS (the company does not deduct on purchase of goods)."
    party = inv.supplier.party
    if party is not None and party.tds_section:
        return party.tds_section, "The supplier's default section."
    return "", ""


def _lines(inv: PurchaseInvoice) -> list[Line]:
    day = bill_day(inv)
    out = []
    if inv.kind == PurchaseInvoice.DIRECT:
        for ln in inv.expense_lines.select_related("item", "ledger"):
            code, why = _default(inv, ln.item, ln.ledger, day)
            label = ln.item.name if ln.item_id else ln.ledger.name
            out.append(Line("expense", ln.position, label, ln.taxable, code, why))
    elif inv.kind == PurchaseInvoice.SUPPLEMENTARY:
        for ln in inv.rate_lines.select_related("item"):
            code, why = _default(inv, ln.item, None, day)
            out.append(Line("rate", ln.position, ln.item.name, ln.taxable, code, why))
    else:
        for ln in inv.lines.select_related("item"):
            code, why = _default(inv, ln.item, None, day)
            out.append(Line("line", ln.position, ln.item.name, ln.taxable, code, why))
        for c in inv.charges.select_related("item"):
            code, why = _default(inv, c.item, None, day)
            out.append(Line("charge", c.position, c.item.name, c.amount, code, why))
    return out


def year_range(company: Company, day: datetime.date) -> tuple[datetime.date, datetime.date]:
    start = fiscal_year_start(day, company.fiscal_year_start_month)
    end = start.replace(year=start.year + 1) - datetime.timedelta(days=1)
    return start, end


def year_so_far(inv: PurchaseInvoice, code: str) -> tuple[Decimal, Decimal]:
    """This supplier's submitted bills in the section this financial year,
    before this bill: (amount before GST, the part TDS was deducted on).

    The amount goes by each earlier line's section by today's masters, as the
    TDS Check does (Sidharth, 2026-11-20): a bill entered before its item got
    194Q still counts towards the year's ₹50 lakh. The part deducted on is what
    the bills deducted on, plus what TDS Adjustments deducted for them."""
    from buying.models import TdsAdjustment, TdsAdjustmentLine

    start, end = year_range(inv.company, bill_day(inv))
    earlier = (
        PurchaseInvoice.objects.filter(
            company=inv.company,
            supplier=inv.supplier,
            status=PurchaseInvoice.SUBMITTED,
            posting_date__range=(start, end),
        )
        .exclude(pk=inv.pk)
        .select_related("company", "supplier__party")
    )
    amount = ZERO
    for bill in earlier:
        amount += sum((ln.taxable for ln, sec, _ in lines_now(bill) if sec == code), ZERO)
    base = (
        PurchaseInvoiceTds.objects.filter(invoice__in=earlier, section=code).aggregate(
            b=Sum("base")
        )["b"]
        or ZERO
    )
    base += (
        TdsAdjustmentLine.objects.filter(
            invoice__in=earlier,
            adjustment__section=code,
            adjustment__status=TdsAdjustment.SUBMITTED,
            amount__gt=0,
        ).aggregate(b=Sum("base"))["b"]
        or ZERO
    )
    return amount, base


def _limits(sec: TdsSection) -> str:
    parts = []
    if sec.bill_limit:
        parts.append(f"one bill ₹{_plain(sec.bill_limit)}")
    if sec.year_limit:
        parts.append(f"year ₹{_plain(sec.year_limit)}")
    return " and ".join(parts)


def work_out(
    sec: TdsSection, taxables: list[Decimal], so_far: Decimal, so_far_base: Decimal
) -> tuple[list[Decimal], list[tuple[str, bool]]]:
    """What TDS is worked out on, for one bill's lines in one section, given the
    supplier's year so far in the section (the amount, and the part TDS was
    deducted on). Also each line's note: (text, whether it adds to the line's
    own note); no text keeps the line's own. Used by every bill and by the
    TDS Check, which runs the year again (buying/tds_check.py)."""
    bases = [ZERO] * len(taxables)
    notes: list[tuple[str, bool]] = [("", False)] * len(taxables)
    if sec.above_limit_only:
        limit = sec.year_limit or ZERO
        running = so_far
        for n, taxable in enumerate(taxables):
            bases[n] = max(ZERO, running + taxable - limit) - max(ZERO, running - limit)
            running += taxable
            notes[n] = (
                (f"Year so far ₹{_plain(so_far)}: TDS on what passes ₹{_plain(limit)}.", False)
                if bases[n]
                else (f"Year so far ₹{_plain(so_far)}: below ₹{_plain(limit)}.", False)
            )
        return bases, notes
    bill = sum(taxables, ZERO)
    over_bill = bool(sec.bill_limit) and bill > sec.bill_limit
    over_year = bool(sec.year_limit) and so_far + bill > sec.year_limit
    no_limits = not sec.bill_limit and not sec.year_limit
    if not (over_bill or over_year or no_limits):
        return bases, [(f"Below the limits ({_limits(sec)}).", False)] * len(taxables)
    bases = list(taxables)
    catch_up = so_far - so_far_base if over_year else ZERO
    if catch_up > 0 and bases:
        bases[0] += catch_up
        notes[0] = (
            f"The year passes ₹{_plain(sec.year_limit)}: includes "
            f"₹{_plain(catch_up)} of earlier bills.",
            False,
        )
    elif over_year:
        code = sec.code
        text = f"The supplier's {code} this year passes ₹{_plain(sec.year_limit)}."
        notes = [(text, True)] * len(taxables)
    return bases, notes


def lines_now(inv: PurchaseInvoice) -> list[tuple[Line, str, str]]:
    """The bill's lines with the section each takes by today's masters (or the
    one chosen on the bill), and why: for the TDS Check."""
    chosen = {(r.line_kind, r.line_position): r.section for r in inv.tds_rows.filter(by_hand=True)}
    out = []
    for ln in _lines(inv):
        key = (ln.kind, ln.position)
        if key in chosen:
            out.append((ln, chosen[key], "Chosen on the bill."))
        else:
            out.append((ln, ln.default, ln.why))
    return out


def refresh(inv: PurchaseInvoice) -> None:
    """Work the bill's TDS out again from its lines, keeping what the person
    chose by hand, and set inv.tds_total. Only for drafts and on Submit."""
    if inv.status != PurchaseInvoice.DRAFT:
        return
    chosen = {(r.line_kind, r.line_position): r.section for r in inv.tds_rows.filter(by_hand=True)}
    lines = _lines(inv)
    party = inv.supplier.party
    abroad = party is not None and party.gst_type == Party.OVERSEAS
    day = bill_day(inv)
    rows: list[PurchaseInvoiceTds] = []
    for n, ln in enumerate(lines, start=1):
        key = (ln.kind, ln.position)
        by_hand = key in chosen
        rows.append(
            PurchaseInvoiceTds(
                invoice=inv,
                position=n,
                line_kind=ln.kind,
                line_position=ln.position,
                label=ln.label[:200],
                section=chosen[key] if by_hand else ln.default,
                by_hand=by_hand,
                taxable=ln.taxable,
                note=("Chosen on the bill." if by_hand else ln.why) if not abroad else "",
            )
        )
    if abroad:
        for r in rows:
            r.section = ""
            r.note = "Supplier abroad: no TDS under these sections."
    by_section: dict[str, list[PurchaseInvoiceTds]] = {}
    for r in rows:
        if r.section:
            by_section.setdefault(r.section, []).append(r)
    for code, group in by_section.items():
        sec = section_on(code, day)
        if sec is None:
            for r in group:
                r.note = f"{code} is not in the TDS sections list on {day:%d-%m-%Y}."
            continue
        rate = rate_for(sec, party)
        so_far, so_far_base = year_so_far(inv, code)
        bases, notes = work_out(sec, [r.taxable for r in group], so_far, so_far_base)
        for r, b, (text, append) in zip(group, bases, notes, strict=True):
            r.base = b
            if text:
                r.note = (r.note + " " + text).strip() if append else text
        for r in group:
            r.rate = rate if r.base else ZERO
            r.amount = rupees(r.base * rate / 100) if r.base else ZERO
    inv.tds_rows.all().delete()
    PurchaseInvoiceTds.objects.bulk_create(rows)
    inv.tds_total = sum((r.amount for r in rows), ZERO)
    PurchaseInvoice.objects.filter(pk=inv.pk).update(tds_total=inv.tds_total)


def tds_ledger(company: Company, code: str, preview: bool = False) -> Ledger:
    """'TDS Payable 194C': one per section, under Duties and Taxes, made the
    first time a bill deducts under it."""
    system_code = f"tds_{code.lower()}"
    ledger = Ledger.objects.filter(company=company, system_code=system_code).first()
    if ledger is not None:
        return ledger
    name = f"TDS Payable {code}"
    ledger = Ledger.objects.filter(company=company, name__iexact=name).first()
    if ledger is None:
        group = LedgerGroup.objects.get(company=company, code="duties_taxes")
        ledger = Ledger(company=company, group=group, name=name)
    if preview:
        return ledger
    ledger.system_code = system_code
    ledger.is_active = True
    ledger.save()
    return ledger


def _by_section(rows) -> dict[str, list]:
    out: dict[str, list] = {}
    for r in rows:
        if r.amount:
            out.setdefault(r.section, []).append(r)
    return out


def bill_lines(inv: PurchaseInvoice, preview: bool = False) -> list[GLLine]:
    """Cr TDS Payable, one line per section."""
    out = []
    for code, rows in _by_section(inv.tds_rows.all()).items():
        amount = sum((r.amount for r in rows), ZERO)
        base = sum((r.base for r in rows), ZERO)
        rate = rows[0].rate.normalize()
        out.append(
            GLLine(
                tds_ledger(inv.company, code, preview),
                credit=amount,
                remarks=f"{rate:f}% on ₹{_plain(base)}",
            )
        )
    return out


def supplier_line(inv: PurchaseInvoice, remarks: str) -> GLLine:
    if inv.tds_total:
        remarks = f"{remarks}, less TDS ₹{_plain(inv.tds_total)}".strip(", ")
    return GLLine(inv.supplier, credit=inv.total - inv.tds_total, remarks=remarks)


# Debit notes ------------------------------------------------------------------


def note_back(note: DebitNote) -> dict[str, Decimal]:
    """TDS a debit note takes back, by section: each line's share of the TDS
    its bill line bore, in proportion to the amount debited."""
    inv = note.invoice
    if inv is None or not inv.tds_total:
        return {}
    rows = {(r.line_kind, r.line_position): r for r in inv.tds_rows.all() if r.amount}
    back: dict[str, Decimal] = {}
    for ln in note.lines.select_related("invoice_line"):
        if ln.invoice_line_id is None:
            continue
        r = rows.get(("line", ln.invoice_line.position))
        if r is None or not r.taxable:
            continue
        share = min(r.base, r.taxable) / r.taxable
        back[r.section] = back.get(r.section, ZERO) + ln.taxable * share * r.rate / 100
    return {code: rupees(v) for code, v in back.items() if rupees(v)}


def note_lines(note: DebitNote, preview: bool = False) -> tuple[list[GLLine], Decimal]:
    """Dr TDS Payable for what the note takes back, and the total."""
    back = note_back(note)
    lines = [
        GLLine(tds_ledger(note.company, code, preview), debit=amount, remarks="TDS taken back")
        for code, amount in back.items()
    ]
    return lines, sum(back.values(), ZERO)


# The bill's TDS box -------------------------------------------------------------


def row_out(r: PurchaseInvoiceTds, day: datetime.date, individual: bool) -> dict:
    sec = section_on(r.section, day)
    return {
        "line_kind": r.line_kind,
        "line_position": r.line_position,
        "label": r.label,
        "section": r.section,
        # As the bill's date shows it: the new Act's number first from 1 April 2026.
        "section_shown": tds_sections.shown(r.section, day),
        "payment_code": tds_sections.payment_code(sec, individual) if sec else "",
        "by_hand": r.by_hand,
        "taxable": r.taxable,
        "base": r.base,
        "rate": f"{r.rate.normalize():f}" if r.rate else "0",
        "amount": r.amount,
        "note": r.note,
    }


def adjusted_on(inv: PurchaseInvoice) -> list[dict]:
    """Submitted TDS Adjustments naming the bill (buying/tds_check.py), so the bill,
    and later a supplier's payment advice, show all the TDS deducted against it."""
    from buying.models import TdsAdjustment, TdsAdjustmentLine

    rows = TdsAdjustmentLine.objects.filter(
        invoice=inv, adjustment__status=TdsAdjustment.SUBMITTED
    ).select_related("adjustment")
    return [
        {
            "id": ln.adjustment_id,
            "number": ln.adjustment.number,
            "date": ln.adjustment.adj_date,
            "section": ln.adjustment.section,
            "amount": ln.amount,
        }
        for ln in rows.order_by("adjustment__adj_date", "adjustment_id")
    ]


def deducted_on(inv: PurchaseInvoice) -> Decimal:
    """All TDS deducted against the bill: on it, and by TDS Adjustments."""
    return inv.tds_total + sum((a["amount"] for a in adjusted_on(inv)), ZERO)


def box(inv: PurchaseInvoice) -> dict:
    party = inv.supplier.party
    codes = sorted({r.section for r in inv.tds_rows.all() if r.section})
    day = bill_day(inv)
    so_far = []
    for code in codes:
        taxable, _ = year_so_far(inv, code)
        so_far.append({"section": tds_sections.shown(code, day), "amount": taxable})
    individual = deductee_type(party) == Party.INDIVIDUAL
    adjusted = adjusted_on(inv)
    return {
        "deductee": deductee_label(party),
        "year_so_far": so_far,
        "rows": [row_out(r, day, individual) for r in inv.tds_rows.all()],
        "total": inv.tds_total,
        "adjusted": adjusted,
        "with_adjusted": inv.tds_total + sum((a["amount"] for a in adjusted), ZERO),
    }


class ChoiceSerializer(serializers.Serializer):
    line_kind = serializers.ChoiceField(choices=[k for k, _ in PurchaseInvoiceTds.KINDS])
    line_position = serializers.IntegerField(min_value=0)
    section = serializers.CharField(allow_blank=True, max_length=12)


class ChoicesSerializer(serializers.Serializer):
    rows = ChoiceSerializer(many=True)


def choose(inv: PurchaseInvoice, rows: list[dict]) -> None:
    """The person's own sections for lines of a draft bill; the line's own
    section again when they pick it back."""
    if inv.status != PurchaseInvoice.DRAFT:
        raise ValidationError({"detail": "TDS changes only on a draft bill."})
    current = {(r.line_kind, r.line_position): r for r in inv.tds_rows.all()}
    defaults = {(ln.kind, ln.position): ln.default for ln in _lines(inv)}
    for row in rows:
        key = (row["line_kind"], row["line_position"])
        if key not in current:
            raise ValidationError({"rows": ["That line is not on the bill; save the bill first."]})
        code = check_section(row["section"], "rows")
        r = current[key]
        r.section = code
        r.by_hand = code != defaults.get(key, "")
        r.save(update_fields=["section", "by_hand"])
    refresh(inv)


class InvoiceTdsView(APIView):
    """GET the bill's TDS box; PUT {rows: [{line_kind, line_position, section}]}
    to change the sections of a draft bill's lines ("" for no TDS)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from buying.invoices import _invoice, _text

        _check(request, VIEW)
        return Response(_text(box(_invoice(request, pk))))

    @tenant_atomic()
    def put(self, request, pk: int):
        from buying.invoices import _fresh, _invoice

        _check(request, CREATE)
        inv = _invoice(request, pk, lock=True)
        serializer = ChoicesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        choose(inv, serializer.validated_data["rows"])
        return Response(_fresh(inv))
