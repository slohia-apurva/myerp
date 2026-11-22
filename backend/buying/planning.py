"""Stock Check (Sidharth, 2026-11-21): for one branch, which items will run
short and how much to buy, from each item's Stock Planning line there.

    In Stock  what the branch holds now (all its places)
    Reserved  everything going out of the branch, submitted or still a draft:
              sales orders still to deliver, draft stock transfers out,
              materials still to issue on manufacturing orders
    Incoming  everything coming in, drafts included: purchase orders still to
              receive, manufacturing orders still to make, and stock
              transfers coming (on the road too: goods in the In Transit
              place are not In Stock), so a check run twice
              never orders the same goods twice
    Expected  In Stock - Reserved + Incoming

An item whose Expected is below its Safety Stock is short; the suggestion
refills it to Order Up To (or the safety stock when that is empty), in the
item's purchase unit, rounded up to the Minimum Order Qty (in whole steps of
it) or else to a whole unit when the unit is counted in whole numbers.

Lines whose fulfilment is Purchase are "To Buy": "Create Purchase Orders"
makes one DRAFT order per supplier. Lines whose fulfilment is Transfer are
"To Transfer" (Sidharth, 2026-11-22, preview 9b): "Create Stock Transfers"
makes one DRAFT transfer per source branch, in the item's sales unit, with no
minimum order. A person checks and submits (dispatches) each one (design
rule: drafts only). "To Make" comes with manufacturing."""

import datetime
from collections import defaultdict
from decimal import ROUND_CEILING, Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying import api as orders
from buying.models import PurchaseOrder, PurchaseOrderLine, StockCheckRun
from core.api import EDIT as MASTERS_EDIT
from core.api import Signed
from core.models import Branch, Item, ItemPlan, ItemUnit, Ledger, PriceList
from core.price_lists import find_rate
from selling.models import SalesOrder, SalesOrderLine
from selling.stock import on_hand
from stock.models import OwnUse, OwnUseLine, StockTransfer, StockTransferLine
from tenancy.context import tenant_atomic

ZERO = Decimal("0")
STEP = Decimal("0.000001")


def _factors(item_ids) -> dict[tuple[int, int], ItemUnit]:
    rows = ItemUnit.objects.filter(item_id__in=item_ids).select_related("unit")
    return {(r.item_id, r.unit_id): r for r in rows}


def _in_stock_units(rows, factors) -> dict[int, Decimal]:
    """Sum of (item, unit, qty) rows in each item's stock unit."""
    out: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for item_id, unit_id, qty in rows:
        row = factors.get((item_id, unit_id))
        out[item_id] += qty * (row.factor if row is not None and row.factor else Decimal("1"))
    return out


def reserved(branch: Branch, item_ids) -> dict[int, Decimal]:
    """Still to deliver on the branch's sales orders, draft stock transfers out
    of it, and draft own use."""
    lines = SalesOrderLine.objects.filter(
        order__branch=branch,
        order__status__in=[SalesOrder.DRAFT, *SalesOrder.OPEN],
        item_id__in=item_ids,
        closed_at__isnull=True,
    ).values_list("item_id", "unit_id", "qty", "delivered_qty")
    rows = [(i, u, max(q - d, ZERO)) for i, u, q, d in lines]
    # Draft stock transfers out of the branch (once dispatched, the goods have left).
    rows += list(
        StockTransferLine.objects.filter(
            transfer__from_branch=branch,
            transfer__status=StockTransfer.DRAFT,
            item_id__in=item_ids,
        ).values_list("item_id", "unit_id", "qty")
    )
    # Draft own use (once submitted, the goods have left).
    rows += list(
        OwnUseLine.objects.filter(
            entry__branch=branch, entry__status=OwnUse.DRAFT, item_id__in=item_ids
        ).values_list("item_id", "unit_id", "qty")
    )
    # Materials still to issue on draft and open manufacturing orders.
    from manufacturing.orders import reserved_lines

    rows += reserved_lines(branch, item_ids)
    return _in_stock_units(rows, _factors(item_ids))


