"""Accounts Payable prints (Sidharth, 2026-11-28, previews
mockups/accounts-payable/3 and 4, kept in colour):

* the management print, landscape: the company heading, an ageing strip, one
  row per supplier; "with Bills" adds each supplier's open bills after it;
* "Outstanding Bills" for one supplier, portrait, to send to them: the same
  heading, "Account Of" and "Summary" boxes, the open bills with what came off
  each (TDS section and adjustments, debit notes, payments), the ageing strip,
  and "Please Confirm" beside the signature.

The small Ganesha image prints at the top centre of page 1 when the company has
"Print Lord Ganesha image" ticked; each page ends "Page n of m".
"""

from __future__ import annotations

import datetime
import io

from django.http import HttpResponse
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from buying import payables
from buying.api import VIEW, _check, _company, _letterhead
from core import india, print_mark, printout
from core.api import Signed
from core.models import Ledger

INK = "#1F2A24"
DEEP = "#17532F"
LEAF = "#2E9E5B"
GREEN = "#1D6B3F"
MUTED = "#5B6B63"
SUB = "#6B7A72"
CARD = "#F2F8F4"
MINT = "#E3F1E8"
LINE = "#E6EEE8"
RED = "#B42318"


def _dmy(d: datetime.date | None) -> str:
    return d.strftime("%d-%m-%Y") if d else ""


def _inr(text: str, blank: bool = False) -> str:
    if blank and float(text or 0) == 0:
        return ""
    return printout.indian(text)


class _Kit:
    """Fonts and paragraph styles shared by both prints."""

    def __init__(self):
        from reportlab.lib.fonts import addMapping

        self.regular, self.bold = printout._font_names()
        self.rupee = self.regular != "Helvetica"
        addMapping(self.regular, 0, 0, self.regular)
        addMapping(self.regular, 1, 0, self.bold)
        addMapping(self.regular, 0, 1, self.regular)
        addMapping(self.regular, 1, 1, self.bold)
        self._styles = {}
        self.size = 8.4  # table text; the portrait print is narrower
        self.pad = 5

    def t(self, value) -> str:
        value = str(value or "")
        if not self.rupee:
            value = value.replace("₹", "Rs ")
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def style(self, size=8.6, lead=None, bold=False, colour=INK, align="left"):
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.styles import ParagraphStyle

        key = (size, lead, bold, colour, align)
        if key not in self._styles:
            self._styles[key] = ParagraphStyle(
                f"s{len(self._styles)}",
                fontName=self.bold if bold else self.regular,
                fontSize=size,
                leading=lead or size * 1.3,
                textColor=colour,
                alignment={"left": TA_LEFT, "right": TA_RIGHT, "center": TA_CENTER}[align],
            )
        return self._styles[key]

    def p(self, text, **kw):
        from reportlab.platypus import Paragraph

        return Paragraph(text, self.style(**kw))

    def cell(self, main: str, note: str = "", right=False, bold=False):
        """A table cell: the value, and a small grey note under it."""
        align = "right" if right else "left"
        text = self.t(main)
        if bold:
            text = f"<b>{text}</b>"
        if note:
            text += f'<br/><font size="{self.size - 1.4}" color="{SUB}">{self.t(note)}</font>'
        return self.p(text, size=self.size, lead=self.size * 1.25, align=align)


