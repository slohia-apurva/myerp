"""Purchase reports (Sidharth, 2026-11-27, previews mockups/purchase-reports/1, 2 and 4).

Reports › Purchase › Pending Purchase Orders: every submitted order with goods
still to come, one row per order. A line is pending while less than its
quantity has been received and nobody used "Close Line" on it. Like the other
long lists (core/paging.py): 25 rows a page, a search per column on the server,
?sort=key / -key, and ?all=1 for Print and Download PDF.
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    Case,
    CharField,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Func,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import VIEW, _check, _company
from buying.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from core import paging
from core.api import Signed

ZERO = Decimal("0")
PAISE = Decimal("0.01")
# Print and Download PDF take every row at once; past this, narrow the dates.
ALL_LIMIT = 5000


def _day(request, name: str) -> datetime.date | None:
    text = request.query_params.get(name, "")
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as err:
        raise ValidationError({name: ["Give the date as YYYY-MM-DD."]}) from err


def _dmy(field: str) -> Func:
    """A date as the screen shows it (27-11-2026), so its column can be searched."""
    return Func(F(field), Value("DD-MM-YYYY"), function="to_char", output_field=CharField())


def _status_search(rows, text: str):
    """Each word typed must be in the status as the screen shows it."""
    for word in paging.words(text.lower()):
        rows = rows.filter(
            status__in=[code for code, label in PurchaseOrder.STATUSES if word in label.lower()]
        )
    return rows


def _money(value: Decimal | None) -> str:
    return str((value or ZERO).quantize(PAISE, rounding=ROUND_HALF_UP))


PENDING = Q(lines__closed_at__isnull=True, lines__qty__gt=F("lines__received_qty"))
MONEY = DecimalField(max_digits=30, decimal_places=10)

# Column key -> what it sorts by; a "-" in front turns it round ("late": most days
# late first means the earliest Expected Delivery first).
SORTS = {
    "number": "number",
    "date": "order_date",
    "supplier": "supplier__name",
    "expected": "expected_date",
    "late": "-expected_date",
    "purchaser": "purchaser__name",
    "branch": "branch__name",
    "lines": "lines_pending",
    "value": "order_value",
    "pending": "pending_value",
    "status": "status",
}
SEARCHES = {
    "number": ["number"],
    "supplier": ["supplier__name"],
    "purchaser": ["purchaser__name"],
    "branch_name": ["branch__name"],
    "date": ["date_text"],
    "expected": ["expected_text"],
}


def pending_orders(company, params, today: datetime.date):
    rows = PurchaseOrder.objects.filter(company=company, status__in=PurchaseOrder.OPEN)
    if start := params.get("from"):
        rows = rows.filter(order_date__gte=start)
    if end := params.get("to"):
        rows = rows.filter(order_date__lte=end)
    if branch := params.get("branch", ""):
        rows = rows.filter(branch_id=branch) if branch.isdigit() else rows.none()
    if params.get("late") == "1":
        rows = rows.filter(expected_date__lt=today)
    rows = rows.annotate(date_text=_dmy("order_date"), expected_text=_dmy("expected_date"))
    rows = paging.search(rows, params, SEARCHES)
    rows = _status_search(rows, params.get("status", ""))
    balance = ExpressionWrapper(F("lines__qty") - F("lines__received_qty"), output_field=MONEY)
    rows = rows.annotate(
        lines_pending=Count("lines", filter=PENDING),
        order_value=Sum("lines__taxable"),
        pending_value=Sum(
            ExpressionWrapper(balance * F("lines__taxable") / F("lines__qty"), output_field=MONEY),
            filter=PENDING,
        ),
    ).filter(lines_pending__gt=0)
    return rows.select_related("supplier", "purchaser", "branch")


def _sorted(rows, key: str, sorts=SORTS, then=("order_date", "number", "pk")):
    field = sorts.get(key.removeprefix("-"))
    if not field:
        return rows.order_by(*then)
    down = key.startswith("-") != field.startswith("-")
    expr = F(field.removeprefix("-"))
    first = expr.desc(nulls_last=True) if down else expr.asc(nulls_last=True)
    return rows.order_by(first, *then)


def _answer(out: dict, rows, count: int, params, row, noun: str) -> Response:
    """Every row (?all=1, for Print, PDF and Excel) or one page of 25."""
    if params.get("all") == "1":
        if count > ALL_LIMIT:
            raise ValidationError(
                {"detail": f"{count:,} {noun} is too many to print. Narrow the PO dates."}
            )
        return Response({**out, "results": [row(r) for r in rows]})
    size = paging.PAGE_SIZE
    last = max(1, -(-count // size))
    try:
        page = min(max(1, int(params.get("page", 1))), last)
    except ValueError:
        page = 1
    return Response(
        {
            **out,
            "count": count,
            "page": page,
            "pages": last,
            "page_size": size,
            "results": [row(r) for r in rows[(page - 1) * size : page * size]],
        }
    )


def _branches(company) -> list[dict]:
    return [{"id": b.pk, "name": b.name} for b in company.branches.order_by("name", "pk")]


def _row(o: PurchaseOrder, today: datetime.date) -> dict:
    late = (today - o.expected_date).days if o.expected_date and o.expected_date < today else 0
    return {
        "id": o.pk,
        "number": o.number,
        "date": o.order_date,
        "supplier": o.supplier.name,
        "expected": o.expected_date,
        "late": late,
        "purchaser": o.purchaser.name if o.purchaser else "",
        "branch": o.branch.name,
        "lines": o.lines_pending,
        "value": _money(o.order_value),
        "pending": _money(o.pending_value),
        "status": o.get_status_display(),
    }


class PendingOrdersView(APIView):
    """GET companies/<id>/pending-purchase-orders/?from=&to=&branch=&late=1&page=&sort=
    and a search per column (number, date, supplier, expected, purchaser, branch_name,
    status). ?all=1 gives every row, for printing."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        _day(request, "from")
        _day(request, "to")
        today = datetime.date.today()
        rows = pending_orders(company, request.query_params, today)
        # The totals add up each order's figures, over every page.
        sums = {"orders": 0, "lines": 0, "value": ZERO, "pending": ZERO}
        for o in rows.values("lines_pending", "order_value", "pending_value"):
            sums["orders"] += 1
            sums["lines"] += o["lines_pending"]
            sums["value"] += o["order_value"] or ZERO
            sums["pending"] += o["pending_value"] or ZERO
        rows = _sorted(rows, request.query_params.get("sort", ""))
        count = sums["orders"]
        out = {
            "company_name": company.name,
            "branches": _branches(company),
            "totals": {
                "orders": count,
                "lines": sums["lines"],
                "value": _money(sums["value"]),
                "pending": _money(sums["pending"]),
            },
        }
        return _answer(out, rows, count, request.query_params, lambda o: _row(o, today), "orders")