def incoming(branch: Branch, item_ids) -> dict[int, Decimal]:
    """Still to receive on the branch's purchase orders, drafts included, and
    stock transfers coming to it (drafts and in transit)."""
    lines = PurchaseOrderLine.objects.filter(
        order__branch=branch,
        order__status__in=[PurchaseOrder.DRAFT, *PurchaseOrder.OPEN],
        item_id__in=item_ids,
        closed_at__isnull=True,
    ).values_list("item_id", "unit_id", "qty", "received_qty")
    rows = [(i, u, max(q - r, ZERO)) for i, u, q, r in lines]
    # Stock transfers to the branch, drafts and those on the road.
    rows += list(
        StockTransferLine.objects.filter(
            transfer__to_branch=branch,
            transfer__status__in=[StockTransfer.DRAFT, StockTransfer.IN_TRANSIT],
            item_id__in=item_ids,
        ).values_list("item_id", "unit_id", "qty")
    )
    # What draft and open manufacturing orders are still to make.
    from manufacturing.orders import incoming_lines

    rows += incoming_lines(branch, item_ids)
    return _in_stock_units(rows, _factors(item_ids))


def round_up(qty: Decimal, step: Decimal | None, whole: bool) -> Decimal:
    """Up to whole steps of the minimum order, else to a whole unit when the unit
    is counted in whole numbers."""
    if qty <= ZERO:
        return ZERO
    if step:
        return (qty / step).to_integral_value(ROUND_CEILING) * step
    if whole:
        return qty.to_integral_value(ROUND_CEILING)
    return qty.quantize(STEP, ROUND_CEILING)


def supplier_ledgers(company) -> dict[int, Ledger]:
    """The company's supplier ledgers, by party."""
    rows = Ledger.objects.filter(company=company, party_side="supplier", party__isnull=False)
    return {ledger.party_id: ledger for ledger in rows.select_related("party")}


def check(company, branch: Branch, everything: bool = False, today=None) -> list[dict]:
    """One row per item the branch buys (Stock Planning: Purchase): its figures and,
    when short (or always, with `everything`), the suggestion."""
    today = today or timezone.localdate()
    plans = list(
        ItemPlan.objects.filter(
            branch=branch, fulfilment=ItemPlan.PURCHASE, item__is_active=True
        ).select_related(
            "item__stock_unit",
            "item__purchase_unit",
            "item__item_group",
            "item__preferred_supplier",
        )
    )
    ids = [p.item_id for p in plans]
    have = on_hand(ids, branch)
    out_qty = reserved(branch, ids)
    in_qty = incoming(branch, ids)
    factors = _factors(ids)
    ledgers = supplier_ledgers(company)
    rows = []
    for p in sorted(plans, key=lambda p: p.item.name.lower()):
        item: Item = p.item
        stock = have.get(item.pk, ZERO)
        kept = out_qty.get(item.pk, ZERO)
        coming = in_qty.get(item.pk, ZERO)
        expected = stock - kept + coming
        short = expected < p.safety_qty
        if not short and not everything:
            continue
        target = p.order_up_to if p.order_up_to is not None else p.safety_qty
        need = max(target - expected, ZERO) if short else ZERO
        unit, suggested, whole = _in_purchase_unit(item, need, factors)
        ledger = ledgers.get(item.preferred_supplier_id) if item.preferred_supplier_id else None
        rate = None
        if ledger is not None and suggested > ZERO:
            rate = find_rate(ledger.party, item, unit, suggested, today, PriceList.BUYING)[0]
        lead = item.lead_time_days
        rows.append(
            {
                "item": item.pk,
                "item_name": item.name,
                "item_number": item.item_number,
                "item_group": item.item_group_id,
                "item_group_name": item.item_group.name if item.item_group_id else "",
                "stock_unit": item.stock_unit.short_name or item.stock_unit.name,
                "in_stock": _plain(stock),
                "reserved": _plain(kept),
                "incoming": _plain(coming),
                "expected": _plain(expected),
                "safety": _plain(p.safety_qty),
                "order_up_to": _plain(p.order_up_to) if p.order_up_to is not None else None,
                "short": short,
                "suggested": _plain(suggested),
                "unit": unit.pk,
                "unit_name": unit.short_name or unit.name,
                "whole_numbers": whole,
                "supplier": ledger.pk if ledger is not None else None,
                "preferred_supplier_name": item.preferred_supplier.name
                if item.preferred_supplier_id
                else "",
                # The preferred supplier has no ledger in this company yet.
                "supplier_missing": item.preferred_supplier_id is not None and ledger is None,
                "rate": _plain(rate) if rate is not None else None,
                "lead_time_days": lead,
                "by": (today + datetime.timedelta(days=lead or 0)).isoformat(),
            }
        )
    return rows