def _heading(kit: _Kit, lh: dict, title: str, lines: list[str], width: float):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    brand = Table(
        [
            [
                kit.p(
                    kit.t(lh["name"][:1]),
                    size=14,
                    lead=16,
                    bold=True,
                    colour="#FFFFFF",
                    align="center",
                ),
                kit.p(kit.t(lh["name"]), size=14, lead=17, bold=True),
            ]
        ],
        colWidths=[22, None],
    )
    brand.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(LEAF)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 3),
                ("BOTTOMPADDING", (0, 0), (0, 0), 3),
                ("LEFTPADDING", (1, 0), (1, 0), 8),
            ]
        )
    )
    addr = [x.strip().rstrip(",") for x in (lh.get("address") or "").split("\n") if x.strip()]
    rows = []
    if addr:
        tail = ", ".join([*addr[1:], lh.get("city") or ""]).strip(", ")
        if lh.get("pincode"):
            tail += f" - {lh['pincode']}"
        rows.append(f"Regd Office: {addr[0]}{',' if tail else ''}")
        if tail:
            rows.append(tail)
    contact = " · ".join(x for x in [lh.get("phone") and f"Ph {lh['phone']}", lh.get("email")] if x)
    if contact:
        rows.append(contact)
    html = [kit.t(x) for x in rows]
    numbers = " · ".join(
        f"<b>{k}</b> {kit.t(v)}"
        for k, v in (("GSTIN", lh.get("gstin")), ("PAN", lh.get("pan")))
        if v
    )
    if numbers:
        html.append(numbers)
    left = [brand, kit.p("<br/>".join(html), size=8.3, lead=11.5, colour=MUTED)]
    right = [kit.p(kit.t(title), size=18, lead=22, bold=True, colour=DEEP, align="right")]
    for n, line in enumerate(lines):
        right.append(
            kit.p(
                kit.t(line),
                size=10.5 if n == 0 else 8.3,
                lead=13 if n == 0 else 11,
                colour=INK if n == 0 else MUTED,
                align="right",
            )
        )
    head = Table([[left, right]], colWidths=[width * 0.55, width * 0.45])
    head.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (0, 0), "TOP"),
                ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (1, 0), (1, 0), 26),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), 2.2, colors.HexColor(LEAF)),
            ]
        )
    )
    return head


def _strip(
    kit: _Kit,
    labels: list[str],
    buckets: list[str],
    total: str,
    width: float,
    by_bill: bool,
    size=10.5,
):
    """The ageing boxes: one per bucket and a dark Total Due."""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    cells = []
    for i, (label, v) in enumerate(zip(labels, buckets, strict=True)):
        name = label if i == 0 and not by_bill else f"{label} days"
        red = i >= 3 and float(v) > 0
        cells.append(
            [
                kit.p(kit.t(name.upper()), size=6.8, lead=9, bold=True, colour=LEAF),
                kit.p(
                    kit.t(f"₹{_inr(v)}"),
                    size=size,
                    lead=size * 1.25,
                    bold=True,
                    colour=RED if red else INK,
                ),
            ]
        )
    cells.append(
        [
            kit.p("TOTAL DUE", size=6.8, lead=9, bold=True, colour="#BFE3CC"),
            kit.p(
                kit.t(f"₹{_inr(total)}"), size=size, lead=size * 1.25, bold=True, colour="#FFFFFF"
            ),
        ]
    )
    gap = 6
    w = (width - gap * 5) / 6
    data = [[]]
    widths = []
    for i, c in enumerate(cells):
        data[0].append(c)
        widths.append(w)
        if i < 5:
            data[0].append("")
            widths.append(gap)
    table = Table(data, colWidths=widths)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(6):
        col = i * 2
        fill = DEEP if i == 5 else CARD
        style.append(("BACKGROUND", (col, 0), (col, 0), colors.HexColor(fill)))
    table.setStyle(TableStyle(style))
    return table


def _grid(
    kit: _Kit,
    heads: list[tuple[str, bool]],
    rows: list[list],
    widths,
    *,
    groups=(),
    subtotals=(),
    total=True,
    span=0,
):
    """The bills or suppliers table: dark green heading repeated on every page,
    light row lines, mint group rows, a mint total row under a dark rule."""
    from reportlab.lib import colors
    from reportlab.platypus import LongTable, TableStyle

    head = [
        kit.p(
            kit.t(h),
            size=kit.size - 0.2,
            lead=kit.size * 1.2,
            bold=True,
            colour="#FFFFFF",
            align="right" if r else "left",
        )
        for h, r in heads
    ]
    table = LongTable([head, *rows], colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(DEEP)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor(LINE)),
        ("LEFTPADDING", (0, 0), (-1, -1), kit.pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), kit.pad),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
    ]
    for n in groups:
        style += [("BACKGROUND", (0, n), (-1, n), colors.HexColor(MINT)), ("SPAN", (0, n), (-1, n))]
    for n in subtotals:
        style.append(("LINEBELOW", (0, n), (-1, n), 1, colors.HexColor("#9CC6AA")))
    if total and rows:
        style += [
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(MINT)),
            ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor(DEEP)),
        ]
        if span:
            style.append(("SPAN", (0, -1), (span - 1, -1)))
    table.setStyle(TableStyle(style))
    return table


