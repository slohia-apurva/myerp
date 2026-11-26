"""Batch Trace: where one batch came from, where it is now and where it went,
read straight from the stock ledger (design rule 1), for recall and audits
under FSSC / ISO (Sidharth, 2026-11-25, preview
mockups/batch-trace/1-batch-trace-preview.png). The retention sample labels
carry a QR code that opens it (#/batches/<id>/trace), so that path stays.

Every stock move carrying the batch is grouped by the entry that made it. An
entry whose moves add up to nothing (a cancelled one, a move between bins) is
left out of the three lists and shows only under "Every Move". Each kind of
entry has a describer that names its party, orders and bills; a kind with none
(one built later, such as the Material Issue or Production Entry) still shows,
with its own name and a link when `reports.PAGES` knows its screen.

Batches are shared by the group, so the trace covers every company the person
may see."""

from collections import defaultdict
from decimal import Decimal

from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import Signed
from core.companies import visible_companies
from core.models import Batch, Ledger, Package, Party, PartyContact
from posting.models import StockMove
from posting.reports import _see_stock, entry

ZERO = Decimal("0")

# Entries that bring a batch in from outside: our purchase, a customer's own
# goods, and (later) what production makes.
SOURCES = {"goods_receipt", "stock_receipt", "production_entry"}
# Goods coming back from a customer.
BACK = {"credit_note"}
# Our own goods moving between our branches: neither in nor out.
TRANSFERS = {"stock_transfer", "stock_transfer_in", "stock_transfer_receipt"}
# Out to a customer: counted in "Customers Who Got It".
TO_CUSTOMER = {"delivery_note", "stock_delivery"}