def _in_sales_unit(item: Item, need: Decimal, factors) -> tuple:
    """`need` stock units as (unit, qty, whole numbers) in the sales unit (the
    unit stock moves in), rounded up to a whole unit when it is counted so; a
    transfer has no minimum order."""
    unit_id = item.sales_unit_id or item.stock_unit_id
    unit_row = factors.get((item.pk, unit_id))
    factor = unit_row.factor if unit_row is not None and unit_row.factor else Decimal("1")
    unit = unit_row.unit if unit_row is not None else item.stock_unit
    whole = unit_row.whole_numbers if unit_row is not None else True
    return unit, round_up(need / factor, None, whole), whole, factor


def check_transfers(company, branch: Branch, everything: bool = False, today=None) -> list[dict]:
    """ "To Transfer" (Sidharth, 2026-11-22, preview 9b): one row per item the
    branch gets from another branch (Stock Planning: Transfer), with the same
    figures as To Buy, the suggestion in the item's sales unit, and what the
    source has free (its In Stock - Reserved). A source short of it is only a
    warning: the draft transfer counts as Reserved there, so the source's own
    check buys or makes more."""
    from stock.transfers import gstin

    today = today or timezone.localdate()
    plans = list(
        ItemPlan.objects.filter(
            branch=branch,
            fulfilment=ItemPlan.TRANSFER,
            transfer_from__isnull=False,
            item__is_active=True,
        ).select_related(
            "item__stock_unit", "item__sales_unit", "item__item_group", "transfer_from__company"
        )
    )
    ids = [p.item_id for p in plans]
    have = on_hand(ids, branch)
    out_qty = reserved(branch, ids)
    in_qty = incoming(branch, ids)
    factors = _factors(ids)
    free: dict[int, dict[int, Decimal]] = {}
    for source in {p.transfer_from for p in plans}:
        mine = [p.item_id for p in plans if p.transfer_from_id == source.pk]
        held, kept = on_hand(mine, source), reserved(source, mine)
        free[source.pk] = {i: held.get(i, ZERO) - kept.get(i, ZERO) for i in mine}
    rows = []
    for p in sorted(plans, key=lambda p: (p.transfer_from.name.lower(), p.item.name.lower())):
        item: Item = p.item
        stock = have.get(item.pk, ZERO)
        kept = out_qty.get(item.pk, ZERO)
        coming = in_qty.get(item.pk, ZERO)
        expected = stock - kept + coming
        short = expected < p.safety_qty
        if not short and not everything:
            continue
        target = p.order_up_to if p.order_up_to is not None else p.safety_qty
        need = max(target - expected, ZERO) if short else ZERO
        unit, suggested, whole, factor = _in_sales_unit(item, need, factors)
        source = p.transfer_from
        at_source = free[source.pk].get(item.pk, ZERO) / factor
        days = p.transfer_days or 0
        rows.append(
            {
                "item": item.pk,
                "item_name": item.name,
                "item_number": item.item_number,
                "item_group": item.item_group_id,
                "item_group_name": item.item_group.name if item.item_group_id else "",
                "stock_unit": item.stock_unit.short_name or item.stock_unit.name,
                "in_stock": _plain(stock),
                "reserved": _plain(kept),
                "incoming": _plain(coming),
                "expected": _plain(expected),
                "safety": _plain(p.safety_qty),
                "order_up_to": _plain(p.order_up_to) if p.order_up_to is not None else None,
                "short": short,
                "suggested": _plain(suggested),
                "unit": unit.pk,
                "unit_name": unit.short_name or unit.name,
                "whole_numbers": whole,
                "from_branch": source.pk,
                "from_branch_name": source.name,
                "transfer_days": p.transfer_days,
                "by": (today + datetime.timedelta(days=days)).isoformat(),
                "free_at_source": _plain(at_source.quantize(Decimal("0.001"))),
                "source_short": at_source < suggested,
                # A source with another GSTIN cannot send by transfer.
                "other_gstin": gstin(source) != gstin(branch),
            }
        )
    return rows


def make_transfers(
    company,
    branch: Branch,
    lines: list[dict],
    user,
    today=None,
    reason: str = "Made by Stock Check.",
    sales_order=None,
    run=None,
) -> list:
    """One draft stock transfer per source branch, into `branch`, for lines
    {item, unit, qty, from_branch, days}. Its bins are picked as on Save; the
    source's stores check and Dispatch it."""
    from stock.models import StockTransfer
    from stock.transfers import _save

    today = today or timezone.localdate()
    by_source: dict[int, list[dict]] = defaultdict(list)
    for line in lines:
        by_source[line["from_branch"].pk].append(line)
    made = []
    for group in by_source.values():
        source = group[0]["from_branch"]
        days = max((ln.get("days") or 0) for ln in group)
        data = {
            "from_branch": source.pk,
            "from_area": None,
            "to_branch": branch.pk,
            "to_area": None,
            "transfer_date": today,
            "expected_date": today + datetime.timedelta(days=days),
            "transporter": None,
            "vehicle_no": "",
            "eway_bill_no": "",
            "reason": reason[:200],
            "notes": "",
            "lines": [
                {"item": ln["item"].pk, "unit": ln["unit"].pk, "qty": ln["qty"]} for ln in group
            ],
        }
        t = StockTransfer(
            company=company, created_by=user, sales_order=sales_order, stock_check_run=run
        )
        try:
            _save(t, data)
        except ValidationError as exc:
            raise ValidationError({"lines": [f"From {source.name}: {_said(exc.detail)}"]}) from exc
        made.append(t)
    return made