def _build(story, *, landscape: bool, footer_text: str, mark: bytes | None, title: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.pagesizes import landscape as turn
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import SimpleDocTemplate

    page = turn(A4) if landscape else A4
    margin = 12 * mm if landscape else 14 * mm
    regular, bold = printout._font_names()
    rupee = regular != "Helvetica"
    picture = ImageReader(io.BytesIO(mark)) if mark else None

    def footer(canvas, number: int, total: int) -> None:
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor("#7A8A82"))
        text = footer_text if rupee else footer_text.replace("₹", "Rs ")
        canvas.drawString(margin, 7 * mm, text)
        canvas.setFont(bold, 7.5)
        canvas.setFillColor(colors.HexColor(GREEN))
        canvas.drawRightString(page[0] - margin, 7 * mm, f"Page {number} of {total}")
        if picture is not None and number == 1:
            iw, ih = picture.getSize()
            h = 13 * mm
            w = h * iw / ih
            canvas.drawImage(
                picture, (page[0] - w) / 2, page[1] - margin - h + 2 * mm, w, h, mask="auto"
            )
        canvas.restoreState()

    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=page,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=14 * mm,
        title=title,
        author="MyERP",
    )
    doc.build(story, canvasmaker=printout._numbered_canvas(footer))
    return out.getvalue()


def _width(landscape: bool) -> float:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    return (A4[1] - 24 * mm) if landscape else (A4[0] - 28 * mm)


def _scope(company, a: payables.Asked) -> list[str]:
    bits = []
    if a.branch:
        b = company.branches.filter(pk=a.branch).first()
        bits.append(b.name if b else "")
    else:
        bits.append("All branches")
    if a.purchaser:
        from core.models import SalesPerson

        p = SalesPerson.objects.filter(pk=a.purchaser).first()
        bits.append(f"Purchaser {p.name}" if p else "")
    if a.overdue:
        bits.append("Overdue only")
    return [x for x in bits if x]


def _bill_cells(kit: _Kit, r: dict) -> list:
    late = r["late"]
    return [
        kit.cell(r["bill_no"], "Opening bill" if r["our_no"] == "Opening" else r["our_no"]),
        kit.cell(_dmy(r["bill_date"])),
        kit.cell(_dmy(r["due_date"])),
        kit.cell(_inr(r["amount"]), right=True),
        kit.cell(_inr(r["tds"], True), r["tds_note"], right=True),
        kit.cell(_inr(r["dn"], True), r["dn_note"], right=True),
        kit.cell(_inr(r["paid"], True), r["paid_note"], right=True),
        kit.cell(_inr(r["balance"]), right=True, bold=True),
        kit.p(
            f'<font color="{RED if late > 60 else INK}">{late or ""}</font>',
            size=kit.size,
            align="right",
        ),
    ]


BILL_HEADS = [
    ("Bill No / Our Entry", False),
    ("Bill Date", False),
    ("Due Date", False),
    ("Bill Amount ₹", True),
    ("TDS ₹", True),
    ("Debit Notes ₹", True),
    ("Paid ₹", True),
    ("Balance ₹", True),
    ("Days Overdue", True),
]


