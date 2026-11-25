"""Prints for the purchase entries after the bill (Sidharth, 2026-11-25: cover the
missing prints): the Debit Note and the Purchase Return's Return Challan in the
purchase order's layout (buying.po_pdf), and the TDS Adjustment as a columnar
voucher (core.printout)."""

from __future__ import annotations

from decimal import Decimal

from django.http import HttpResponse
from rest_framework.views import APIView

from buying.models import DebitNote, PurchaseOrder, PurchaseReturn, TdsAdjustment
from core import printout, words
from core.api import Signed

ZERO = Decimal("0")


def _dmy(d) -> str:
    return f"{d:%d-%m-%Y}" if d else ""


def _signature(doc) -> str:
    if doc.submitted_by and doc.status != "draft":
        return doc.submitted_by.signature_url()
    return ""


def _respond(content: bytes, number: str, fallback: str, request) -> HttpResponse:
    response = HttpResponse(content, content_type="application/pdf")
    name = (number or fallback).replace("/", "-")
    how = "attachment" if request.query_params.get("download") == "1" else "inline"
    response["Content-Disposition"] = f'{how}; filename="{name}.pdf"'
    return response


# Debit Note ------------------------------------------------------------------


def debit_note_data(note: DebitNote) -> dict:
    """The note as the supplier gets it: no ledger posting, which is ours."""
    from buying.api import _branch_address, _letterhead
    from buying.debit_notes import _fresh
    from buying.invoice_pdf import _money, _supplier_box, order_description

    inv = note.invoice
    data = _fresh(note)
    orders = list(PurchaseOrder.objects.filter(receipts__invoices=inv).distinct())
    data["doc_title"] = "DEBIT NOTE"
    data["order_date"] = note.note_date
    data["currency"], data["currency_symbol"] = "INR", "₹"
    data["letterhead"] = _letterhead(note.company)
    data["box_titles"] = ("Supplier", "Issued By", None)
    data["addresses"] = {
        "supplier": _supplier_box(inv, orders),
        "bill_to": _branch_address(note.branch),
    }
    rate = note.reason == "rate"
    described = {
        ln.pk: order_description(ln.invoice_line.receipt_line)
        for ln in note.lines.select_related("invoice_line__receipt_line__order_line")
    }
    data["lines"] = [
        {
            **x,
            "description": "\n".join(
                y
                for y in [
                    described.get(x["id"], ""),
                    f"Rate {x['rate']} → {x['new_rate']} on {x['qty']} {x['unit_name']}"
                    if rate and x.get("new_rate") is not None
                    else (f"Returned on {x['return_number']}" if x["return_number"] else ""),
                ]
                if y
            ),
            # A rate note credits the difference per unit.
            "rate": str(Decimal(x["rate"]) - Decimal(x["new_rate"]))
            if rate and x.get("new_rate") is not None
            else x["rate"],
        }
        for x in data["lines"]
    ]
    data["charges"] = []
    your = " of ".join(x for x in [note.supplier_note_no, _dmy(note.supplier_note_date)] if x)
    data["print_meta"] = [
        (k, v or "")
        for k, v in [
            ("Reason", data["reason_label"]),
            ("Against Your Bill", f"{inv.bill_no} of {_dmy(inv.bill_date)}" if inv.bill_no else ""),
            ("Our Purchase Invoice", inv.number),
            (
                "Purchase Return" + ("s" if len(data["returns"]) > 1 else ""),
                ", ".join(data["returns"]),
            ),
            ("Your Credit Note", your),
            ("Entered By", data["created_by_name"]),
        ]
    ]
    after = []
    if note.tds_total:
        after = [
            ("Less TDS taken back", f"-{_money(note.tds_total)}", False),
            ("Net Debit", f"₹{_money(note.total - note.tds_total)}", True),
        ]
    data["after_total"] = after
    data["amount_words"] = words.amount(note.total, "INR", "Indian Rupee")
    data["submitted_by_signature"] = _signature(note)
    data["terms"] = f"Notes:\n{note.notes}" if note.notes.strip() else ""
    return data


# Return Challan ----------------------------------------------------------------