def _in_purchase_unit(item: Item, need: Decimal, factors) -> tuple:
    """`need` stock units as (unit, qty, whole numbers) in the purchase unit,
    rounded up to the minimum order."""
    unit_id = item.purchase_unit_id or item.stock_unit_id
    unit_row = factors.get((item.pk, unit_id))
    factor = unit_row.factor if unit_row is not None and unit_row.factor else Decimal("1")
    unit = unit_row.unit if unit_row is not None else item.stock_unit
    step = item.min_order_qty / factor if item.min_order_qty else None
    whole = unit_row.whole_numbers if unit_row is not None else True
    return unit, round_up(need / factor, step, whole), whole


def _plain(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value.quantize(STEP).normalize(), "f")
    return "0" if text in ("-0", "") else text


def make_orders(
    company,
    branch: Branch,
    lines: list[dict],
    user,
    today=None,
    notes: str = "Made by Stock Check.",
    sales_order=None,
    run=None,
) -> list:
    """One draft purchase order per supplier for the ticked lines."""
    today = today or timezone.localdate()
    by_supplier: dict[int, list[dict]] = defaultdict(list)
    for line in lines:
        by_supplier[line["supplier"].pk].append(line)
    made = []
    for group in by_supplier.values():
        ledger = group[0]["supplier"]
        if ledger.company_id != company.pk or ledger.party_side != "supplier":
            raise ValidationError({"lines": ["Pick a supplier of this company."]})
        lead = max((ln["item"].lead_time_days or 0) for ln in group)
        purchaser = ledger.salesman if ledger.salesman_id else None
        body = {
            "supplier": ledger.pk,
            "branch": branch.pk,
            "order_date": today.isoformat(),
            "expected_date": (today + datetime.timedelta(days=lead)).isoformat(),
            "credit_term": ledger.party.credit_term_id,
            "transporter": ledger.preferred_transporter_id,
            "purchaser": purchaser.pk
            if purchaser is not None and purchaser.is_active and purchaser.is_purchaser
            else None,
            "notes": notes,
            "lines": [],
        }
        for ln in group:
            item, unit = ln["item"], ln["unit"]
            rate = find_rate(ledger.party, item, unit, ln["qty"], today, PriceList.BUYING)[0]
            body["lines"].append(
                {
                    "item": item.pk,
                    "unit": unit.pk,
                    "qty": str(ln["qty"]),
                    "rate": str(rate if rate is not None else ZERO),
                }
            )
        serializer = orders.OrderSerializer(data=body)
        serializer.is_valid(raise_exception=True)
        order = PurchaseOrder(
            company=company, created_by=user, sales_order=sales_order, stock_check_run=run
        )
        try:
            orders._save_order(order, dict(serializer.validated_data))
        except ValidationError as exc:
            raise ValidationError({"lines": [f"{ledger.name}: {_said(exc.detail)}"]}) from exc
        made.append(order)
    return made