def management_pdf(company, params) -> bytes:
    """Accounts Payable for management: ageing strip, one row per supplier, and
    with ?layout=bills each supplier's open bills after it."""
    from reportlab.platypus import PageBreak, Spacer

    kit = _Kit()
    a = payables.asked(params)
    rows, totals = payables.suppliers_view(company, params, a)
    width = _width(True)
    aged = "Aged by Bill Date" if a.by_bill else "Aged by Due Date"
    scope = _scope(company, a)
    story = [
        _heading(
            kit,
            _letterhead(company),
            "ACCOUNTS PAYABLE",
            [f"As on {_dmy(a.as_on)} · {aged}", " · ".join(scope)],
            width,
        ),
        Spacer(1, 8),
        _strip(kit, a.labels, totals["b"], totals["due"], width, a.by_bill),
        Spacer(1, 8),
    ]
    labels = [lab if i == 0 and not a.by_bill else lab for i, lab in enumerate(a.labels)]
    heads = [("#", False), ("Supplier", False), ("Bills", True)] + [
        (f"{x} ₹", True) for x in labels
    ]
    heads += [("Total Due ₹", True), ("Oldest Overdue (Days)", True)]
    body = []
    for n, r in enumerate(rows, 1):
        note = " · ".join(x for x in (r["code"], r["term"], r["purchaser"]) if x)
        line = [
            kit.cell(str(n)),
            kit.cell(r["supplier"], note),
            kit.cell(str(r["bills"]), right=True),
        ]
        for i, v in enumerate(r["b"]):
            red = i >= 3 and float(v) > 0 and not a.by_bill
            line.append(
                kit.p(
                    f'<font color="{RED if red else INK}">{kit.t(_inr(v, True))}</font>',
                    size=8.4,
                    align="right",
                )
            )
        line += [
            kit.cell(_inr(r["due"]), right=True, bold=True),
            kit.cell(str(r["oldest"] or ""), right=True),
        ]
        body.append(line)
    body.append(
        [
            kit.cell(""),
            kit.cell(
                f"Total · {totals['suppliers']} supplier{'' if totals['suppliers'] == 1 else 's'}",
                bold=True,
            ),
            kit.cell(str(totals["bills"]), right=True, bold=True),
        ]
        + [kit.cell(_inr(v), right=True, bold=True) for v in totals["b"]]
        + [kit.cell(_inr(totals["due"]), right=True, bold=True), kit.cell("")]
    )
    fixed = [22, None, 34] + [68] * 5 + [78, 70]
    rest = width - sum(w for w in fixed if w)
    story.append(_grid(kit, heads, body, [w or rest for w in fixed]))
    if params.get("layout") == "bills":
        bill_rows, _t, groups = payables.bills_view(company, params, a)
        order = {r["id"]: n for n, r in enumerate(rows)}
        bill_rows.sort(key=lambda r: (order.get(r["supplier_id"], 1e9), r["bill_date"]))
        story += [
            PageBreak(),
            kit.p(
                f"Accounts Payable with Bills · As on {_dmy(a.as_on)}",
                size=11,
                lead=14,
                bold=True,
                colour=DEEP,
            ),
            Spacer(1, 5),
        ]
        body, group_rows, sub_rows = [], [], []
        current = None
        for r in bill_rows:
            if r["supplier_id"] != current:
                if current is not None:
                    body.append(_subtotal(kit, groups[current]))
                    sub_rows.append(len(body))
                current = r["supplier_id"]
                body.append(
                    [
                        kit.p(
                            kit.t(
                                " · ".join(x for x in (r["supplier"], r["code"], r["term"]) if x)
                            ),
                            size=8.6,
                            bold=True,
                            colour=DEEP,
                        )
                    ]
                    + [""] * 8
                )
                group_rows.append(len(body))
            body.append(_bill_cells(kit, r))
        if current is not None:
            body.append(_subtotal(kit, groups[current]))
            sub_rows.append(len(body))
        widths = [width * x for x in (0.17, 0.08, 0.08, 0.11, 0.12, 0.12, 0.12, 0.11, 0.09)]
        story.append(
            _grid(kit, BILL_HEADS, body, widths, groups=group_rows, subtotals=sub_rows, total=False)
        )
    footer = " · ".join(["Accounts Payable", company.name, *scope, f"As on {_dmy(a.as_on)}"])
    return _build(
        story,
        landscape=True,
        footer_text=footer,
        mark=print_mark.mark(company),
        title="Accounts Payable",
    )


def _subtotal(kit: _Kit, g: dict) -> list:
    return (
        [kit.cell("Supplier total", bold=True), "", ""]
        + [
            kit.cell(_inr(g[k], k != "amount" and k != "balance"), right=True, bold=True)
            for k in ("amount", "tds", "dn", "paid", "balance")
        ]
        + [""]
    )