def _num(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _party(ledger: Ledger | None, side: str, contacts: dict[int, PartyContact]) -> dict | None:
    """A customer or supplier as the trace shows it: name, number and main contact."""
    if ledger is None:
        return None
    p: Party | None = ledger.party
    if p is None:
        return {"id": None, "name": ledger.name, "number": "", "contact": ""}
    c = contacts.get(p.pk)
    contact = " · ".join(x for x in (c.name, c.phone) if x) if c else ""
    number = (p.customer_number if side == "customer" else p.vendor_number) or (
        p.customer_number or p.vendor_number
    )
    return {"id": p.pk, "name": p.name, "number": number, "contact": contact}


def _ref(kind: str, obj, company: int) -> dict:
    return {**entry(kind, obj.pk, obj.number), "company": company}


# --- What each kind of entry says about itself --------------------------------
# Each takes the ids of its entries and returns {id: {...}} with any of:
# party, side, orders, bills, note, to (words when there is no party).


def _goods_receipts(ids):
    from buying.models import GoodsReceipt, PurchaseInvoice

    out = {}
    rows = GoodsReceipt.objects.filter(pk__in=ids).select_related("supplier__party")
    for r in rows.prefetch_related("orders", "invoices"):
        bills = [i for i in r.invoices.all() if i.status == PurchaseInvoice.SUBMITTED]
        out[r.pk] = {
            "ledger": r.supplier,
            "side": "supplier",
            "orders": [_ref("purchase_order", o, r.company_id) for o in r.orders.all()],
            "bills": [
                {**_ref("purchase_invoice", b, r.company_id), "extra": b.bill_no} for b in bills
            ],
            "note": "QC " + r.get_qc_cartons_display() if r.qc_cartons else "",
        }
    return out


def _purchase_returns(ids):
    from buying.models import PurchaseReturn

    out = {}
    rows = PurchaseReturn.objects.filter(pk__in=ids).select_related("supplier__party", "receipt")
    for r in rows:
        out[r.pk] = {
            "ledger": r.supplier,
            "side": "supplier",
            "orders": [_ref("goods_receipt", r.receipt, r.company_id)],
            "bills": [],
            "note": "",
        }
    return out


def _delivery_notes(ids):
    from selling.models import DeliveryNote, SalesInvoice

    out = {}
    rows = DeliveryNote.objects.filter(pk__in=ids).select_related(
        "customer__party", "order", "pick_list"
    )
    for n in rows.prefetch_related("invoices"):
        bills = [i for i in n.invoices.all() if i.status == SalesInvoice.SUBMITTED]
        out[n.pk] = {
            "ledger": n.customer,
            "side": "customer",
            "orders": [_ref("sales_order", n.order, n.company_id)],
            "bills": [_ref("sales_invoice", b, n.company_id) for b in bills],
            "note": f"Pick List {n.pick_list.number}" if n.pick_list_id else "",
        }
    return out


def _credit_notes(ids):
    from selling.models import CreditNote

    out = {}
    rows = CreditNote.objects.filter(pk__in=ids).select_related("customer__party", "invoice")
    for n in rows:
        out[n.pk] = {
            "ledger": n.customer,
            "side": "customer",
            "orders": [],
            "bills": [_ref("sales_invoice", n.invoice, n.company_id)],
            "note": "Sales return",
        }
    return out


def _customer_stock(ids):
    from stock.models import CustomerStock

    out = {}
    for e in CustomerStock.objects.filter(pk__in=ids).select_related("customer__party"):
        note = f"Challan {e.challan_no}" if e.challan_no else ""
        out[e.pk] = {
            "ledger": e.customer,
            "side": "customer",
            "orders": [],
            "bills": [],
            "note": " · ".join(x for x in ("Customer's own goods", note, e.reason) if x),
        }
    return out


def _own_use(ids):
    from stock.models import OwnUse

    return {
        e.pk: {"to": "Own use", "orders": [], "bills": [], "note": e.reason}
        for e in OwnUse.objects.filter(pk__in=ids)
    }


def _transfers(ids):
    from stock.models import StockTransfer

    out = {}
    for t in StockTransfer.objects.filter(pk__in=ids).select_related("from_branch", "to_branch"):
        out[t.pk] = {
            "to": f"{t.from_branch.name} → {t.to_branch.name}",
            "orders": [],
            "bills": [],
            "note": t.reason,
        }
    return out


DESCRIBE = {
    "goods_receipt": _goods_receipts,
    "purchase_return": _purchase_returns,
    "delivery_note": _delivery_notes,
    "credit_note": _credit_notes,
    "stock_receipt": _customer_stock,
    "stock_delivery": _customer_stock,
    "own_use": _own_use,
    "stock_transfer": _transfers,
}


def _ranges(numbers: list[str]) -> str:
    """PK-000120, PK-000121, PK-000122 -> "PK-000120 to PK-000122 (3)"."""
    if not numbers:
        return ""
    numbers = sorted(numbers)
    runs: list[list[str]] = []
    for n in numbers:
        if runs:
            last = runs[-1][-1]
            try:
                follows = (
                    last.rsplit("-", 1)[0] == n.rsplit("-", 1)[0]
                    and int(n.rsplit("-", 1)[1]) == int(last.rsplit("-", 1)[1]) + 1
                )
            except (IndexError, ValueError):
                follows = False
            if follows:
                runs[-1].append(n)
                continue
        runs.append([n])
    text = ", ".join(r[0] if len(r) == 1 else f"{r[0]} to {r[-1]}" for r in runs)
    return f"{text} ({len(numbers)})"


def trace(batch: Batch, companies) -> dict:
    moves = list(
        StockMove.objects.filter(batch=batch, company__in=companies)
        .select_related("company", "branch", "location__parent", "owner")
        .order_by("date", "id")
    )

    # One group per entry: its net quantity, first date, company and branch.
    groups: dict[tuple, dict] = {}
    for m in moves:
        kind = "stock_transfer" if m.voucher_type in TRANSFERS else m.voucher_type
        key = (kind, m.voucher_id)
        g = groups.setdefault(
            key,
            {
                "kind": kind,
                "id": m.voucher_id,
                "number": m.voucher_no,
                "company": m.company,
                "branch": m.branch,
                "date": m.date,
                "net": ZERO,
                "out": ZERO,  # for a transfer: what left the From branch
                "owner": m.owner,
                "first": m.pk,
            },
        )
        g["net"] += m.qty
        if m.voucher_type == "stock_transfer":
            g["out"] -= m.qty
        if not m.is_reversal and m.date < g["date"]:
            g["date"] = m.date

    by_kind: dict[str, list[int]] = defaultdict(list)
    for kind, vid in groups:
        by_kind[kind].append(vid)
    info: dict[tuple, dict] = {}
    for kind, ids in by_kind.items():
        if kind in DESCRIBE:
            for vid, d in DESCRIBE[kind](ids).items():
                info[(kind, vid)] = d

    ledgers = [d["ledger"] for d in info.values() if d.get("ledger")]
    party_ids = {lg.party_id for lg in ledgers if lg.party_id}
    contacts: dict[int, PartyContact] = {}
    for c in PartyContact.objects.filter(party_id__in=party_ids).order_by("-is_primary", "id"):
        contacts.setdefault(c.party_id, c)

    unit = batch.item.stock_unit.short_name if batch.item.stock_unit_id else ""
    came, went = [], []
    customers: dict = {}
    received = sent = back = moved = ZERO
    for key, g in sorted(groups.items(), key=lambda kv: (kv[1]["date"], kv[1]["first"])):
        kind = g["kind"]
        d = info.get(key, {})
        party = _party(d.get("ledger"), d.get("side", ""), contacts)
        row = {
            "date": g["date"],
            "entry": {**entry(kind, g["id"], g["number"]), "company": g["company"].pk},
            "company_name": g["company"].name,
            "branch_name": g["branch"].name,
            "party": party,
            "to": d.get("to", ""),
            "orders": d.get("orders", []),
            "bills": d.get("bills", []),
            "note": d.get("note", ""),
            "customer_goods": g["owner"] is not None,
        }
        if kind == "stock_transfer":
            if g["out"] > 0:
                moved += g["out"]
                went.append({**row, "qty": _num(g["out"]), "moved": True, "back": ""})
            continue
        if g["net"] == 0:
            continue  # cancelled, or only moved between bins
        if kind in SOURCES or (g["net"] > 0 and kind not in BACK):
            received += g["net"]
            came.append({**row, "qty": _num(g["net"])})
            continue
        if kind in BACK:
            back += g["net"]
            went.append({**row, "qty": "", "moved": False, "back": _num(g["net"])})
        else:
            sent -= g["net"]
            went.append({**row, "qty": _num(-g["net"]), "moved": False, "back": ""})
        if party and (kind in TO_CUSTOMER or kind in BACK):
            c = customers.setdefault(
                party["id"] or party["name"], {**party, "qty": ZERO, "entries": 0}
            )
            c["qty"] -= g["net"]
            c["entries"] += 1

    # Where it is now: each place with stock, its bags and what is held there.
    places: dict[tuple, dict] = {}
    for m in moves:
        k = (m.location_id, m.owner_id)
        p = places.setdefault(
            k,
            {
                "location": m.location,
                "company": m.company,
                "branch": m.branch,
                "owner": m.owner,
                "qty": ZERO,
            },
        )
        p["qty"] += m.qty
    bags: dict[int, list[str]] = defaultdict(list)
    for k in Package.objects.filter(
        batch=batch,
        company__in=companies,
        status__in=(Package.IN_STOCK, Package.PART_USED),
    ).only("number", "location_id"):
        bags[k.location_id].append(k.number)
    held = _held(batch, companies)
    now, in_stock, held_total = [], ZERO, ZERO
    for (loc_id, _owner), p in sorted(
        places.items(),
        key=lambda kv: (kv[1]["company"].name, kv[1]["branch"].name, str(kv[1]["location"])),
    ):
        if p["qty"] == 0:
            continue
        in_stock += p["qty"]
        here = held.get(loc_id, [])
        held_total += sum((h["q"] for h in here), ZERO)
        now.append(
            {
                "company_name": p["company"].name,
                "branch_name": p["branch"].name,
                "location": loc_id,
                "location_name": str(p["location"]),
                "owner_name": p["owner"].name if p["owner"] else "",
                "bags": _ranges(bags.get(loc_id, [])),
                "qty": _num(p["qty"]),
                "held": [{**h["entry"], "qty": _num(h["q"])} for h in here],
            }
        )

    # Every move, with the running balance.
    running = ZERO
    every = []
    for m in moves:
        running += m.qty
        every.append(
            {
                "date": m.date,
                "entry": {
                    **entry(m.voucher_type, m.voucher_id, m.voucher_no),
                    "company": m.company_id,
                },
                "reversal": m.is_reversal,
                "company_name": m.company.name,
                "branch_name": m.branch.name,
                "location_name": str(m.location),
                "qty": _num(m.qty),
                "balance": _num(running),
            }
        )

    item = batch.item
    return {
        "batch": {
            "id": batch.pk,
            "number": batch.number,
            "supplier_batch_no": batch.supplier_batch_no,
            "mfg_date": batch.mfg_date,
            "expiry_date": batch.expiry_date,
            "status": batch.status,
            "status_label": batch.get_status_display(),
            "notes": batch.notes,
            "is_active": batch.is_active,
            "item": item.pk,
            "item_name": item.name,
            "item_number": item.item_number,
        },
        "unit": unit,
        "companies": len({m.company_id for m in moves}),
        "came_from": came,
        "now": now,
        "went": went,
        "customers": [
            {**c, "qty": _num(c["qty"])}
            for c in sorted(customers.values(), key=lambda c: (-c["qty"], c["name"]))
        ],
        "moves": every,
        "balance": {
            "received": _num(received),
            "sent": _num(sent),
            "back": _num(back),
            "moved": _num(moved),
            "in_stock": _num(in_stock),
            "held": _num(held_total),
        },
    }


def _held(batch: Batch, companies) -> dict[int, list[dict]]:
    """Stock of the batch kept aside, by place: open pick lists and open
    manufacturing orders that picked it and have not taken it yet."""
    from manufacturing.models import ManufacturingOrder, ManufacturingOrderPick
    from selling.models import PickList, PickListLine

    out: dict[int, dict[tuple, dict]] = defaultdict(dict)
    lines = PickListLine.objects.filter(
        batch=batch, pick_list__status__in=PickList.HOLDING, pick_list__company__in=companies
    ).select_related("pick_list")
    for ln in lines:
        p = ln.pick_list
        key = ("pick_list", p.pk)
        h = out[ln.location_id].setdefault(
            key,
            {"entry": {**entry("pick_list", p.pk, p.number), "company": p.company_id}, "q": ZERO},
        )
        h["q"] += ln.qty
    picks = ManufacturingOrderPick.objects.filter(
        batch=batch, order__status__in=ManufacturingOrder.OPEN, order__company__in=companies
    ).select_related("order")
    for pk in picks:
        o = pk.order
        key = ("manufacturing_order", o.pk)
        h = out[pk.location_id].setdefault(
            key,
            {
                "entry": {**entry("manufacturing_order", o.pk, o.number), "company": o.company_id},
                "q": ZERO,
            },
        )
        h["q"] += pk.qty
    return {loc: list(rows.values()) for loc, rows in out.items()}


class BatchTraceView(APIView):
    """GET batches/<id>/trace/ -> the whole trace of one batch."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _see_stock(request)
        batch = Batch.objects.select_related("item__stock_unit").filter(pk=pk).first()
        if batch is None:
            raise NotFound("No such batch.")
        return Response(trace(batch, visible_companies(request.user)))
