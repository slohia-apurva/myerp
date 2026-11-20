"""Stock reports, read straight from the stock ledger (design rule 1): the
Stock Summary (what is on hand as on a day, by item, batch and bin, with its
value) and the Stock Ledger of one item (every move in and out, with a running
balance). Asked by Sidharth on 2026-11-18 to check his first goods receipt.

Values are the rupee values the moves were posted at, plus any change made
later by a supplier's bill at another rate (a stock revaluation), which is
counted at the bin and batch the revalued lot came in to."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import Signed, _company
from core.models import Batch, Branch, Item, WarehouseLocation
from posting.models import StockMove, StockRevaluation

ZERO = Decimal("0")
SEE_STOCK = "stock.view"

# Where each kind of entry opens, for the links in the reports.
PAGES = {
    "goods_receipt": "goods-receipts",
    "purchase_invoice": "purchase-invoices",
    "purchase_return": "purchase-returns",
    "debit_note": "debit-notes",
    "tds_adjustment": "tds-adjustments",
    "credit_note": "credit-notes",
}
NAMES = {
    "goods_receipt": "Goods Receipt",
    "purchase_invoice": "Purchase Invoice",
    "purchase_return": "Purchase Return",
    "debit_note": "Debit Note",
    "tds_adjustment": "TDS Adjustment",
    "credit_note": "Credit Note",
}


def _see_stock(request) -> None:
    if not request.user.can(SEE_STOCK):
        raise PermissionDenied("Your role does not allow seeing stock.")


def _day(request, key: str, default: date | None) -> date | None:
    raw = request.query_params.get(key, "")
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({key: "Give the date as YYYY-MM-DD."}) from exc


def _id(request, key: str) -> int | None:
    raw = request.query_params.get(key, "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValidationError({key: "Not a valid choice."}) from exc


def short_bin(loc) -> str:
    """The bin or area alone (see WarehouseLocation.__str__)."""
    return str(loc)


def _place(loc) -> str:
    """The bin or area alone; the warehouse has its own filter."""
    return short_bin(loc)


def entry(voucher_type: str, voucher_id: int, voucher_no: str) -> dict:
    return {
        "type": voucher_type,
        "type_label": NAMES.get(voucher_type, voucher_type.replace("_", " ").title()),
        "id": voucher_id,
        "number": voucher_no,
        "page": PAGES.get(voucher_type, ""),
    }


class StockSummaryView(APIView):
    """GET companies/<id>/stock-summary/?as_on=&branch=&item=

    Every item with stock on the day, its batches, and the bins or areas each
    batch is in: quantity in the item's stock unit and rupee value."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _see_stock(request)
        company = _company(request, pk)
        as_on = _day(request, "as_on", date.today())
        moves = StockMove.objects.filter(company=company, date__lte=as_on)
        revals = StockRevaluation.objects.filter(company=company, date__lte=as_on)
        branch = _id(request, "branch")
        if branch is not None:
            moves = moves.filter(branch_id=branch)
            revals = revals.filter(branch_id=branch)
        item = _id(request, "item")
        if item is not None:
            moves = moves.filter(item_id=item)
            revals = revals.filter(item_id=item)

        # (item, batch, location) -> [qty, value]
        cells: dict[tuple, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
        for row in moves.values("item", "batch", "location").annotate(
            q=Sum("qty"), v=Sum("value", filter=Q(valued=True))
        ):
            key = (row["item"], row["batch"], row["location"])
            cells[key][0] += row["q"] or ZERO
            cells[key][1] += row["v"] or ZERO
        for row in revals.values("item", "lot__move__batch", "lot__move__location").annotate(
            v=Sum("value")
        ):
            key = (row["item"], row["lot__move__batch"], row["lot__move__location"])
            cells[key][1] += row["v"] or ZERO
        cells = {k: v for k, v in cells.items() if v[0] != 0 or v[1] != 0}

        items = Item.objects.select_related("stock_unit").in_bulk({k[0] for k in cells})
        batches = Batch.objects.in_bulk({k[1] for k in cells if k[1]})
        places = WarehouseLocation.objects.select_related("parent", "branch__company").in_bulk(
            {k[2] for k in cells}
        )

        # One flat line per item, batch and bin (Sidharth, 2026-11-18, preview
        # mockups/reports/3-stock-summary-flat-preview.png).
        lines = []
        for (it, bt, loc), (q, v) in cells.items():
            item_obj, place = items[it], places[loc]
            lines.append(
                {
                    "item": it,
                    "item_number": item_obj.item_number,
                    "item_name": item_obj.name,
                    "batch": batches[bt].number if bt else "",
                    "warehouse": place.branch.name,
                    "bin": short_bin(place),
                    "unit": item_obj.stock_unit.short_name,
                    "qty": str(q),
                    "rate": str((v / q).quantize(Decimal("0.01"))) if q else "",
                    "value": str(v),
                }
            )
        lines.sort(
            key=lambda r: (
                r["item_name"].lower(),
                r["batch"].lower(),
                r["warehouse"].lower(),
                r["bin"].lower(),
            )
        )
        return Response(
            {
                "company_name": company.name,
                "as_on": as_on,
                "lines": lines,
                "total_value": str(sum((Decimal(r["value"]) for r in lines), ZERO)),
            }
        )


class StockLedgerView(APIView):
    """GET companies/<id>/stock-ledger/?item=&from=&to=&branch=&batch=&location=

    Every move of one item in the period, oldest first, with the opening
    balance before it and the balance after each move. A stock revaluation
    shows as a row with no quantity that changes the value only."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _see_stock(request)
        company = _company(request, pk)
        item_id = _id(request, "item")
        if item_id is None:
            raise ValidationError({"item": "Pick an item."})
        item = Item.objects.select_related("stock_unit").filter(pk=item_id).first()
        if item is None:
            raise NotFound("No such item.")
        start = _day(request, "from", None)
        end = _day(request, "to", date.today())
        if start and end and start > end:
            raise ValidationError({"from": "From is after To."})

        moves = StockMove.objects.filter(company=company, item=item, date__lte=end)
        revals = StockRevaluation.objects.filter(company=company, item=item, date__lte=end)
        every = moves  # for the batch and bin choices
        for key, field, rfield in (
            ("branch", "branch_id", "branch_id"),
            ("batch", "batch_id", "lot__move__batch_id"),
            ("location", "location_id", "lot__move__location_id"),
        ):
            value = _id(request, key)
            if value is not None:
                moves = moves.filter(**{field: value})
                revals = revals.filter(**{rfield: value})

        open_q = open_v = ZERO
        if start:
            before = moves.filter(date__lt=start).aggregate(
                q=Sum("qty"), v=Sum("value", filter=Q(valued=True))
            )
            open_v = (before["v"] or ZERO) + (
                revals.filter(date__lt=start).aggregate(v=Sum("value"))["v"] or ZERO
            )
            open_q = before["q"] or ZERO
            moves = moves.filter(date__gte=start)
            revals = revals.filter(date__gte=start)

        rows = []
        for m in moves.select_related("batch", "location__parent", "location__branch__company"):
            rows.append(
                (
                    m.date,
                    m.created_at,
                    m.pk,
                    {
                        "date": m.date,
                        "entry": entry(m.voucher_type, m.voucher_id, m.voucher_no),
                        "cancel": m.is_reversal,
                        "batch": m.batch.number if m.batch_id else "",
                        "place": _place(m.location),
                        "qty_in": str(m.qty) if m.qty > 0 else "",
                        "qty_out": str(-m.qty) if m.qty < 0 else "",
                        "_q": m.qty,
                        "_v": m.value if m.valued else ZERO,
                    },
                )
            )
        for r in revals.select_related(
            "lot__move__batch",
            "lot__move__location__parent",
            "lot__move__location__branch__company",
        ):
            mv = r.lot.move
            rows.append(
                (
                    r.date,
                    r.created_at,
                    r.pk,
                    {
                        "date": r.date,
                        "entry": entry(r.voucher_type, r.voucher_id, r.voucher_no),
                        "cancel": r.is_reversal,
                        "batch": mv.batch.number if mv.batch_id else "",
                        "place": _place(mv.location),
                        "qty_in": "",
                        "qty_out": "",
                        "revaluation": True,
                        "_q": ZERO,
                        "_v": r.value,
                    },
                )
            )
        rows.sort(key=lambda r: (r[0], r[1], r[2]))
        q, v = open_q, open_v
        out = []
        for *_, row in rows:
            q += row.pop("_q")
            moved = row.pop("_v")
            v += moved
            row.update(value=str(moved), balance_qty=str(q), balance_value=str(v))
            out.append(row)

        options = every.select_related("batch", "location__parent", "location__branch__company")
        batch_opts = {m.batch_id: m.batch.number for m in options if m.batch_id}
        place_opts = {m.location_id: _place(m.location) for m in options}
        return Response(
            {
                "company_name": company.name,
                "item": item.pk,
                "item_number": item.item_number,
                "item_name": item.name,
                "unit": item.stock_unit.short_name,
                "from": start,
                "to": end,
                "opening_qty": str(open_q),
                "opening_value": str(open_v),
                "rows": out,
                "closing_qty": str(q),
                "closing_value": str(v),
                "batches": [
                    {"id": k, "number": n}
                    for k, n in sorted(batch_opts.items(), key=lambda x: x[1].lower())
                ],
                "places": [
                    {"id": k, "name": n}
                    for k, n in sorted(place_opts.items(), key=lambda x: x[1].lower())
                ],
            }
        )


def _last_in(move: StockMove | None) -> dict | None:
    if move is None:
        return None
    return {"date": move.date, **entry(move.voucher_type, move.voucher_id, move.voucher_no)}


class ItemStockView(APIView):
    """GET companies/<id>/item-stock/            -> {"items": {item id: qty}}
    GET companies/<id>/item-stock/?item=<id>      -> that item's stock today

    For the Items master (Sidharth, 2026-11-18, preview
    mockups/reports/2-items-stock-preview.png): the "In Stock" column, and the
    "Stock" box beside an item with each warehouse's quantity and value, its
    batches and when it was last received."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _see_stock(request)
        company = _company(request, pk)
        moves = StockMove.objects.filter(company=company)
        item_id = _id(request, "item")
        if item_id is None:
            rows = moves.values("item").annotate(q=Sum("qty"))
            return Response({"items": {r["item"]: str(r["q"]) for r in rows}})

        item = Item.objects.select_related("stock_unit").filter(pk=item_id).first()
        if item is None:
            raise NotFound("No such item.")
        moves = moves.filter(item=item)
        revals = StockRevaluation.objects.filter(company=company, item=item)
        per_branch: dict[int, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
        for r in moves.values("branch", "branch__name").annotate(
            q=Sum("qty"), v=Sum("value", filter=Q(valued=True))
        ):
            per_branch[r["branch"]] = [r["q"] or ZERO, r["v"] or ZERO]
        names = {
            b.pk: b.name
            for b in Branch.objects.select_related("company").filter(pk__in=list(per_branch))
        }
        for r in revals.values("branch").annotate(v=Sum("value")):
            per_branch[r["branch"]][1] += r["v"] or ZERO
        branches = [
            {"branch": b, "name": names.get(b, ""), "qty": str(q), "value": str(v)}
            for b, (q, v) in sorted(per_branch.items(), key=lambda x: names.get(x[0], ""))
            if q != 0 or v != 0
        ]
        batches = [
            {
                "number": r["batch__number"],
                "expiry_date": r["batch__expiry_date"],
                "qty": str(r["q"]),
            }
            for r in moves.exclude(batch=None)
            .values("batch__number", "batch__expiry_date")
            .annotate(q=Sum("qty"))
            .exclude(q=0)
            .order_by("batch__expiry_date", "batch__number")
        ]
        last = moves.filter(qty__gt=0, is_reversal=False).order_by("-date", "-id").first()
        return Response(
            {
                "item": item.pk,
                "unit": item.stock_unit.short_name,
                "qty": str(sum((Decimal(b["qty"]) for b in branches), ZERO)),
                "value": str(sum((Decimal(b["value"]) for b in branches), ZERO)),
                "branches": branches,
                "batches": batches,
                "last_received": _last_in(last),
            }
        )
