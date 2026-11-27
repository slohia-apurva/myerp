"""Purchase reports (Sidharth, 2026-11-27, previews mockups/purchase-reports/1 and 4).

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
    CharField,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Func,
    Q,
    Sum,
    Value,
)
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying.api import VIEW, _check, _company
from buying.models import PurchaseOrder
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


def _sorted(rows, key: str):
    field = SORTS.get(key.removeprefix("-"))
    if not field:
        return rows.order_by("order_date", "number", "pk")
    down = key.startswith("-") != field.startswith("-")
    expr = F(field.removeprefix("-"))
    first = expr.desc(nulls_last=True) if down else expr.asc(nulls_last=True)
    return rows.order_by(first, "order_date", "number", "pk")


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
            "branches": [
                {"id": b.pk, "name": b.name} for b in company.branches.order_by("name", "pk")
            ],
            "totals": {
                "orders": count,
                "lines": sums["lines"],
                "value": _money(sums["value"]),
                "pending": _money(sums["pending"]),
            },
        }
        if request.query_params.get("all") == "1":
            if count > ALL_LIMIT:
                raise ValidationError(
                    {"detail": f"{count:,} orders is too many to print. Narrow the PO dates."}
                )
            return Response({**out, "results": [_row(o, today) for o in rows]})
        last = max(1, -(-count // paging.PAGE_SIZE))
        try:
            page = min(max(1, int(request.query_params.get("page", 1))), last)
        except ValueError:
            page = 1
        size = paging.PAGE_SIZE
        return Response(
            {
                **out,
                "count": count,
                "page": page,
                "pages": last,
                "page_size": size,
                "results": [_row(o, today) for o in rows[(page - 1) * size : page * size]],
            }
        )
