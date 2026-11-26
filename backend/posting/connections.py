"""Connections: on every entry's view, the entries it came from, the ones made
from it, and the returns, notes and adjustments against it, grouped, each with
its number, date and status (Sidharth, 2026-11-26, previews
mockups/connections/1 and 2, approved "looks good").

One request per view: GET v1/companies/<company>/connections/<kind>/<id>/. The
answer names the chain the entry sits in, then the groups. A kind the person's
role may not see is left out. Entries two steps away are shown too (the invoice
made from an order's delivery note), so the whole chain is visible from any
entry in it. Payments and receipts are not built yet: they show as "later".

Everything is read inside the one company the view is for."""

from django.db.models import Q
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import Signed, _company
from posting.reports import NAMES, PAGES
from selling.hold import rupees

# Who may see each kind (any one of the codes will do), as the entry's own screen.
SEE = {
    "purchase_order": ("purchase.view",),
    "goods_receipt": ("purchase.view", "stock.view"),
    "purchase_invoice": ("purchase.view",),
    "supplementary_bill": ("purchase.view",),
    "purchase_return": ("purchase.view", "stock.view"),
    "debit_note": ("purchase.view",),
    "tds_adjustment": ("accounts.view",),
    "sales_order": ("sales.view",),
    "pick_list": ("sales.view", "stock.view"),
    "delivery_note": ("sales.view", "stock.view"),
    "sales_invoice": ("sales.view",),
    "credit_note": ("sales.view",),
    "manufacturing_order": ("production.view",),
    "stock_transfer": ("stock.view",),
}
LABELS = {**NAMES, "supplementary_bill": "Supplementary Bill", "original_bill": "Original Bill"}
PAGE = {**PAGES, "supplementary_bill": "purchase-invoices", "original_bill": "purchase-invoices"}
SHORT = {
    "purchase_order": "PO",
    "goods_receipt": "GRN",
    "purchase_invoice": "Bill",
    "original_bill": "Original Bill",
    "supplementary_bill": "Supplementary",
    "purchase_return": "Return",
    "debit_note": "Debit Note",
    "tds_adjustment": "TDS Adjustment",
    "sales_order": "SO",
    "pick_list": "Pick List",
    "delivery_note": "DN",
    "sales_invoice": "SI",
    "credit_note": "Credit Note",
    "manufacturing_order": "MO",
    "stock_transfer": "Transfer",
}
PURCHASE_CHAIN = [
    "purchase_order",
    "goods_receipt",
    "purchase_invoice",
    "purchase_return",
    "debit_note",
]
SALES_CHAIN = ["sales_order", "pick_list", "delivery_note", "sales_invoice", "credit_note"]
PAYMENT_LATER = "not built yet: payments against this bill will show here"
RECEIPT_LATER = "not built yet: money received against this invoice will show here"


def _date(obj):
    for f in (
        "posting_date",
        "bill_date",
        "order_date",
        "receipt_date",
        "return_date",
        "note_date",
        "invoice_date",
        "adj_date",
        "transfer_date",
    ):
        if (d := getattr(obj, f, None)) is not None:
            return d
    created = getattr(obj, "created_at", None)
    return created.date() if created else None


def _note(kind: str, obj) -> str:
    """A few words beside the number: the total, or what kind of note it is."""
    bits = []
    if kind == "credit_note":
        bits.append(obj.get_kind_display())
    if kind == "debit_note":
        bits.append(obj.get_reason_display())
    if kind == "manufacturing_order":
        bits.append(f"{obj.item.code} · {obj.item.name}" if obj.item_id else "")
    total = getattr(obj, "total", None)
    if total and kind != "purchase_order" and kind != "sales_order":
        bits.append(rupees(total))
    return " · ".join(b for b in bits if b)


def _doc(kind: str, obj) -> dict:
    status = getattr(obj, "status", "")
    return {
        "id": obj.pk,
        "number": obj.number or "",
        "date": _date(obj),
        "status": status,
        "status_label": obj.get_status_display() if status else "",
        "note": _note(kind, obj),
    }


def _sorted(rows) -> list:
    rows = {r.pk: r for r in rows}.values()
    return sorted(rows, key=lambda r: (str(_date(r) or ""), r.pk))