def return_data(r: PurchaseReturn) -> dict:
    """The challan that goes with the goods: valued at our receipt cost, no GST
    (a return is not a sale; the debit note carries the GST)."""
    from buying.api import _branch_address, _letterhead
    from buying.invoice_pdf import _supplier_box, order_description
    from buying.returns import _fresh

    data = _fresh(r)
    orders = list(PurchaseOrder.objects.filter(receipts=r.receipt).distinct())
    described = {
        ln.pk: order_description(ln.receipt_line)
        for ln in r.lines.select_related("receipt_line__order_line")
    }
    data["doc_title"] = "RETURN CHALLAN"
    data["order_date"] = r.return_date
    data["currency"], data["currency_symbol"] = "INR", "₹"
    data["letterhead"] = _letterhead(r.company)
    data["box_titles"] = ("Return To", "Sent From", None)
    data["addresses"] = {
        "supplier": _supplier_box(r, orders),
        "bill_to": _branch_address(r.branch),
    }
    data["lines"] = [
        {
            **x,
            "rate": x["receipt_rate"],
            "taxable": x["value"],
            "gst_rate": "0",
            "cgst": ZERO,
            "sgst": ZERO,
            "igst": ZERO,
            "description": "\n".join(
                y
                for y in [
                    described.get(x["id"], ""),
                    x["batch_number"] and f"Batch {x['batch_number']}",
                ]
                if y
            ),
        }
        for x in data["lines"]
    ]
    data["charges"] = []
    value = data["value"]
    data.update(
        taxable_total=value,
        cgst_total=ZERO,
        sgst_total=ZERO,
        igst_total=ZERO,
        round_off=ZERO,
        total=value,
        hide_round_off=True,
        total_label="Value",
    )
    rcpt = r.receipt
    data["print_meta"] = [
        (k, v or "")
        for k, v in [
            ("Reason", data["reason_label"]),
            ("Against GRN", f"{rcpt.number} of {_dmy(rcpt.receipt_date)}"),
            ("Your Challan / Bill", data["challan_no"]),
            ("Purchase Order", ", ".join(sorted(o.number for o in orders if o.number))),
            ("Transporter", data["transporter_name"]),
            ("LR No", r.lr_no),
            ("Vehicle", r.vehicle_no),
            ("e-Way Bill", r.eway_bill_no),
        ]
    ]
    data["after_total"] = []
    data["amount_words"] = words.amount(value, "INR", "Indian Rupee")
    data["submitted_by_signature"] = _signature(r)
    terms = [
        "Note:",
        "Goods returned to you against our goods receipt; not a sale.",
        "Value at our receipt cost, for transport only. A debit note follows where billed.",
    ]
    if r.notes.strip():
        terms += [r.notes]
    data["terms"] = "\n".join(terms)
    return data


# TDS Adjustment --------------------------------------------------------------


def tds_adjustment_pdf(adj: TdsAdjustment) -> bytes:
    from buying.tds_check import _fresh, _plan
    from core import print_mark
    from posting import api as posting_api

    data = _fresh(adj)
    rows = [
        [
            x["number"],
            x["bill_no"],
            _dmy(x["posting_date"]),
            str(x["base"]),
            f"{x['rate']}%",
            str(x["due"]),
            str(x["deducted"]),
            str(x["amount"]),
            str(x["months"] or ""),
            str(x["interest"]),
        ]
        for x in data["lines"]
    ]
    rows.append(["Total", "", "", "", "", "", "", str(adj.total), "", str(adj.interest)])
    bills = {
        "title": "Bills",
        "columns": ["Bill", "Supplier Bill No", "Posting Date", "Base ₹", "TDS %",
                    "TDS Due ₹", "Deducted ₹", "Adjustment ₹", "Months", "Interest ₹"],
        "rows": rows,
    }  # fmt: skip
    if adj.status == TdsAdjustment.DRAFT:
        lines = [(g.ledger.name, g.debit, g.credit) for g in _plan(adj, preview=True)]
    else:
        lines = [
            (x["ledger_name"], Decimal(x["debit"]), Decimal(x["credit"]))
            for x in posting_api.posted("tds_adjustment", adj.pk)["rows"]
        ]
    dr = sum((d for _n, d, _c in lines), ZERO)
    cr = sum((c for _n, _d, c in lines), ZERO)
    posting = {
        "title": "Ledger Posting",
        "columns": ["Ledger", "Debit ₹", "Credit ₹"],
        "rows": [[n, str(d) if d else "", str(c) if c else ""] for n, d, c in lines]
        + ([["Total", str(dr), str(cr)]] if lines else []),
    }
    status = {"draft": "Draft · number on Submit", "cancelled": "Cancelled"}.get(adj.status, "")
    who = (
        f"Approved by {data['submitted_by_name']} on {adj.submitted_at:%d-%m-%Y}"
        if adj.submitted_at and data["submitted_by_name"]
        else "Not yet approved"
    )
    details = {
        "title": "Details",
        "columns": ["Detail", "Value"],
        "rows": [
            [k, v]
            for k, v in [
                ("Supplier", adj.supplier.name),
                ("Section", data["section_shown"]),
                ("Type", data["kind_label"]),
                ("Remarks", adj.remarks),
                ("Entered By", data["created_by_name"]),
                ("Status", status or who),
            ]
            if v
        ],
    }
    scope = " · ".join([adj.company.name, f"Date {_dmy(adj.adj_date)}"])
    title = f"TDS Adjustment {adj.number}" if adj.number else "TDS Adjustment (draft)"
    mark = print_mark.mark(adj.company)
    sheets = [details, bills] + ([posting] if posting["rows"] else [])
    return printout.pdf(title, scope, sheets, mark)


# Views -----------------------------------------------------------------------


class DebitNotePdfView(APIView):
    """GET (&download=1): the debit note as a PDF."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from buying.api import VIEW, _check
        from buying.debit_notes import _note
        from buying.po_pdf import order_pdf

        _check(request, VIEW)
        note = _note(request, pk)
        return _respond(order_pdf(debit_note_data(note)), note.number, "draft-debit-note", request)


class ReturnPdfView(APIView):
    """GET (&download=1): the purchase return's Return Challan as a PDF."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from buying.po_pdf import order_pdf
        from buying.returns import VIEW, _check, _return

        _check(request, VIEW)
        r = _return(request, pk)
        return _respond(order_pdf(return_data(r)), r.number, "draft-return-challan", request)


class TdsAdjustmentPdfView(APIView):
    """GET (&download=1): the TDS adjustment as a PDF."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        from buying.tds_check import VIEW, _adjustment, _check

        _check(request, VIEW)
        adj = _adjustment(request, pk)
        return _respond(tds_adjustment_pdf(adj), adj.number, "draft-tds-adjustment", request)
