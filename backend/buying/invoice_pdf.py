"""The purchase invoice as a PDF (Sidharth, 2026-11-25: "we are missing a
purchase invoice format"). The same layout as the purchase order print
(buying.po_pdf): letterhead with the company's image on page 1, Supplier /
Bill To / Received At boxes, the bill's details, the lines with their goods
receipt and order, the tax summary, totals less TDS to the net payable, due
dates, the ledger posting, notes and the signature.

One print serves all three kinds of bill on the Purchase Invoice model: a bill
against goods receipts, a supplementary bill (rate up) and a bill without a
goods receipt (services and goods not kept in stock)."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse
from rest_framework.views import APIView

from buying.models import PurchaseInvoice, PurchaseOrder
from core import words
from core.api import Signed

TITLES = {
    PurchaseInvoice.REGULAR: "PURCHASE INVOICE",
    PurchaseInvoice.SUPPLEMENTARY: "SUPPLEMENTARY BILL",
    PurchaseInvoice.DIRECT: "PURCHASE INVOICE",
}


def _dmy(d) -> str:
    return f"{d:%d-%m-%Y}" if d else ""


def _supplier_box(inv: PurchaseInvoice, orders: list[PurchaseOrder]) -> dict:
    """The supplier's address as the order kept it, else its billing address."""
    from buying.api import _party_address, _party_fssai

    party = inv.supplier.party
    kept = next((o.supplier_address for o in orders if o.supplier_address), None)
    if not kept and party is not None:
        rows = list(party.addresses.all())
        a = next((x for x in rows if x.is_billing), rows[0] if rows else None)
        kept = _party_address(a) if a else {}
    kept = kept or {}
    return {
        "name": inv.supplier.name,
        **kept,
        "gstin": kept.get("gstin") or (party.gstin if party else ""),
        "fssai": _party_fssai(party, kept.get("label", "")),
    }


def _lines(data: dict, inv: PurchaseInvoice) -> list[dict]:
    """The bill's lines in the order print's shape: item, HSN, qty, rate, taxable."""
    if inv.kind == PurchaseInvoice.SUPPLEMENTARY:
        return [
            {
                **x,
                "item_number": x["item_number"],
                "rate": str(Decimal(x["new_rate"]) - Decimal(x["rate"])),
                "description": f"Rate {x['rate']} → {x['new_rate']} on {x['qty']} {x['unit_name']}",
            }
            for x in data.get("rate_lines") or []
        ]
    if inv.kind == PurchaseInvoice.DIRECT:
        return [
            {
                **x,
                "item_name": x["name"],
                "item_number": "",
                "description": " · ".join(
                    y
                    for y in [x["description"], x["booked_to_name"] and f"To {x['booked_to_name']}"]
                    if y
                ),
            }
            for x in data.get("expense_lines") or []
        ]
    return [
        {
            **x,
            "description": " · ".join(
                y
                for y in [
                    x["receipt_number"] and f"GRN {x['receipt_number']}",
                    x["order_number"] and f"PO {x['order_number']}",
                ]
                if y
            ),
        }
        for x in data["lines"]
    ]


def print_data(inv: PurchaseInvoice) -> dict:
    from buying.api import _branch_address, _letterhead
    from buying.invoices import _fresh

    data = _fresh(inv)
    orders = list(
        PurchaseOrder.objects.filter(
            Q(receipts__invoices=inv) | Q(receipts__invoices__supplementaries=inv)
        ).distinct()
    )
    receipts = list(inv.receipts.select_related("branch"))
    if inv.original_id:
        receipts = list(inv.original.receipts.select_related("branch"))
    data["doc_title"] = TITLES[inv.kind]
    data["order_date"] = inv.posting_date or inv.bill_date
    data["currency"], data["currency_symbol"] = "INR", "₹"
    data["letterhead"] = _letterhead(inv.company)
    data["box_titles"] = ("Supplier", "Bill To", "Received At")
    received = receipts[0].branch if receipts else inv.branch
    data["addresses"] = {
        "supplier": _supplier_box(inv, orders),
        "bill_to": _branch_address(inv.branch),
        "ship_to": _branch_address(received),
    }
    data["lines"] = _lines(data, inv)
    if inv.kind != PurchaseInvoice.REGULAR:
        data["charges"] = []
    for x in data.get("charges") or []:
        x["basis_label"] = "Added to stock cost" if x["in_stock_cost"] else "Expense"
    grns = ", ".join(r.number for r in receipts if r.number)
    pos = ", ".join(sorted(o.number for o in orders if o.number))
    dues = data.get("dues") or []
    data["print_meta"] = [
        (k, v or "")
        for k, v in [
            ("Supplier Bill No", inv.bill_no),
            ("Bill Date", _dmy(inv.bill_date)),
            ("Posting Date", _dmy(inv.posting_date)),
            ("Credit Term", data["credit_term_name"]),
            (
                "Against Bill",
                inv.original_id
                and f"{inv.original.number} (bill {inv.original.bill_no}"
                f" of {_dmy(inv.original.bill_date)})",
            ),
            ("Goods Receipt" + ("s" if len(receipts) > 1 else ""), grns),
            ("Purchase Order" + ("s" if len(orders) > 1 else ""), pos),
            ("Bill Type", inv.kind == PurchaseInvoice.DIRECT and data["kind_label"]),
            ("Entered By", data["created_by_name"]),
        ]
    ]
    after = []
    box = data.get("tds") or {}
    # One line per section, named as the TDS Payable ledger names it.
    by_section: dict[str, Decimal] = {}
    for r in box.get("rows") or []:
        if Decimal(r["amount"] or 0):
            key = r["section"] or ""
            by_section[key] = by_section.get(key, Decimal(0)) + Decimal(r["amount"])
    for code, amount in by_section.items():
        after.append((f"Less TDS {code}".strip(), f"-{_money(amount)}", False))
    if inv.tds_total:
        after.append(("Net Payable", f"₹{_money(inv.total - inv.tds_total)}", True))
    data["after_total"] = after
    data["dues"] = dues if inv.status != PurchaseInvoice.CANCELLED else []
    data["posting"] = [e for e in data.get("entries") or [] if e.get("ledger")]
    data["amount_words"] = words.amount(inv.total, "INR", "Indian Rupee")
    data["submitted_by_signature"] = (
        inv.submitted_by.signature_url()
        if inv.submitted_by and inv.status != PurchaseInvoice.DRAFT
        else ""
    )
    data["terms"] = f"Notes:\n{inv.notes}" if inv.notes.strip() else ""
    return data


def _money(v: Decimal) -> str:
    from buying.po_pdf import _indian_int

    return _indian_int(f"{Decimal(v).quantize(Decimal('0.01')):f}")


def invoice_pdf(inv: PurchaseInvoice) -> bytes:
    from buying.po_pdf import order_pdf

    return order_pdf(print_data(inv))


class InvoicePdfView(APIView):
    """GET (&download=1): the purchase invoice, supplementary bill or bill without
    goods receipt as a PDF, inline unless asked to download."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from buying.api import VIEW, _check
        from buying.invoices import _invoice

        _check(request, VIEW)
        inv = _invoice(request, pk)
        response = HttpResponse(invoice_pdf(inv), content_type="application/pdf")
        name = (inv.number or "draft-purchase-invoice").replace("/", "-")
        how = "attachment" if request.query_params.get("download") == "1" else "inline"
        response["Content-Disposition"] = f'{how}; filename="{name}.pdf"'
        return response