def _orders_of(receipts):
    """The purchase orders of these receipts: picked on the receipt, or through its lines."""
    from buying.models import PurchaseOrder

    return PurchaseOrder.objects.filter(
        Q(receipts__in=receipts) | Q(lines__receipt_lines__receipt__in=receipts)
    ).distinct()


# --- The links of each kind -----------------------------------------------
# Each returns the chain (kinds, this one marked) and its groups:
# [(title, [(kind, rows) | ("later", name, words)])].


def _po(o):
    from buying.models import DebitNote, GoodsReceipt, PurchaseInvoice, PurchaseReturn

    receipts = list(
        GoodsReceipt.objects.filter(Q(orders=o) | Q(lines__order_line__order=o)).distinct()
    )
    invoices = PurchaseInvoice.objects.filter(receipts__in=receipts)
    return PURCHASE_CHAIN, [
        ("Came From", [("sales_order", [o.sales_order] if o.sales_order_id else [])]),
        ("Received and Billed", [("goods_receipt", receipts), ("purchase_invoice", invoices)]),
        (
            "Returns and Notes",
            [
                ("purchase_return", PurchaseReturn.objects.filter(receipt__in=receipts)),
                ("debit_note", DebitNote.objects.filter(invoice__in=invoices)),
            ],
        ),
    ]


def _grn(r):
    from buying.models import DebitNote

    invoices = list(r.invoices.all())
    returns = list(r.returns.all())
    notes = DebitNote.objects.filter(
        Q(invoice__in=invoices) | Q(lines__return_line__ret__in=returns)
    )
    return PURCHASE_CHAIN, [
        ("Came From", [("purchase_order", _orders_of([r]))]),
        ("Billed", [("purchase_invoice", invoices)]),
        ("Returns and Notes", [("purchase_return", returns), ("debit_note", notes)]),
    ]


def _pi(inv):
    from buying.models import GoodsReceipt, PurchaseReturn, TdsAdjustment

    base = inv.original if inv.original_id else inv
    receipts = GoodsReceipt.objects.filter(invoices=base)
    came = [
        ("purchase_order", _orders_of(receipts)),
        ("goods_receipt", receipts),
    ]
    if inv.original_id:
        came.append(("original_bill", [inv.original]))
    return PURCHASE_CHAIN, [
        ("Came From", came),
        (
            "Returns and Notes",
            [
                ("purchase_return", PurchaseReturn.objects.filter(receipt__in=receipts)),
                ("debit_note", inv.debit_notes.all()),
                ("supplementary_bill", inv.supplementaries.all()),
            ],
        ),
        (
            "Paid and Adjusted",
            [
                ("later", "Payment", PAYMENT_LATER),
                ("tds_adjustment", TdsAdjustment.objects.filter(lines__invoice=inv)),
            ],
        ),
    ]


def _pr(r):
    from buying.models import DebitNote

    return PURCHASE_CHAIN, [
        (
            "Came From",
            [
                ("purchase_order", _orders_of([r.receipt])),
                ("goods_receipt", [r.receipt]),
                ("purchase_invoice", r.receipt.invoices.all()),
            ],
        ),
        ("Notes", [("debit_note", DebitNote.objects.filter(lines__return_line__ret=r))]),
    ]


def _dn_buy(n):
    from buying.models import GoodsReceipt, PurchaseReturn

    receipts = GoodsReceipt.objects.filter(invoices=n.invoice)
    return PURCHASE_CHAIN, [
        (
            "Came From",
            [
                ("purchase_order", _orders_of(receipts)),
                ("goods_receipt", receipts),
                ("purchase_invoice", [n.invoice]),
            ],
        ),
        (
            "Goods Sent Back",
            [("purchase_return", PurchaseReturn.objects.filter(lines__debit_lines__note=n))],
        ),
    ]


def _tdsa(a):
    from buying.models import PurchaseInvoice

    return [], [
        (
            "For Bills",
            [
                (
                    "purchase_invoice",
                    PurchaseInvoice.objects.filter(tds_adjustment_lines__adjustment=a),
                )
            ],
        )
    ]