def for_sales_order(so, user, today=None) -> list[dict]:
    """Sales order Submit (Sidharth, 2026-11-21): the Stock Check for the order's
    stock items at its branch (the order itself now counts in Reserved). An item
    the branch buys gets a draft purchase order, one per supplier, linked to the
    order: refilled to Order Up To when it has a Stock Planning line there, or
    for the shortage alone when it only has Main Fulfilment Purchase. Items to
    make are noted for now; an item the branch gets by transfer gets a draft
    stock transfer from its source branch, one per source (preview 9b). A
    supplier or source whose draft cannot be made is noted too; Submit never
    fails because of this. The result is kept on the order as `shortages`."""
    today = today or timezone.localdate()
    branch = so.branch
    items = {
        ln.item_id: ln.item
        for ln in so.lines.select_related("item__stock_unit", "item__preferred_supplier")
        if ln.item.maintain_stock
    }
    ids = list(items)
    plans = {
        p.item_id: p
        for p in ItemPlan.objects.filter(branch=branch, item_id__in=ids).select_related(
            "transfer_from__company"
        )
    }
    have = on_hand(ids, branch)
    out_qty = reserved(branch, ids)
    in_qty = incoming(branch, ids)
    factors = _factors(ids)
    ledgers = supplier_ledgers(so.company)
    notes: list[dict] = []
    to_buy: dict[int, list[dict]] = defaultdict(list)
    to_move: list[dict] = []
    for item in sorted(items.values(), key=lambda i: i.name.lower()):
        plan = plans.get(item.pk)
        how = plan.fulfilment if plan is not None else item.default_request_type
        expected = have.get(item.pk, ZERO) - out_qty.get(item.pk, ZERO) + in_qty.get(item.pk, ZERO)
        floor = plan.safety_qty if plan is not None else ZERO
        note = {
            "item": item.pk,
            "item_name": item.name,
            "stock_unit": item.stock_unit.short_name or item.stock_unit.name,
            "expected": _plain(expected),
            "short": "0",
            "safety": _plain(plan.safety_qty) if plan is not None else "0",
            "action": "ok",
            "order": None,
            "message": "",
        }
        notes.append(note)
        if expected >= floor or how == ItemPlan.CUSTOMER_PROVIDED:
            continue
        target = floor
        if plan is not None and plan.order_up_to is not None:
            target = plan.order_up_to
        need = target - expected
        note["short"] = _plain(need)
        if how == ItemPlan.MANUFACTURE:
            note["action"] = "make"
        elif how == ItemPlan.TRANSFER:
            note["action"] = "transfer"
            if plan is not None and plan.transfer_from_id:
                unit, qty, _whole, _f = _in_sales_unit(item, need, factors)
                note.update(qty=_plain(qty), unit_name=unit.short_name or unit.name)
                note["from_name"] = plan.transfer_from.name
                to_move.append(
                    {
                        "item": item,
                        "unit": unit,
                        "qty": qty,
                        "from_branch": plan.transfer_from,
                        "days": plan.transfer_days,
                        "note": note,
                    }
                )
            else:
                note["message"] = "No branch to transfer from on its Stock Planning line."
        elif how != ItemPlan.PURCHASE:
            note["action"] = "unplanned"
        else:
            ledger = ledgers.get(item.preferred_supplier_id) if item.preferred_supplier_id else None
            unit, qty, _whole = _in_purchase_unit(item, need, factors)
            note.update(qty=_plain(qty), unit_name=unit.short_name or unit.name)
            if ledger is None or not ledger.is_active:
                note["action"] = "no_supplier"
                note["message"] = (
                    f"{item.preferred_supplier.name} has no supplier ledger in this company."
                    if item.preferred_supplier_id
                    else "The item has no Preferred Supplier."
                )
            else:
                note["action"] = "po"
                to_buy[ledger.pk].append(
                    {"item": item, "unit": unit, "qty": qty, "supplier": ledger, "note": note}
                )
    for group in to_buy.values():
        try:
            with tenant_atomic():
                [order] = make_orders(
                    so.company,
                    branch,
                    group,
                    user,
                    today,
                    notes=f"Made on Submit of Sales Order {so.number} for its shortages.",
                    sales_order=so,
                )
        except ValidationError as exc:
            for ln in group:
                ln["note"].update(action="failed", message=_said(exc.detail))
            continue
        for ln in group:
            ln["note"]["order"] = order.pk
            ln["note"]["supplier_name"] = order.supplier.name
            ln["note"]["by"] = order.expected_date.isoformat() if order.expected_date else ""
    by_source: dict[int, list[dict]] = defaultdict(list)
    for ln in to_move:
        by_source[ln["from_branch"].pk].append(ln)
    for group in by_source.values():
        try:
            with tenant_atomic():
                [moved] = make_transfers(
                    so.company,
                    branch,
                    group,
                    user,
                    today,
                    reason=f"Made on Submit of Sales Order {so.number} for its shortages.",
                    sales_order=so,
                )
        except ValidationError as exc:
            for ln in group:
                ln["note"].update(action="failed", message=_said(exc.detail))
            continue
        for ln in group:
            ln["note"].update(
                action="st",
                transfer=moved.pk,
                by=moved.expected_date.isoformat() if moved.expected_date else "",
            )
    so.shortages = notes
    so.save(update_fields=["shortages"])
    return notes


