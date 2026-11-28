"""Reports › Purchase › Accounts Payable (Sidharth, 2026-11-28, previews
mockups/accounts-payable/1 to 4): what the company owes each supplier on a day,
bill by bill, aged by days past the due date.

An open bill is a submitted purchase invoice (regular, supplementary or without
goods receipt) or a supplier's opening bill from the old books. What is still
owed on it is its total, less:
* TDS: what the bill deducted, less what its debit notes took back, plus or
  minus TDS Adjustments made on it later (the supplier is owed the rest);
* debit notes against it (returns and rate differences);
* payments, once the Payment entry is built (the "Paid" column is 0 till then).
That is exactly what the bill credited to the supplier's ledger, less what the
notes and adjustments debited. Due dates are the bill's own (its credit term's
parts, counted from the bill date). Debit notes and TDS Adjustments come off the
latest due date first, as on the debit note screen.

Two views: one row per supplier (Not Due / 1-30 / 31-60 / 61-90 / Over 90) and
one row per bill. Both are worked out here in Python from a few queries, then
searched, sorted and paged like the other long lists: 25 a page, a search per
column, ?sort=key / -key, ?all=1 for Print, PDF and Excel.

?age_by=bill ages by days since the bill date instead (0-30 … Over 180).
?ledger=<id> keeps one supplier (not "supplier", which is that column's search).
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import VIEW, _check, _company
from buying.models import (
    DebitNote,
    PurchaseInvoice,
    PurchaseInvoiceTds,
    TdsAdjustmentLine,
)
from core import paging
from core.api import Signed
from core.models import CR, Ledger, LedgerOpeningBill, SalesPerson

ZERO = Decimal("0")
PAISE = Decimal("0.01")
ALL_LIMIT = 20000

DUE_LABELS = ["Not Due", "1-30", "31-60", "61-90", "Over 90"]
BILL_LABELS = ["0-30", "31-60", "61-90", "91-180", "Over 180"]


def money(v: Decimal) -> str:
    return str((v or ZERO).quantize(PAISE, rounding=ROUND_HALF_UP))


def dmy(d: datetime.date | None) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def _plain(v: Decimal) -> str:
    """A rate as people write it: 0.1, 2, 1.5."""
    text = f"{v.normalize():f}"
    return text


def due_bucket(late: int) -> int:
    if late <= 0:
        return 0
    return 1 if late <= 30 else 2 if late <= 60 else 3 if late <= 90 else 4


def bill_bucket(age: int) -> int:
    return 0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3 if age <= 180 else 4


@dataclass
class Bill:
    key: str
    supplier: Ledger
    invoice_id: int | None
    bill_no: str
    our_no: str
    bill_date: datetime.date
    amount: Decimal
    tds: Decimal = ZERO
    tds_notes: list[str] = field(default_factory=list)
    dn: Decimal = ZERO
    dn_notes: list[str] = field(default_factory=list)
    paid: Decimal = ZERO
    paid_notes: list[str] = field(default_factory=list)
    # (due date, amount) parts, net of TDS, before notes and payments.
    parts: list[list] = field(default_factory=list)
    branch_id: int | None = None
    # Worked out by `settle`.
    balance: Decimal = ZERO
    due_date: datetime.date | None = None
    late: int = 0
    buckets: list[Decimal] = field(default_factory=lambda: [ZERO] * 5)
    age: int = 0

    def settle(self, as_on: datetime.date, by_bill: bool) -> None:
        self.balance = self.amount - self.tds - self.dn - self.paid
        # Notes and adjustments come off the latest due first; payments (later)
        # the earliest first.
        less = self.balance
        parts = [[d, a] for d, a in self.parts] or [[self.bill_date, self.amount - self.tds]]
        total = sum((a for _, a in parts), ZERO)
        if self.balance >= 0:
            off = total - self.balance  # what has come off the parts
            for p in reversed(parts):
                take = min(p[1], off) if p[1] > 0 else ZERO
                p[1] -= take
                off -= take
            open_parts = [p for p in parts if p[1] > 0]
        else:  # we have paid or debited more than the bill: an advance
            open_parts = [[parts[-1][0], less]]
        self.due_date = open_parts[0][0] if open_parts else parts[-1][0]
        self.late = max(0, (as_on - self.due_date).days)
        self.age = max(0, (as_on - self.bill_date).days)
        self.buckets = [ZERO] * 5
        if by_bill:
            self.buckets[bill_bucket(self.age)] = self.balance
        else:
            for d, a in open_parts:
                self.buckets[due_bucket((as_on - d).days)] += a

    @property
    def overdue(self) -> Decimal:
        return self.balance - self.buckets[0] if self.late else ZERO


def open_bills(
    company,
    as_on: datetime.date,
    *,
    by_bill: bool = False,
    branch: int | None = None,
    purchaser: int | None = None,
    supplier: int | None = None,
) -> list[Bill]:
    """Every supplier bill with something still owed (or overpaid) on `as_on`."""
    invoices = PurchaseInvoice.objects.filter(
        company=company, status=PurchaseInvoice.SUBMITTED, posting_date__lte=as_on
    ).select_related("supplier__party__credit_term", "supplier__salesman")
    ledgers = Ledger.objects.filter(company=company, party_side="supplier")
    if branch:
        invoices = invoices.filter(branch_id=branch)
    if purchaser:
        invoices = invoices.filter(supplier__salesman_id=purchaser)
        ledgers = ledgers.filter(salesman_id=purchaser)
    if supplier:
        invoices = invoices.filter(supplier_id=supplier)
        ledgers = ledgers.filter(pk=supplier)
    bills: dict[int, Bill] = {}
    for inv in invoices.prefetch_related("dues"):
        b = Bill(
            key=f"pi-{inv.pk}",
            supplier=inv.supplier,
            invoice_id=inv.pk,
            bill_no=inv.bill_no or inv.number,
            our_no=inv.number,
            bill_date=inv.bill_date or inv.posting_date,
            amount=inv.total,
            tds=inv.tds_total,
            parts=[[d.due_date, d.amount] for d in inv.dues.all()],
            branch_id=inv.branch_id,
        )
        bills[inv.pk] = b
    ids = list(bills)
    if ids:
        sections: dict[int, list[str]] = defaultdict(list)
        for inv_id, sec, rate in (
            PurchaseInvoiceTds.objects.filter(invoice_id__in=ids, amount__gt=0)
            .order_by("invoice_id", "position")
            .values_list("invoice_id", "section", "rate")
        ):
            label = f"{sec} {_plain(rate)}%" if sec else f"{_plain(rate)}%"
            if label not in sections[inv_id]:
                sections[inv_id].append(label)
        for inv_id, labels in sections.items():
            bills[inv_id].tds_notes.extend(labels)
        for inv_id, number, total, tds in (
            DebitNote.objects.filter(
                invoice_id__in=ids, status=DebitNote.SUBMITTED, note_date__lte=as_on
            )
            .order_by("note_date", "id")
            .values_list("invoice_id", "number", "total", "tds_total")
        ):
            b = bills[inv_id]
            b.dn += total
            b.tds -= tds
            b.dn_notes.append(number)
        for inv_id, number, amount in (
            TdsAdjustmentLine.objects.filter(
                invoice_id__in=ids,
                adjustment__status="submitted",
                adjustment__adj_date__lte=as_on,
            )
            .order_by("adjustment__adj_date", "adjustment_id")
            .values_list("invoice_id", "adjustment__number", "amount")
        ):
            b = bills[inv_id]
            b.tds += amount
            sign = "+" if amount >= 0 else "-"
            b.tds_notes.append(f"adj. {sign}{money(abs(amount))} ({number})")
    out = list(bills.values())
    # Opening bills from the old books: no branch, so only for all branches.
    if not branch:
        for ob in (
            LedgerOpeningBill.objects.filter(ledger__in=ledgers, bill_date__lte=as_on)
            .select_related("ledger__party__credit_term", "ledger__salesman")
            .order_by("bill_date", "id")
        ):
            signed = ob.amount if ob.side == CR else -ob.amount
            out.append(
                Bill(
                    key=f"ob-{ob.pk}",
                    supplier=ob.ledger,
                    invoice_id=None,
                    bill_no=ob.ref,
                    our_no="Opening",
                    bill_date=ob.bill_date,
                    amount=signed,
                    parts=[[ob.due_date or ob.bill_date, signed]],
                )
            )
    for b in out:
        b.settle(as_on, by_bill)
    return [b for b in out if b.balance != 0]


# --- rows -------------------------------------------------------------------


def _code(ledger: Ledger) -> str:
    return ledger.party.vendor_number if ledger.party_id else ""


def _term(ledger: Ledger) -> str:
    party = ledger.party if ledger.party_id else None
    return party.credit_term.name if party and party.credit_term_id else ""


def bill_row(b: Bill, labels: list[str]) -> dict:
    s = b.supplier
    kind = next((i for i, v in enumerate(b.buckets) if v), 0)
    return {
        "id": b.key,
        "invoice": b.invoice_id,
        "supplier_id": s.pk,
        "supplier": s.name,
        "code": _code(s),
        "term": _term(s),
        "bill_no": b.bill_no,
        "our_no": b.our_no,
        "bill_date": b.bill_date,
        "due_date": b.due_date,
        "amount": money(b.amount),
        "tds": money(b.tds),
        "tds_note": ", ".join(b.tds_notes),
        "dn": money(b.dn),
        "dn_note": ", ".join(b.dn_notes),
        "paid": money(b.paid),
        "paid_note": ", ".join(b.paid_notes),
        "balance": money(b.balance),
        "late": b.late,
        "age": labels[kind],
        "age_index": kind,
        "buckets": [money(v) for v in b.buckets],
    }


def supplier_rows(bills: list[Bill]) -> list[dict]:
    by: dict[int, dict] = {}
    for b in bills:
        s = b.supplier
        r = by.get(s.pk)
        if r is None:
            r = by[s.pk] = {
                "id": s.pk,
                "supplier": s.name,
                "code": _code(s),
                "term": _term(s),
                "purchaser": s.salesman.name if s.salesman_id else "",
                "bills": 0,
                "b": [ZERO] * 5,
                "due": ZERO,
                "overdue": ZERO,
                "oldest": 0,
            }
        r["bills"] += 1
        r["b"] = [x + y for x, y in zip(r["b"], b.buckets, strict=True)]
        r["due"] += b.balance
        r["overdue"] += b.overdue
        r["oldest"] = max(r["oldest"], b.late)
    return list(by.values())


def _supplier_out(r: dict) -> dict:
    return {
        **r,
        "b": [money(v) for v in r["b"]],
        "due": money(r["due"]),
        "overdue": money(r["overdue"]),
    }


# --- searching, sorting, paging ---------------------------------------------

SUPPLIER_SEARCH = {"supplier": "supplier", "code": "code", "term": "term", "purchaser": "purchaser"}
BILL_SEARCH = {
    "supplier": "supplier",
    "bill_no": "bill_no",
    "our_no": "our_no",
    "bill_date": "bill_date_text",
    "due_date": "due_date_text",
    "age": "age",
}
SUPPLIER_SORT = {
    "supplier": lambda r: r["supplier"].lower(),
    "code": lambda r: r["code"],
    "term": lambda r: r["term"].lower(),
    "purchaser": lambda r: r["purchaser"].lower(),
    "bills": lambda r: r["bills"],
    "b0": lambda r: r["b"][0],
    "b1": lambda r: r["b"][1],
    "b2": lambda r: r["b"][2],
    "b3": lambda r: r["b"][3],
    "b4": lambda r: r["b"][4],
    "due": lambda r: r["due"],
    "oldest": lambda r: r["oldest"],
}
BILL_SORT = {
    "supplier": lambda r: (r["supplier"].lower(), r["bill_date"]),
    "bill_no": lambda r: r["bill_no"].lower(),
    "our_no": lambda r: r["our_no"],
    "bill_date": lambda r: r["bill_date"],
    "due_date": lambda r: r["due_date"],
    "amount": lambda r: Decimal(r["amount"]),
    "tds": lambda r: Decimal(r["tds"]),
    "dn": lambda r: Decimal(r["dn"]),
    "paid": lambda r: Decimal(r["paid"]),
    "balance": lambda r: Decimal(r["balance"]),
    "late": lambda r: r["late"],
    "age": lambda r: r["age_index"],
}


def _search(rows: list[dict], params, columns: dict[str, str]) -> list[dict]:
    for name, key in columns.items():
        for word in paging.words(params.get(name, "").lower()):
            rows = [r for r in rows if word in str(r.get(key, "")).lower()]
    return rows


def _sort(rows: list[dict], key: str, sorts: dict, default) -> list[dict]:
    rows = sorted(rows, key=default)
    by = sorts.get(key.removeprefix("-"))
    if by:
        rows = sorted(rows, key=by, reverse=key.startswith("-"))
    return rows


def _day(params, name: str, default: datetime.date) -> datetime.date:
    text = params.get(name, "")
    if not text:
        return default
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as err:
        raise ValidationError({name: ["Give the date as YYYY-MM-DD."]}) from err


def _number(params, name: str) -> int | None:
    text = params.get(name, "")
    if not text:
        return None
    if not text.isdigit():
        raise ValidationError({name: ["Pick from the list."]})
    return int(text)


@dataclass
class Asked:
    as_on: datetime.date
    by_bill: bool
    branch: int | None
    purchaser: int | None
    supplier: int | None
    overdue: bool

    @property
    def labels(self) -> list[str]:
        return BILL_LABELS if self.by_bill else DUE_LABELS


def asked(params) -> Asked:
    age_by = params.get("age_by", "due")
    if age_by not in ("due", "bill"):
        raise ValidationError({"age_by": ["Pick Due Date or Bill Date."]})
    return Asked(
        as_on=_day(params, "as_on", datetime.date.today()),
        by_bill=age_by == "bill",
        branch=_number(params, "branch"),
        purchaser=_number(params, "purchaser"),
        supplier=_number(params, "ledger"),
        overdue=params.get("overdue") == "1",
    )


def report_bills(company, a: Asked) -> list[Bill]:
    bills = open_bills(
        company,
        a.as_on,
        by_bill=a.by_bill,
        branch=a.branch,
        purchaser=a.purchaser,
        supplier=a.supplier,
    )
    if a.overdue:
        bills = [b for b in bills if b.late > 0 and b.balance > 0]
    return bills


def suppliers_view(company, params, a: Asked) -> tuple[list[dict], dict]:
    rows = supplier_rows(report_bills(company, a))
    rows = _search(rows, params, SUPPLIER_SEARCH)
    totals = {
        "suppliers": len(rows),
        "bills": sum(r["bills"] for r in rows),
        "b": [money(sum((r["b"][i] for r in rows), ZERO)) for i in range(5)],
        "due": money(sum((r["due"] for r in rows), ZERO)),
    }
    rows = _sort(rows, params.get("sort", ""), SUPPLIER_SORT, lambda r: (-r["due"], r["supplier"]))
    return [_supplier_out(r) for r in rows], totals


def bills_view(company, params, a: Asked) -> tuple[list[dict], dict, dict]:
    bills = report_bills(company, a)
    rows = [bill_row(b, a.labels) for b in bills]
    for r in rows:
        r["bill_date_text"], r["due_date_text"] = dmy(r["bill_date"]), dmy(r["due_date"])
    rows = _search(rows, params, BILL_SEARCH)

    def add(rs, key):
        return money(sum((Decimal(r[key]) for r in rs), ZERO))

    totals = {
        "bills": len(rows),
        "suppliers": len({r["supplier_id"] for r in rows}),
        **{k: add(rows, k) for k in ("amount", "tds", "dn", "paid", "balance")},
    }
    groups: dict[int, dict] = {}
    by_supplier = defaultdict(list)
    for r in rows:
        by_supplier[r["supplier_id"]].append(r)
    for sid, rs in by_supplier.items():
        groups[sid] = {
            "bills": len(rs),
            **{k: add(rs, k) for k in ("amount", "tds", "dn", "paid", "balance")},
        }
    rows = _sort(
        rows,
        params.get("sort", ""),
        BILL_SORT,
        lambda r: (r["supplier"].lower(), r["bill_date"], r["our_no"]),
    )
    for r in rows:
        r.pop("bill_date_text")
        r.pop("due_date_text")
    return rows, totals, groups


def _page(rows: list, params) -> dict:
    if params.get("all") == "1":
        if len(rows) > ALL_LIMIT:
            raise ValidationError({"detail": "Too many rows to print. Pick a branch or purchaser."})
        return {"results": rows}
    size = paging.PAGE_SIZE
    last = max(1, -(-len(rows) // size))
    try:
        page = min(max(1, int(params.get("page", 1))), last)
    except ValueError:
        page = 1
    return {
        "count": len(rows),
        "page": page,
        "pages": last,
        "page_size": size,
        "results": rows[(page - 1) * size : page * size],
    }


def _choices(company) -> dict:
    used = (
        Ledger.objects.filter(company=company, party_side="supplier", salesman__isnull=False)
        .values_list("salesman_id", flat=True)
        .distinct()
    )
    return {
        "branches": [{"id": b.pk, "name": b.name} for b in company.branches.order_by("name", "pk")],
        "purchasers": [
            {"id": p.pk, "name": p.name}
            for p in SalesPerson.objects.filter(Q(pk__in=used)).order_by("name", "pk")
        ],
    }


class PayablesView(APIView):
    """GET companies/<id>/accounts-payable/?view=suppliers|bills&as_on=&age_by=due|bill
    &branch=&purchaser=&ledger=&overdue=1&page=&sort= and a search per column.
    ?all=1 gives every row, for Print, PDF and Excel."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        params = request.query_params
        a = asked(params)
        view = params.get("view", "suppliers")
        out = {
            "company_name": company.name,
            "as_on": a.as_on,
            "age_by": "bill" if a.by_bill else "due",
            "labels": a.labels,
            **_choices(company),
        }
        if view == "suppliers":
            rows, totals = suppliers_view(company, params, a)
            return Response({**out, "totals": totals, **_page(rows, params)})
        if view == "bills":
            rows, totals, groups = bills_view(company, params, a)
            page = _page(rows, params)
            shown = {r["supplier_id"] for r in page["results"]}
            return Response(
                {
                    **out,
                    "totals": totals,
                    "groups": {str(k): v for k, v in groups.items() if k in shown},
                    **page,
                }
            )
        raise ValidationError({"view": ["Pick suppliers or bills."]})