def _so(o):
    from manufacturing.models import ManufacturingOrder
    from selling.models import CreditNote, SalesInvoice

    notes = list(o.delivery_notes.all())
    invoices = SalesInvoice.objects.filter(delivery_notes__in=notes)
    return SALES_CHAIN, [
        (
            "Made For It",
            [
                ("purchase_order", o.purchase_orders.all()),
                ("manufacturing_order", ManufacturingOrder.objects.filter(sales_order=o)),
                ("stock_transfer", o.stock_transfers.all()),
            ],
        ),
        (
            "Sent",
            [
                ("pick_list", o.pick_lists.all()),
                ("delivery_note", notes),
                ("sales_invoice", invoices),
            ],
        ),
        (
            "Returns and Receipts",
            [
                ("credit_note", CreditNote.objects.filter(invoice__in=invoices)),
                ("later", "Receipt", RECEIPT_LATER),
            ],
        ),
    ]


def _pick(p):
    from selling.models import CreditNote, SalesInvoice

    notes = list(p.delivery_notes.all())
    invoices = SalesInvoice.objects.filter(delivery_notes__in=notes)
    return SALES_CHAIN, [
        ("Came From", [("sales_order", [p.order])]),
        ("Sent", [("delivery_note", notes), ("sales_invoice", invoices)]),
        ("Returns", [("credit_note", CreditNote.objects.filter(invoice__in=invoices))]),
    ]


def _dn_sell(n):
    from selling.models import CreditNote

    invoices = list(n.invoices.all())
    return SALES_CHAIN, [
        ("Came From", [("sales_order", [n.order]), ("pick_list", [n.pick_list])]),
        ("Billed", [("sales_invoice", invoices)]),
        ("Returns", [("credit_note", CreditNote.objects.filter(invoice__in=invoices))]),
    ]


def _si(inv):
    from selling.models import PickList, SalesOrder

    notes = list(inv.delivery_notes.all())
    return SALES_CHAIN, [
        (
            "Came From",
            [
                ("sales_order", SalesOrder.objects.filter(delivery_notes__in=notes)),
                ("pick_list", PickList.objects.filter(delivery_notes__in=notes)),
                ("delivery_note", notes),
            ],
        ),
        (
            "Returns and Receipts",
            [("credit_note", inv.credit_notes.all()), ("later", "Receipt", RECEIPT_LATER)],
        ),
    ]


def _cn(n):
    from selling.models import SalesOrder

    notes = list(n.invoice.delivery_notes.all())
    return SALES_CHAIN, [
        (
            "Came From",
            [
                ("sales_order", SalesOrder.objects.filter(delivery_notes__in=notes)),
                ("delivery_note", notes),
                ("sales_invoice", [n.invoice]),
            ],
        ),
    ]


def _mo(o):
    return [], [
        ("Came From", [("sales_order", [o.sales_order] if o.sales_order_id else [])]),
        (
            "Made From It",
            [
                (
                    "later",
                    "Material Issue",
                    "not built yet: materials issued to this order will show here",
                ),
                ("later", "Production Entry", "not built yet: what was made will show here"),
            ],
        ),
    ]


def _st(t):
    return [], [("Came From", [("sales_order", [t.sales_order] if t.sales_order_id else [])])]


def _models():
    from buying.models import (
        DebitNote,
        GoodsReceipt,
        PurchaseInvoice,
        PurchaseOrder,
        PurchaseReturn,
        TdsAdjustment,
    )
    from manufacturing.models import ManufacturingOrder
    from selling.models import CreditNote, DeliveryNote, PickList, SalesInvoice, SalesOrder
    from stock.models import StockTransfer

    return {
        "purchase_order": (PurchaseOrder, _po),
        "goods_receipt": (GoodsReceipt, _grn),
        "purchase_invoice": (PurchaseInvoice, _pi),
        "purchase_return": (PurchaseReturn, _pr),
        "debit_note": (DebitNote, _dn_buy),
        "tds_adjustment": (TdsAdjustment, _tdsa),
        "sales_order": (SalesOrder, _so),
        "pick_list": (PickList, _pick),
        "delivery_note": (DeliveryNote, _dn_sell),
        "sales_invoice": (SalesInvoice, _si),
        "credit_note": (CreditNote, _cn),
        "manufacturing_order": (ManufacturingOrder, _mo),
        "stock_transfer": (StockTransfer, _st),
    }


def _may(user, kind: str) -> bool:
    return any(user.can(code) for code in SEE.get(kind, ()))