def _supplier_box(kit: _Kit, ledger: Ledger) -> list:
    party = ledger.party
    out = [
        kit.p("ACCOUNT OF", size=7.2, lead=10, bold=True, colour=LEAF),
        kit.p(f"<b>{kit.t(ledger.name)}</b>", size=9.4, lead=13),
    ]
    place = None
    if party:
        place = party.addresses.filter(is_billing=True).first() or party.addresses.first()
    if place:
        lines = [x.strip() for x in place.address.split("\n") if x.strip()]
        city = place.city + (f" - {place.pincode}" if place.pincode else "")
        if city.strip(" -"):
            lines.append(city)
        state = india.STATES.get(place.state_code, "")
        lines.append(
            " - ".join(
                x for x in (f"{state} ({place.state_code})" if state else "", place.country) if x
            )
        )
        out.append(kit.p("<br/>".join(kit.t(x) for x in lines), size=8.8, lead=12.5))
    facts = []
    if party:
        facts += [
            ("GSTIN", (place.gstin if place and place.gstin else party.gstin)),
            ("PAN", party.pan),
        ]
        code = party.vendor_number
        term = party.credit_term.name if party.credit_term_id else ""
        facts.append(
            ("Code", " · ".join(x for x in (code, f"Credit Term {term}" if term else "") if x))
        )
    rows = [f'<font color="{GREEN}"><b>{k}</b></font>&nbsp;&nbsp;{kit.t(v)}' for k, v in facts if v]
    if rows:
        out.append(kit.p("<br/>".join(rows), size=8.8, lead=13))
    return out