# ---------------------------------------------------------------------------
# Reports › Purchase › Procurement Tracker (preview mockups/purchase-reports/2):
# one row per line of a submitted order, with what was ordered, received and
# billed and what is still to come. ?lines=pending (the default) keeps lines
# with a balance; received keeps those received in full or closed; all both.

LINE_PENDING = Q(closed_at__isnull=True, qty__gt=F("received_qty"))
LINE_SORTS = {
    "supplier": "order__supplier__name",
    "number": "order__number",
    "date": "order__order_date",
    "expected": "order__expected_date",
    "item_code": "item__item_number",
    "item_name": "item__name",
    "unit": "unit__short_name",
    "ordered": "qty",
    "received": "received_qty",
    "balance": "balance",
    "grn": "grn_number",
    "billed": "billed",
    "status": "line_status",
    "rate": "rate",
    "pending": "pending_value",
    "purchaser": "order__purchaser__name",
    "branch": "order__branch__name",
    "reason": "close_reason",
}
LINE_SEARCHES = {
    "supplier": ["order__supplier__name"],
    "number": ["order__number"],
    "date": ["date_text"],
    "expected": ["expected_text"],
    "item_code": ["item__item_number"],
    "item_name": ["item__name"],
    "unit": ["unit__short_name", "unit__name"],
    "grn": ["grn_number"],
    "purchaser": ["order__purchaser__name"],
    "branch_name": ["order__branch__name"],
    "reason": ["close_reason"],
}
SUBMITTED = (
    PurchaseOrder.ORDERED,
    PurchaseOrder.PART_RECEIVED,
    PurchaseOrder.RECEIVED,
    PurchaseOrder.CLOSED,
)
CLOSED, RECEIVED, PART, WAITING = "Closed", "Received", "Part received", "Pending"