def connections(user, company, kind: str, pk: int) -> dict:
    table = _models()
    if kind not in table or not _may(user, kind):
        raise NotFound("No such entry.")
    model, links = table[kind]
    obj = model.objects.filter(pk=pk, company=company).first()
    if obj is None:
        raise NotFound("No such entry.")
    if kind == "purchase_invoice" and obj.kind == model.SUPPLEMENTARY:
        me = "supplementary_bill"
    else:
        me = kind
    chain, groups = links(obj)
    out, summary = [], []
    for title, kinds in groups:
        shown = []
        for k in kinds:
            if k[0] == "later":
                shown.append({"type": "later", "name": k[1], "later": k[2]})
                continue
            name, rows = k
            see_as = "purchase_invoice" if name in ("original_bill", "supplementary_bill") else name
            if not _may(user, see_as):
                continue
            rows = [
                r
                for r in _sorted(rows)
                if getattr(r, "company_id", company.pk) == company.pk and r != obj
            ]
            if name == "purchase_invoice":
                rows = [r for r in rows if r.kind != r.SUPPLEMENTARY]
            docs = [_doc(name, r) for r in rows]
            if docs:
                summary.append(f"{SHORT.get(name, LABELS.get(name, name))} {len(docs)}")
            shown.append(
                {
                    "type": name,
                    "name": LABELS.get(name, name),
                    "page": PAGE.get(name, ""),
                    "count": len(docs),
                    "docs": docs,
                }
            )
        if shown:
            out.append({"title": title, "kinds": shown})
    return {
        "type": me,
        "chain": [{"type": k, "name": LABELS[k], "me": k == kind} for k in chain],
        "groups": out,
        "summary": " · ".join(summary) or "Nothing yet",
    }


# --- Masters: parties and items (preview mockups/connections/3) ------------
# Counts only for a party, for the company being worked in, with "All n" opening
# that list already searched for the party (`col`, `q`) and showing every
# status. An item's entries cannot be searched for in the lists, so the latest
# few are named instead.

LATEST = 5
LABELS.update({"stock_receipt": "Stock Receipt", "stock_delivery": "Stock Delivery"})
LABELS.update({"bom": "BOM", "bom_material": "BOM (as Material)", "batch": "Batch"})
SEE.update({"stock_receipt": ("stock.view",), "stock_delivery": ("stock.view",)})
SEE.update(
    {"bom": ("masters.view",), "bom_material": ("masters.view",), "batch": ("masters.view",)}
)
SHORT.update({"stock_receipt": "Stock Receipt", "stock_delivery": "Stock Delivery"})
SHORT.update({"bom": "BOM", "bom_material": "BOM Material", "batch": "Batch"})


def _party_groups(company, party):
    from buying.models import (
        DebitNote,
        GoodsReceipt,
        PurchaseInvoice,
        PurchaseOrder,
        PurchaseReturn,
        TdsAdjustment,
    )
    from core.models import Ledger
    from manufacturing.models import ManufacturingOrder
    from selling.models import CreditNote, DeliveryNote, SalesInvoice, SalesOrder
    from stock.models import CustomerStock

    ledgers = list(Ledger.objects.filter(company=company, party=party))
    name = ledgers[0].name if ledgers else party.name
    c = {"company": company}

    def by(model, field):
        return model.objects.filter(**c, **{f"{field}__in": ledgers})

    stock = CustomerStock.objects.filter(**c, customer__in=ledgers)
    return name, [
        (
            "Sales",
            [
                ("sales_order", by(SalesOrder, "customer"), "customer"),
                ("delivery_note", by(DeliveryNote, "customer"), "customer"),
                ("sales_invoice", by(SalesInvoice, "customer"), "customer"),
                ("credit_note", by(CreditNote, "customer"), "customer"),
            ],
        ),
        (
            "Purchase",
            [
                ("purchase_order", by(PurchaseOrder, "supplier"), "supplier"),
                ("goods_receipt", by(GoodsReceipt, "supplier"), "supplier"),
                ("purchase_invoice", by(PurchaseInvoice, "supplier"), "supplier"),
                ("purchase_return", by(PurchaseReturn, "supplier"), "supplier"),
                ("debit_note", by(DebitNote, "supplier"), "supplier"),
            ],
        ),
        (
            "Other",
            [
                ("stock_receipt", stock.filter(kind=CustomerStock.RECEIPT), "customer"),
                ("stock_delivery", stock.filter(kind=CustomerStock.DELIVERY), "customer"),
                (
                    "manufacturing_order",
                    ManufacturingOrder.objects.filter(**c, customer=party),
                    None,
                ),
                ("tds_adjustment", by(TdsAdjustment, "supplier"), "supplier"),
                ("later", "Payment / Receipt", "not built yet"),
            ],
        ),
    ]