def supplier_pdf(company, ledger: Ledger, params) -> bytes:
    """Outstanding Bills for one supplier, to send to them."""
    from reportlab.lib import colors
    from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle

    kit = _Kit()
    kit.size, kit.pad = 7.6, 3
    a = payables.asked(params)
    a.supplier = ledger.pk
    a.branch = None
    a.purchaser = None
    a.overdue = False
    rows, totals, _g = payables.bills_view(company, {}, a)
    sums = payables.supplier_rows(payables.report_bills(company, a))
    b = [payables.money(v) for v in sums[0]["b"]] if sums else ["0.00"] * 5
    overdue = payables.money(sums[0]["overdue"]) if sums else "0.00"
    width = _width(False)
    lh = _letterhead(company)
    story = [
        _heading(
            kit,
            lh,
            "OUTSTANDING BILLS",
            [f"As on {_dmy(a.as_on)}", f"Printed {_dmy(datetime.date.today())}"],
            width,
        ),
        Spacer(1, 10),
    ]
    less = sum(float(totals[k]) for k in ("tds", "dn", "paid"))
    summary = [
        ("Bills open", str(totals["bills"])),
        ("Bill amounts", _inr(totals["amount"])),
        ("Less TDS, debit notes, payments", _inr(f"{less:.2f}")),
        ("Of which overdue", _inr(overdue)),
    ]
    sum_rows = [
        [kit.p(kit.t(k), size=8.8), kit.p(kit.t(v), size=8.8, align="right")] for k, v in summary
    ]
    balance = totals["balance"]
    side = "Cr" if float(balance) >= 0 else "Dr"
    sum_rows.append(
        [
            kit.p("Balance Payable", size=10, bold=True, colour=DEEP),
            kit.p(
                kit.t(f"{_inr(balance.lstrip('-'))} {side}"),
                size=10,
                bold=True,
                colour=DEEP,
                align="right",
            ),
        ]
    )
    sum_table = Table(sum_rows, colWidths=[None, 90])
    sum_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LINEABOVE", (0, -1), (-1, -1), 1.6, colors.HexColor(LEAF)),
                ("TOPPADDING", (0, -1), (-1, -1), 5),
            ]
        )
    )
    boxes = Table(
        [
            [
                _supplier_box(kit, ledger),
                "",
                [kit.p("SUMMARY", size=7.2, lead=10, bold=True, colour=LEAF), sum_table],
            ]
        ],
        colWidths=[width * 0.55, 10, None],
    )
    boxes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(CARD)),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor(CARD)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )
    owe = (
        f"As per our books, <b>we owe you ₹{kit.t(_inr(balance))}</b> on {_dmy(a.as_on)} "
        "against the bills below."
        if float(balance) >= 0
        else f"As per our books, <b>you owe us ₹{kit.t(_inr(balance.lstrip('-')))}</b> "
        f"on {_dmy(a.as_on)}."
    )
    story += [
        boxes,
        Spacer(1, 8),
        kit.p("IN PLAIN WORDS", size=7.2, lead=10, bold=True, colour=LEAF),
        kit.p(owe, size=9.4, lead=13),
        Spacer(1, 6),
    ]
    heads = [("Your Bill No / Our Entry", False)] + BILL_HEADS[1:]
    body = [_bill_cells(kit, r) for r in rows]
    body.append(
        [
            kit.cell(
                f"Total · {totals['bills']} open bill{'' if totals['bills'] == 1 else 's'}",
                bold=True,
            ),
            "",
            "",
        ]
        + [
            kit.cell(_inr(totals[k], k not in ("amount", "balance")), right=True, bold=True)
            for k in ("amount", "tds", "dn", "paid", "balance")
        ]
        + [""]
    )
    widths = [width * x for x in (0.15, 0.11, 0.11, 0.12, 0.08, 0.13, 0.08, 0.13, 0.09)]
    story.append(_grid(kit, heads, body, widths, span=3))
    story += [
        Spacer(1, 8),
        _strip(kit, a.labels, b, totals["balance"], width, a.by_bill, 9),
        Spacer(1, 10),
    ]
    mail = lh.get("email") or ""
    confirm = (
        "Please check these bills against your books and confirm the balance of "
        f"<b>₹{kit.t(_inr(balance.lstrip('-')))} {side}</b>"
        + (" (payable to you)" if side == "Cr" else "")
        + ", or send us the bills that differ, within 15 days"
        + (f" to {kit.t(mail)}" if mail else "")
        + ". TDS shown is deducted under the section named and will appear in your Form 26AS / 16A."
    )
    end = Table(
        [
            [
                [
                    kit.p("PLEASE CONFIRM", size=7.2, lead=10, bold=True, colour=LEAF),
                    kit.p(confirm, size=8.8, lead=12.5),
                ],
                "",
                [
                    kit.p(
                        kit.t(f"FOR {company.name.upper()}"),
                        size=7.2,
                        lead=10,
                        bold=True,
                        colour=LEAF,
                    ),
                    Spacer(1, 30),
                    kit.p("Authorised Signatory", size=8.8),
                ],
            ]
        ],
        colWidths=[width * 0.6, 10, None],
    )
    end.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 0.8, colors.HexColor("#CFE0D4")),
                ("BOX", (2, 0), (2, 0), 0.8, colors.HexColor("#CFE0D4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )
    story.append(KeepTogether([end]))
    footer = f"Outstanding Bills · {ledger.name} · As on {_dmy(a.as_on)}"
    return _build(
        story,
        landscape=False,
        footer_text=footer,
        mark=print_mark.mark(company),
        title="Outstanding Bills",
    )


def supplier_file(company, ledger: Ledger, params) -> tuple[str, bytes, str]:
    stem = printout._slug(f"outstanding-bills-{ledger.name}-{payables.asked(params).as_on}")
    return f"{stem}.pdf", supplier_pdf(company, ledger, params), "application/pdf"


def _supplier(company, pk: int) -> Ledger:
    ledger = (
        Ledger.objects.filter(company=company, party_side="supplier", pk=pk)
        .select_related("party__credit_term")
        .first()
    )
    if ledger is None:
        raise NotFound("No such supplier in this company.")
    return ledger


def _respond(data: bytes, name: str, params) -> HttpResponse:
    response = HttpResponse(data, content_type="application/pdf")
    how = "attachment" if params.get("download") == "1" else "inline"
    response["Content-Disposition"] = f'{how}; filename="{name}"'
    return response


class PayablesPdfView(APIView):
    """GET companies/<id>/accounts-payable/pdf/?layout=summary|bills and the
    report's own filters (&download=1 to download)."""

    permission_classes = [Signed]

    def get(self, request, pk: int):
        _check(request, VIEW)
        company = _company(request, pk)
        params = request.query_params
        data = management_pdf(company, params)
        stem = printout._slug(f"accounts-payable-{payables.asked(params).as_on}")
        return _respond(data, f"{stem}.pdf", params)


class SupplierPdfView(APIView):
    """GET companies/<id>/accounts-payable/suppliers/<ledger>/pdf/?as_on=&age_by="""

    permission_classes = [Signed]

    def get(self, request, pk: int, ledger: int):
        _check(request, VIEW)
        company = _company(request, pk)
        name, data, _kind = supplier_file(company, _supplier(company, ledger), request.query_params)
        return _respond(data, name, request.query_params)


class SupplierMailView(APIView):
    """ "Email Outstanding Statement": GET the draft (who it goes to, subject,
    message); POST {to, cc, subject, message} sends it from the company's mailbox
    with the Outstanding Bills PDF attached."""

    permission_classes = [Signed]

    def _contacts(self, ledger: Ledger):
        if not ledger.party_id:
            return []
        people = list(ledger.party.contacts.exclude(email="").order_by("-is_primary", "name"))
        # Accounts people first: a statement is for whoever keeps their books.
        return sorted(people, key=lambda c: "accounts" not in (c.kinds or []))

    def get(self, request, pk: int, ledger: int):
        from buying.api import SUBMIT
        from core import mail

        _check(request, SUBMIT)
        company = _company(request, pk)
        sup = _supplier(company, ledger)
        a = payables.asked(request.query_params)
        contacts = self._contacts(sup)
        acct = mail.account_of(company)
        return Response(
            {
                "supplier_name": sup.name,
                "mail_ready": bool(acct and acct.password),
                "from": acct.address if acct else "",
                "to": [{"name": c.name, "email": c.email} for c in contacts[:1]],
                "to_options": [
                    {"name": c.name, "email": c.email, "of": "Supplier"} for c in contacts
                ],
                "cc": [{"name": request.user.display_name, "email": request.user.email}]
                if request.user.email
                else [],
                "cc_options": [
                    {"name": c.name, "email": c.email, "of": "Supplier"} for c in contacts
                ],
                "subject": f"Outstanding bills as on {_dmy(a.as_on)}: {company.name}",
                "message": (
                    "Please find attached the list of your bills outstanding in our books "
                    f"as on {_dmy(a.as_on)}. Kindly check it against your books and confirm "
                    "the balance, or let us know the bills that differ."
                ),
                "signature": f"{request.user.display_name}\n{company.name}",
                "attachment": supplier_file(company, sup, request.query_params)[0],
            }
        )

    def post(self, request, pk: int, ledger: int):
        import html

        from buying.api import SUBMIT
        from buying.supplier_mail import _emails
        from core import mail

        _check(request, SUBMIT)
        company = _company(request, pk)
        sup = _supplier(company, ledger)
        data = request.data
        to = _emails(data.get("to"), "to")
        if not to:
            raise ValidationError({"to": ["Give at least one address to send to."]})
        cc = [e for e in _emails(data.get("cc"), "cc") if e not in to]
        subject = str(data.get("subject") or "").strip()[:200]
        if not subject:
            raise ValidationError({"subject": ["Give the subject."]})
        message = str(data.get("message") or "").strip()
        names = {c.email.lower(): c.name for c in self._contacts(sup)}
        greeting = names.get(to[0].lower(), "Sir/Madam")
        signature = f"{request.user.display_name}\n{company.name}"
        text = f"Dear {greeting},\n\n{message}\n\nRegards,\n{signature}\n"
        para = '<p style="margin:0 0 10px">{}</p>'
        body = (
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1f2933">'
            + "".join(
                para.format(html.escape(p).replace("\n", "<br>"))
                for p in [f"Dear {greeting},", *message.split("\n\n"), f"Regards,\n{signature}"]
                if p.strip()
            )
            + "</div>"
        )
        try:
            mail.send(
                company,
                to=to,
                cc=cc,
                subject=subject,
                text=text,
                html=body,
                reply_to=[request.user.email] if request.user.email else [],
                files=[supplier_file(company, sup, data)],
            )
        except mail.NotSetUp as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"sent_to": to, "cc": cc})
