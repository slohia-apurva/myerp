"""Accounts reports, read straight from the general ledger (design rule 1):
the Trial Balance (every ledger's opening, debits, credits and closing in a
period, under its ledger groups) and the Ledger Statement of one ledger (every
entry with a running balance). Asked by Sidharth on 2026-11-18 to check the
posting of his first goods receipt.

Balances are signed debit-positive. A ledger's opening balance is the one
entered on it (as at the start of the books) plus every entry before From."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import Signed, _company
from core.models import Ledger, LedgerGroup, fiscal_year_start
from posting.models import GLEntry
from posting.reports import _day, _id, entry

ZERO = Decimal("0")
SEE_BOOKS = "accounts.view"


def _see_books(request) -> None:
    if not request.user.can(SEE_BOOKS):
        raise PermissionDenied("Your role does not allow seeing the books.")


def _period(request, company) -> tuple[date, date]:
    end = _day(request, "to", date.today())
    start = _day(request, "from", fiscal_year_start(end, company.fiscal_year_start_month))
    if start > end:
        raise ValidationError({"from": "From is after To."})
    return start, end


class TrialBalanceView(APIView):
    """GET companies/<id>/trial-balance/?from=&to=

    `rows` in the order of the ledger group tree: each group (with the totals
    of everything under it) followed by its sub-groups and ledgers. Ledgers
    with no opening and no entries are left out, and so are groups left empty."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _see_books(request)
        company = _company(request, pk)
        start, end = _period(request, company)
        entries = GLEntry.objects.filter(company=company, date__lte=end)
        before = {
            r["ledger"]: (r["d"] or ZERO) - (r["c"] or ZERO)
            for r in entries.filter(date__lt=start)
            .values("ledger")
            .annotate(d=Sum("debit"), c=Sum("credit"))
        }
        during = {
            r["ledger"]: (r["d"] or ZERO, r["c"] or ZERO)
            for r in entries.filter(date__gte=start)
            .values("ledger")
            .annotate(d=Sum("debit"), c=Sum("credit"))
        }

        groups = list(LedgerGroup.objects.filter(company=company))
        kids: dict[int | None, list[LedgerGroup]] = defaultdict(list)
        for g in groups:
            kids[g.parent_id].append(g)
        for v in kids.values():
            v.sort(key=lambda g: (g.sequence, g.name.lower()))
        ledgers_of: dict[int, list[dict]] = defaultdict(list)
        for led in Ledger.objects.filter(company=company).order_by("name"):
            opening = led.opening_signed + before.get(led.pk, ZERO)
            debit, credit = during.get(led.pk, (ZERO, ZERO))
            if opening == 0 and debit == 0 and credit == 0:
                continue
            ledgers_of[led.group_id].append(
                {
                    "kind": "ledger",
                    "id": led.pk,
                    "name": led.name,
                    "opening": opening,
                    "debit": debit,
                    "credit": credit,
                    "closing": opening + debit - credit,
                }
            )

        rows: list[dict] = []

        def walk(g: LedgerGroup, depth: int, parent: int | None) -> dict | None:
            mine: list[dict] = []
            total = {"opening": ZERO, "debit": ZERO, "credit": ZERO, "closing": ZERO}
            for child in kids.get(g.pk, []):
                head = walk(child, depth + 1, g.pk)
                if head is not None:
                    mine.extend(head["rows"])
                    for k in total:
                        total[k] += head[k]
            for led in ledgers_of.get(g.pk, []):
                mine.append({**led, "depth": depth + 1, "parent": g.pk})
                for k in total:
                    total[k] += led[k]
            if not mine:
                return None
            head_row = {"kind": "group", "id": g.pk, "name": g.name, "depth": depth}
            head_row |= {"parent": parent, **total}
            return {"rows": [head_row, *mine], **total}

        grand = {"opening": ZERO, "debit": ZERO, "credit": ZERO, "closing": ZERO}
        for top in kids.get(None, []):
            done = walk(top, 0, None)
            if done is not None:
                rows.extend(done["rows"])
                for k in grand:
                    grand[k] += done[k]

        def show(r: dict) -> dict:
            return {
                **r,
                **{k: str(r[k]) for k in ("opening", "debit", "credit", "closing")},
            }

        return Response(
            {
                "company_name": company.name,
                "from": start,
                "to": end,
                "rows": [show(r) for r in rows],
                "total": {k: str(v) for k, v in grand.items()},
            }
        )


class LedgerStatementView(APIView):
    """GET companies/<id>/ledger-statement/?ledger=&from=&to=

    The opening balance on From, every entry to the ledger in the period with
    the other ledgers of the same entry ("Particulars") and the balance after
    it, and the closing balance."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _see_books(request)
        company = _company(request, pk)
        ledger_id = _id(request, "ledger")
        if ledger_id is None:
            raise ValidationError({"ledger": "Pick a ledger."})
        ledger = (
            Ledger.objects.filter(pk=ledger_id, company=company).select_related("group").first()
        )
        if ledger is None:
            raise NotFound("No such ledger.")
        start, end = _period(request, company)
        mine = GLEntry.objects.filter(ledger=ledger, date__lte=end)
        earlier = mine.filter(date__lt=start).aggregate(d=Sum("debit"), c=Sum("credit"))
        opening = ledger.opening_signed + (earlier["d"] or ZERO) - (earlier["c"] or ZERO)
        lines = list(mine.filter(date__gte=start))

        # The other side of each entry: the ledgers on the opposite side of the same voucher.
        keys = {(e.voucher_type, e.voucher_id) for e in lines}
        others: dict[tuple, list[GLEntry]] = defaultdict(list)
        if keys:
            types = {k[0] for k in keys}
            ids = {k[1] for k in keys}
            for o in (
                GLEntry.objects.filter(company=company, voucher_type__in=types, voucher_id__in=ids)
                .exclude(ledger=ledger)
                .select_related("ledger")
            ):
                others[(o.voucher_type, o.voucher_id, o.is_reversal)].append(o)

        balance = opening
        out = []
        total_d = total_c = ZERO
        for e in lines:
            balance += e.debit - e.credit
            total_d += e.debit
            total_c += e.credit
            side = [
                o
                for o in others.get((e.voucher_type, e.voucher_id, e.is_reversal), [])
                if (o.credit > 0) == (e.debit > 0)
            ]
            names = list(dict.fromkeys(o.ledger.name for o in side))
            out.append(
                {
                    "date": e.date,
                    "entry": entry(e.voucher_type, e.voucher_id, e.voucher_no),
                    "cancel": e.is_reversal,
                    "particulars": ", ".join(names),
                    "remarks": e.remarks,
                    "debit": str(e.debit),
                    "credit": str(e.credit),
                    "balance": str(balance),
                }
            )
        return Response(
            {
                "company_name": company.name,
                "ledger": ledger.pk,
                "ledger_name": ledger.name,
                "group_name": ledger.group.name,
                "from": start,
                "to": end,
                "opening": str(opening),
                "rows": out,
                "total_debit": str(total_d),
                "total_credit": str(total_c),
                "closing": str(balance),
            }
        )