def tracker_lines(company, params):
    rows = PurchaseOrderLine.objects.filter(order__company=company, order__status__in=SUBMITTED)
    if start := params.get("from"):
        rows = rows.filter(order__order_date__gte=start)
    if end := params.get("to"):
        rows = rows.filter(order__order_date__lte=end)
    if branch := params.get("branch", ""):
        rows = rows.filter(order__branch_id=branch) if branch.isdigit() else rows.none()
    which = params.get("lines", "pending")
    if which == "pending":
        rows = rows.filter(LINE_PENDING)
    elif which == "received":
        rows = rows.exclude(LINE_PENDING)
    receipts = GoodsReceiptLine.objects.filter(
        order_line=OuterRef("pk"), receipt__status=GoodsReceipt.SUBMITTED
    )
    latest = receipts.order_by("-receipt__receipt_date", "-receipt_id")
    billed = receipts.values("order_line").annotate(t=Sum("billed_qty")).values("t")
    rows = rows.annotate(
        date_text=_dmy("order__order_date"),
        expected_text=_dmy("order__expected_date"),
        grn_number=Subquery(latest.values("receipt__number")[:1]),
        grn_id=Subquery(latest.values("receipt_id")[:1]),
        billed=Coalesce(Subquery(billed[:1]), Value(ZERO), output_field=MONEY),
        balance=Case(
            When(LINE_PENDING, then=F("qty") - F("received_qty")),
            default=Value(ZERO),
            output_field=MONEY,
        ),
        line_status=Case(
            When(closed_at__isnull=False, then=Value(CLOSED)),
            When(received_qty__gte=F("qty"), then=Value(RECEIVED)),
            When(received_qty__gt=0, then=Value(PART)),
            default=Value(WAITING),
            output_field=CharField(),
        ),
    )
    rows = rows.annotate(
        pending_value=ExpressionWrapper(F("balance") * F("taxable") / F("qty"), output_field=MONEY)
    )
    rows = paging.search(rows, params, LINE_SEARCHES)
    for word in paging.words(params.get("status", "").lower()):
        rows = rows.filter(line_status__icontains=word)
    return rows.select_related(
        "order__supplier", "order__purchaser", "order__branch", "item", "unit"
    )


def _line_row(ln: PurchaseOrderLine, today: datetime.date) -> dict:
    o = ln.order
    return {
        "id": ln.pk,
        "order": o.pk,
        "number": o.number,
        "date": o.order_date,
        "supplier": o.supplier.name,
        "expected": o.expected_date,
        "late": bool(ln.balance and o.expected_date and o.expected_date < today),
        "item_code": ln.item.item_number,
        "item_name": ln.item.name,
        "unit": ln.unit.short_name,
        "ordered": str(ln.qty),
        "received": str(ln.received_qty),
        "balance": str(ln.balance),
        "grn": ln.grn_number or "",
        "grn_id": ln.grn_id,
        "billed": str(ln.billed),
        "status": ln.line_status,
        "rate": str(ln.rate),
        "pending": _money(ln.pending_value),
        "purchaser": o.purchaser.name if o.purchaser else "",
        "branch": o.branch.name,
        "reason": ln.close_reason if ln.closed_at else "",
    }


class ProcurementTrackerView(APIView):
    """GET companies/<id>/procurement-tracker/?from=&to=&branch=&lines=pending|received|all
    &page=&sort= and a search per column. ?all=1 gives every row, for printing."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        _day(request, "from")
        _day(request, "to")
        if request.query_params.get("lines", "pending") not in ("pending", "received", "all"):
            raise ValidationError({"lines": ["Pick pending, received or all."]})
        today = datetime.date.today()
        rows = tracker_lines(company, request.query_params)
        count = rows.count()
        rows = _sorted(
            rows,
            request.query_params.get("sort", ""),
            LINE_SORTS,
            ("order__order_date", "order__number", "position", "pk"),
        )
        out = {"company_name": company.name, "branches": _branches(company)}
        return _answer(
            out, rows, count, request.query_params, lambda ln: _line_row(ln, today), "lines"
        )