def _item_groups(company, item):
    from buying.models import GoodsReceipt, PurchaseInvoice, PurchaseOrder, PurchaseReturn
    from core.models import Batch
    from manufacturing.models import Bom, ManufacturingOrder
    from selling.models import CreditNote, DeliveryNote, SalesInvoice, SalesOrder

    c = {"company": company}

    def by(model):
        return model.objects.filter(**c, lines__item=item).distinct()

    return item.name, [
        (
            "Sales",
            [
                ("sales_order", by(SalesOrder), None),
                ("delivery_note", by(DeliveryNote), None),
                ("sales_invoice", by(SalesInvoice), None),
                ("credit_note", by(CreditNote), None),
            ],
        ),
        (
            "Purchase",
            [
                ("purchase_order", by(PurchaseOrder), None),
                ("goods_receipt", by(GoodsReceipt), None),
                ("purchase_invoice", by(PurchaseInvoice), None),
                ("purchase_return", by(PurchaseReturn), None),
            ],
        ),
        (
            "Production and Stock",
            [
                ("bom", Bom.objects.filter(item=item), None),
                ("bom_material", Bom.objects.filter(lines__item=item).distinct(), None),
                ("manufacturing_order", ManufacturingOrder.objects.filter(**c, item=item), None),
                ("batch", Batch.objects.filter(item=item), None),
            ],
        ),
    ]


def _latest(rows) -> list:
    newest = sorted(rows, key=lambda r: (str(_date(r) or ""), r.pk), reverse=True)
    return newest[:LATEST]


def _master_doc(what: str, obj) -> dict:
    """An entry as `_doc` gives it; a BOM or a batch (not a company's) carries its own link."""
    doc = _doc(what, obj)
    if what in ("bom", "bom_material"):
        doc["href"] = f"#/boms?view={obj.pk}"
        doc["note"] = f"{obj.item.name} · version {obj.version}"
    elif what == "batch":
        doc["href"] = f"#/batches/{obj.pk}/trace"
        doc["note"] = "Batch Trace"
    return doc


def master_connections(user, company, kind: str, pk: int) -> dict:
    from core.models import Item, Party

    if not user.can("masters.view"):
        raise NotFound("No such record.")
    if kind == "party":
        obj = Party.objects.filter(pk=pk).first()
        groups = _party_groups if obj else None
    elif kind == "item":
        obj = Item.objects.filter(pk=pk).first()
        groups = _item_groups if obj else None
    else:
        obj = groups = None
    if obj is None:
        raise NotFound("No such record.")
    name, layout = groups(company, obj)
    out, summary = [], []
    for title, kinds in layout:
        shown = []
        for k in kinds:
            if k[0] == "later":
                shown.append({"type": "later", "name": k[1], "later": k[2]})
                continue
            what, rows, col = k
            if not _may(user, what):
                continue
            count = rows.count()
            entry = {
                "type": what,
                "name": LABELS.get(what, what),
                "page": PAGE.get(what, ""),
                "count": count,
            }
            if kind == "party":
                entry["all"] = {"col": col, "q": name} if col and count else None
            else:
                entry["docs"] = [_master_doc(what, r) for r in _latest(rows)] if count else []
            if count:
                summary.append(f"{SHORT.get(what, LABELS.get(what, what))} {count}")
            shown.append(entry)
        if shown:
            out.append({"title": title, "kinds": shown})
    return {
        "type": kind,
        "chain": [],
        "groups": out,
        "summary": " · ".join(summary) or "Nothing yet",
    }


class ConnectionsView(APIView):
    permission_classes = [Signed]

    def get(self, request, pk: int, kind: str, entry: int):
        company = _company(request, pk)
        if kind in ("party", "item"):
            return Response(master_connections(request.user, company, kind, entry))
        return Response(connections(request.user, company, kind, entry))