def daily_run(company, now=None) -> list[StockCheckRun]:
    """The daily Stock Check (Sidharth, 2026-11-21): for each stock branch of the
    company with Stock Planning lines to buy, what "Create Purchase Orders" does
    for every short item that has a supplier: one draft per supplier. Items with
    no supplier, and suppliers whose draft cannot be made, are listed in the
    bell notice to the Purchase people. Drafts count as Incoming, so a draft
    nobody has submitted is not ordered again the next morning."""
    from core.notifications import notify, people_with_roles

    today = timezone.localdate(now)
    branches = Branch.objects.filter(
        company=company,
        is_active=True,
        no_stock=False,
        pk__in=ItemPlan.objects.filter(
            fulfilment__in=[ItemPlan.PURCHASE, ItemPlan.TRANSFER]
        ).values("branch_id"),
    ).order_by("name")
    runs = []
    for branch in branches:
        rows = check(company, branch, today=today)
        moves = check_transfers(company, branch, today=today)
        run = StockCheckRun.objects.create(
            company=company, branch=branch, daily=True, short_count=len(rows) + len(moves)
        )
        runs.append(run)
        if not rows and not moves:
            continue
        items = Item.objects.in_bulk([r["item"] for r in rows])
        units = {
            u.unit_id: u.unit
            for u in ItemUnit.objects.filter(
                item_id__in=items, unit_id__in=[r["unit"] for r in rows]
            ).select_related("unit")
        }
        ledgers = Ledger.objects.in_bulk([r["supplier"] for r in rows if r["supplier"]])
        groups: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            ledger = ledgers.get(r["supplier"]) if r["supplier"] else None
            if ledger is None or not ledger.is_active:
                run.missing.append(r["item_name"])
            elif Decimal(r["suggested"]) > ZERO:
                groups[ledger.pk].append(
                    {
                        "item": items[r["item"]],
                        "unit": units.get(r["unit"]) or items[r["item"]].stock_unit,
                        "qty": Decimal(r["suggested"]),
                        "supplier": ledger,
                    }
                )
        made = []
        for group in groups.values():
            try:
                with tenant_atomic():
                    made += make_orders(
                        company,
                        branch,
                        group,
                        None,
                        today,
                        notes="Made by the daily Stock Check.",
                        run=run,
                    )
            except ValidationError as exc:
                run.failed.append(_said(exc.detail))
        sent = _daily_transfers(company, branch, moves, run, today)
        run.order_count = len(made) + len(sent)
        run.item_count = sum(o.lines.count() for o in made) + sum(t.lines.count() for t in sent)
        run.save(update_fields=["order_count", "item_count", "missing", "failed"])
        # One part per paragraph, one line per order or item (Sidharth, 2026-11-22).
        parts = [f"{_count(len(rows) + len(moves), 'item')} below safety stock."]
        if made:
            parts.append(
                "Draft Purchase Orders made:\n"
                + "\n".join(
                    f"• {o.supplier.name}: {_count(o.lines.count(), 'item')}, "
                    f"by {o.expected_date:%d/%m/%Y}"
                    for o in made
                )
            )
        if sent:
            parts.append(
                "Draft Stock Transfers made:\n"
                + "\n".join(
                    f"• From {t.from_branch.name}: {_count(t.lines.count(), 'item')}, "
                    f"by {t.expected_date:%d/%m/%Y}"
                    for t in sent
                )
            )
        if run.missing:
            parts.append(
                "No Preferred Supplier, not ordered:\n"
                + "\n".join(f"• {name}" for name in run.missing)
            )
        if run.failed:
            parts.append("Not made:\n" + "\n".join(f"• {text}" for text in run.failed))
        notify(
            people_with_roles(company, "purchase", "storekeeper", "owner"),
            company,
            f"Daily Stock Check, {branch.name}",
            "\n\n".join(parts),
            f"#/companies/{company.pk}/stock-check?branch={branch.pk}",
        )
    return runs


def _daily_transfers(company, branch: Branch, rows: list[dict], run, today) -> list:
    """The To Transfer part of the daily run: one draft per source branch."""
    items = Item.objects.in_bulk([r["item"] for r in rows])
    units = {
        (u.item_id, u.unit_id): u.unit
        for u in ItemUnit.objects.filter(item_id__in=items).select_related("unit")
    }
    sources = Branch.objects.in_bulk([r["from_branch"] for r in rows])
    lines = []
    for r in rows:
        if r["other_gstin"]:
            run.failed.append(f"{r['item_name']}: {r['from_branch_name']} has another GSTIN.")
        elif Decimal(r["suggested"]) > ZERO:
            lines.append(
                {
                    "item": items[r["item"]],
                    "unit": units.get((r["item"], r["unit"])) or items[r["item"]].stock_unit,
                    "qty": Decimal(r["suggested"]),
                    "from_branch": sources[r["from_branch"]],
                    "days": r["transfer_days"],
                }
            )
    made = []
    by_source: dict[int, list[dict]] = defaultdict(list)
    for ln in lines:
        by_source[ln["from_branch"].pk].append(ln)
    for group in by_source.values():
        try:
            with tenant_atomic():
                made += make_transfers(
                    company, branch, group, None, today,
                    reason="Made by the daily Stock Check.", run=run,
                )  # fmt: skip
        except ValidationError as exc:
            run.failed.append(_said(exc.detail))
    return made


def due(company, now=None) -> bool:
    """The daily run is on, its hour has come, and it has not run today."""
    now = timezone.localtime(now)
    if not company.daily_stock_check or now.hour < company.daily_stock_check_hour:
        return False
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return not StockCheckRun.objects.filter(
        company=company, daily=True, made_at__gte=start
    ).exists()


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _said(detail) -> str:
    if isinstance(detail, dict):
        return " ".join(_said(v) for v in detail.values())
    if isinstance(detail, list):
        return " ".join(_said(v) for v in detail)
    return str(detail)


def _branch(company, value) -> Branch:
    branch = Branch.objects.filter(
        pk=value if str(value).isdigit() else 0, company=company, no_stock=False
    ).first()
    if branch is None:
        raise ValidationError({"branch": ["Pick a branch of this company that keeps stock."]})
    return branch


class StockCheckView(APIView):
    """GET ?branch=ID&show=short|all: the To Buy rows of the branch, and the
    company's suppliers for the line pickers."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        orders._check(request, orders.VIEW)
        company = orders._company(request, pk)
        branch = _branch(company, request.query_params.get("branch", ""))
        everything = request.query_params.get("show") == "all"
        rows = check(company, branch, everything=everything)
        moves = check_transfers(company, branch, everything=everything)
        suppliers = Ledger.objects.filter(
            Q(is_active=True) | Q(pk__in=[r["supplier"] for r in rows if r["supplier"]]),
            company=company,
            party_side="supplier",
            party__isnull=False,
        ).order_by("name")
        return Response(
            {
                "branch": branch.pk,
                "checked_at": timezone.localtime().isoformat(),
                "daily": _daily_out(request, company),
                "runs": [_run_out(r) for r in StockCheckRun.objects.filter(branch=branch)[:5]],
                "drafts": [
                    _draft_out(o)
                    for o in PurchaseOrder.objects.filter(
                        branch=branch, status=PurchaseOrder.DRAFT, stock_check_run__isnull=False
                    )
                    .select_related("supplier", "stock_check_run__made_by")
                    .prefetch_related("lines")
                    .order_by("-id")
                ],
                "rows": rows,
                "transfers": moves,
                "transfer_drafts": _transfer_drafts(branch),
                "may_transfer": may_transfer(request.user),
                "suppliers": [{"id": s.pk, "name": s.name} for s in suppliers],
            }
        )


def may_transfer(user) -> bool:
    return user.can("stock.create") or user.can("purchase.create")


def _transfer_drafts(branch: Branch) -> list[dict]:
    from stock.models import StockTransfer

    rows = (
        StockTransfer.objects.filter(
            to_branch=branch, status=StockTransfer.DRAFT, stock_check_run__isnull=False
        )
        .select_related("from_branch", "stock_check_run__made_by")
        .prefetch_related("lines")
        .order_by("-id")
    )
    return [
        {
            "id": t.pk,
            "made_at": t.stock_check_run.made_at,
            "daily": t.stock_check_run.daily,
            "made_by_name": t.stock_check_run.made_by.display_name
            if t.stock_check_run.made_by_id
            else "",
            "from_branch_name": t.from_branch.name,
            "item_count": len(t.lines.all()),
            "expected_date": t.expected_date,
        }
        for t in rows
    ]


def _daily_out(request, company) -> dict:
    return {
        "on": company.daily_stock_check,
        "hour": company.daily_stock_check_hour,
        "can_change": request.user.can(MASTERS_EDIT),
    }


def _run_out(r: StockCheckRun) -> dict:
    return {
        "id": r.pk,
        "made_at": r.made_at,
        "daily": r.daily,
        "made_by_name": r.made_by.display_name if r.made_by_id else "",
        "short_count": r.short_count,
        "order_count": r.order_count,
        "missing": r.missing,
        "failed": r.failed,
    }


def _draft_out(o: PurchaseOrder) -> dict:
    run = o.stock_check_run
    return {
        "id": o.pk,
        "made_at": run.made_at,
        "daily": run.daily,
        "made_by_name": run.made_by.display_name if run.made_by_id else "",
        "supplier_name": o.supplier.name,
        "item_count": len(o.lines.all()),
        "expected_date": o.expected_date,
        "total": str(o.total),
    }


class _Daily(serializers.Serializer):
    on = serializers.BooleanField()
    hour = serializers.IntegerField(min_value=0, max_value=23)


class StockCheckDailyView(APIView):
    """PUT {on, hour}: the company's daily Stock Check (needs the right to change
    masters)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def put(self, request, pk: int):
        orders._check(request, orders.VIEW)
        if not request.user.can(MASTERS_EDIT):
            raise PermissionDenied("Only someone who may change masters can set the daily run.")
        company = orders._company(request, pk)
        serializer = _Daily(data=request.data)
        serializer.is_valid(raise_exception=True)
        company.daily_stock_check = serializer.validated_data["on"]
        company.daily_stock_check_hour = serializer.validated_data["hour"]
        company.save(update_fields=["daily_stock_check", "daily_stock_check_hour"])
        return Response(_daily_out(request, company))


class _Line(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    unit = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    supplier = serializers.PrimaryKeyRelatedField(queryset=Ledger.objects.all())


class _Make(serializers.Serializer):
    branch = serializers.IntegerField()
    lines = _Line(many=True, allow_empty=False)


class StockCheckOrdersView(APIView):
    """POST {branch, lines: [{item, unit, qty, supplier}]}: one draft purchase
    order per supplier."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        orders._check(request, orders.CREATE)
        company = orders._company(request, pk)
        serializer = _Make(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = _branch(company, serializer.validated_data["branch"])
        lines = []
        for ln in serializer.validated_data["lines"]:
            row = ItemUnit.objects.filter(item=ln["item"], unit_id=ln["unit"]).first()
            if row is None:
                raise ValidationError({"lines": [f"Pick one of the units of {ln['item'].name}."]})
            lines.append({**ln, "unit": row.unit})
        run = StockCheckRun.objects.create(
            company=company, branch=branch, made_by=request.user, short_count=len(lines)
        )
        made = make_orders(company, branch, lines, request.user, run=run)
        run.order_count, run.item_count = len(made), len(lines)
        run.save(update_fields=["order_count", "item_count"])
        return Response(
            [
                {"id": o.pk, "supplier_name": o.supplier.name, "lines": o.lines.count()}
                for o in made
            ],
            status=status.HTTP_201_CREATED,
        )


class _MoveLine(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    unit = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    from_branch = serializers.IntegerField()


class _Move(serializers.Serializer):
    branch = serializers.IntegerField()
    lines = _MoveLine(many=True, allow_empty=False)


class StockCheckTransfersView(APIView):
    """POST {branch, lines: [{item, unit, qty, from_branch}]}: one draft stock
    transfer per source branch, into the branch (preview 9b)."""

    permission_classes = [Signed]

    @tenant_atomic()
    def post(self, request, pk: int):
        orders._check(request, orders.VIEW)
        if not may_transfer(request.user):
            raise PermissionDenied("Your role may not make stock transfers.")
        company = orders._company(request, pk)
        serializer = _Move(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = _branch(company, serializer.validated_data["branch"])
        plans = {
            p.item_id: p
            for p in ItemPlan.objects.filter(branch=branch, fulfilment=ItemPlan.TRANSFER)
        }
        lines = []
        for ln in serializer.validated_data["lines"]:
            row = ItemUnit.objects.filter(item=ln["item"], unit_id=ln["unit"]).first()
            if row is None:
                raise ValidationError({"lines": [f"Pick one of the units of {ln['item'].name}."]})
            source = _branch(company, ln["from_branch"])
            plan = plans.get(ln["item"].pk)
            lines.append(
                {
                    **ln,
                    "unit": row.unit,
                    "from_branch": source,
                    "days": plan.transfer_days if plan is not None else None,
                }
            )
        run = StockCheckRun.objects.create(
            company=company, branch=branch, made_by=request.user, short_count=len(lines)
        )
        made = make_transfers(company, branch, lines, request.user, run=run)
        run.order_count, run.item_count = len(made), len(lines)
        run.save(update_fields=["order_count", "item_count"])
        return Response(
            [
                {"id": t.pk, "from_branch_name": t.from_branch.name, "lines": t.lines.count()}
                for t in made
            ],
            status=status.HTTP_201_CREATED,
        )
