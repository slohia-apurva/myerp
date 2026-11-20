"""The pick list as the stores print it (Sidharth, 2026-11-20, preview 8).

Portrait A4 in the look of the sales order and PO prints: the company at the
top left, PICK LIST with its number and a barcode of the number at the right;
one row of facts (sales order, customer, Despatch From, delivery date,
transporter); an amber note when not all is in stock; then the rows sorted bin
by bin, each bin printed large with its barcode (the same LOC code as the GRN
bin sheets), the item, batch and expiry, the quantity to pick in the order's
unit (the stock unit under it when they differ), a tick box and a space to
write what was picked. What could not be found is listed in red after them,
then the "Picked By", "Checked By" and "Date and Time" lines. Each page says
"Page n of m"; the company's image prints at the top of page 1 when it prints
one.
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.utils import timezone

from buying.po_pdf import DEEP, INK, LEAF, MUTED, _dmy, _image
from core import printout

RED = "#B91C1C"
AMBER_BG = "#FFF8E6"
AMBER_LINE = "#F3D58A"
AMBER_INK = "#7A4B00"
ROW_LINE = "#D9E2DC"
SHORT_BG = "#FDF0F0"


def bin_rows(data: dict) -> list[tuple[dict, dict]]:
    """(item, row) pairs in the order the picker walks: bin by bin, then line."""
    rows = [(i, r) for i in data["items"] for r in i["rows"]]
    return sorted(
        rows,
        key=lambda x: (
            x[1]["location_name"].lower(),
            x[0]["position"],
            x[1].get("batch_number", ""),
            x[1].get("package_number") or "~",
        ),
    )


def pick_pdf(data: dict, letterhead: dict, transporter: str) -> bytes:
    """`data` is the list as its screen gets it (selling.pick_lists.pick_out)."""
    from reportlab.graphics.barcode.code128 import Code128
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        KeepTogether,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    regular, bold = printout._font_names()
    for b, i in ((0, 0), (1, 0), (0, 1), (1, 1)):
        addMapping(regular, b, i, bold if b else regular)
    c = colors.HexColor

    def t(value) -> str:
        value = "" if value is None else str(value)
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def style(name, size=8, lead=None, font=None, colour=INK, align=None):
        s = ParagraphStyle(
            name, fontName=font or regular, fontSize=size, leading=lead or size * 1.3
        )
        s.textColor = c(colour)
        if align == "right":
            s.alignment = TA_RIGHT
        elif align == "center":
            s.alignment = TA_CENTER
        return s

    lh = letterhead
    page_w, page_h = A4
    left = right = 14 * mm
    width = page_w - left - right

    # --- heading ----------------------------------------------------------------
    brand = Table(
        [
            [
                Paragraph(t(lh["name"][:1]), style("logo", 14, 16, bold, "#FFFFFF", "center")),
                Paragraph(t(lh["name"]), style("co", 13, 16, bold)),
            ]
        ],
        colWidths=[24, None],
    )
    brand.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), c(LEAF)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 4),
                ("BOTTOMPADDING", (0, 0), (0, 0), 4),
                ("LEFTPADDING", (1, 0), (1, 0), 8),
            ]
        )
    )
    made = timezone.localtime(data["created_at"]) if data.get("created_at") else None
    number_code = Code128(data["number"], barWidth=0.75, barHeight=24, humanReadable=False)
    number_code.hAlign = "RIGHT"
    title = [
        Paragraph("PICK LIST", style("h1", 18, 21, bold, DEEP, "right")),
        Paragraph(t(data["number"]), style("no", 11, 14, bold, INK, "right")),
        Paragraph(
            f"Made {made:%d-%m-%Y %-I:%M %p}".replace("AM", "am").replace("PM", "pm")
            if made
            else "",
            style("dt", 9, 12, align="right"),
        ),
        Spacer(1, 3),
        number_code,
    ]
    band = Table([[brand, title]], colWidths=[width * 0.55, width * 0.45])
    band.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (0, 0), "TOP"),
                ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
                ("LINEBELOW", (0, 0), (-1, 0), 2.2, c(LEAF)),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    lab = style("lab", 6.5, font=bold, colour=LEAF)
    val = style("val", 8.5, 11)
    fact_pairs = [
        ("Sales Order", data["order_number"]),
        ("Customer", data["customer_name"]),
        ("Despatch From", data["despatch_from"]),
        ("Delivery Date", _dmy(data.get("delivery_date"))),
        ("Transporter", transporter),
    ]
    facts = Table(
        [[[Paragraph(k.upper(), lab), Paragraph(t(v) or "-", val)] for k, v in fact_pairs]],
        colWidths=[width / 5] * 5,
    )
    facts.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story = [band, facts, Spacer(1, 8)]
    if not data["all_in"]:
        head, _, rest = data["text"].partition(":")
        note = Table(
            [[Paragraph(f"<b>{t(head)}:</b>{t(rest)}", style("note", 8.5, 11, colour=AMBER_INK))]],
            colWidths=[width],
        )
        note.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), c(AMBER_BG)),
                    ("BOX", (0, 0), (-1, -1), 0.8, c(AMBER_LINE)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story += [note, Spacer(1, 8)]

    # --- rows, bin by bin -------------------------------------------------------
    section = style("sec", 8.5, 11, bold, DEEP)
    rows = bin_rows(data)

    def tick_box():
        d = Drawing(14, 14)
        d.add(Rect(1, 1, 12, 12, strokeColor=c(INK), strokeWidth=1, fillColor=None, rx=1.5))
        return d

    def bin_cell(r):
        code = f"LOC-{r['location']:06d}"
        bars = Code128(code, barWidth=0.62, barHeight=18, humanReadable=False, quiet=False)
        bars.hAlign = "LEFT"
        return [
            Paragraph(t(r["location_name"]), style("bin", 13, 15, bold)),
            Spacer(1, 2),
            bars,
            Spacer(1, 2),
            Paragraph(code, style("loc", 6.5, 8, colour=MUTED)),
        ]

    def package_cell(i, r):
        if not r.get("package_number"):
            return Paragraph("No package", style("np", 7.5, 9, colour=MUTED))
        bars = Code128(
            r["package_number"], barWidth=0.55, barHeight=14, humanReadable=False, quiet=False
        )
        bars.hAlign = "LEFT"
        opened = Decimal(r["qty"]) < Decimal(r["package_left"] or "0")
        under = (
            Paragraph(
                f"OPEN: take {t(r['qty'])} of {t(r['package_left'])} {t(i['stock_unit_name'])}",
                style("op", 7, 8.5, bold, AMBER_INK),
            )
            if opened
            else Paragraph(t(r["package_label"]), style("pl", 7, 8.5, colour=MUTED))
        )
        return [
            Paragraph(t(r["package_number"]), style("pk", 8.5, 10, bold)),
            bars,
            Spacer(1, 2),
            under,
        ]

    if rows:
        cols = [22, width * 0.19, None, width * 0.13, width * 0.17, width * 0.15, width * 0.1]
        head_s = style("th", 7.5, 9, bold, "#FFFFFF")
        table = [
            [
                "",
                Paragraph("Bin", head_s),
                Paragraph("Item", head_s),
                Paragraph("Batch · Expiry", head_s),
                Paragraph("Package", head_s),
                Paragraph("Pick", style("thr", 7.5, 9, bold, "#FFFFFF", "right")),
                Paragraph("Picked", head_s),
            ]
        ]
        seen: dict[int, int] = {}
        last_bin = None
        for i, r in rows:
            seen[i["order_line"]] = seen.get(i["order_line"], 0) + 1
            again = seen[i["order_line"]] > 1
            note = f"Line {i['position']} · " + (
                f"rest of {i['ordered']} {i['unit_name']}"
                if again
                else f"ordered {i['ordered']} {i['unit_name']}"
            )
            batch = [Paragraph(t(r["batch_number"]) or "-", style("b", 8.5, 11))]
            if r["expiry"]:
                batch.append(
                    Paragraph(f"exp {_dmy(r['expiry'])}", style("e", 7.5, 9, colour=MUTED))
                )
            qty = [
                Paragraph(
                    f"{t(r['qty_unit'])} {t(i['unit_name'])}",
                    style("q", 12, 14, bold, INK, "right"),
                )
            ]
            if i["factor"] != "1":
                qty.append(
                    Paragraph(
                        f"{t(r['qty'])} {t(i['stock_unit_name'])}",
                        style("qs", 7.5, 9, colour=MUTED, align="right"),
                    )
                )
            new_bin = r["location"] != last_bin
            last_bin = r["location"]
            table.append(
                [
                    tick_box(),
                    bin_cell(r) if new_bin else "",
                    [
                        Paragraph(t(i["item_name"]), style("it", 9, 11, bold)),
                        Paragraph(t(note), style("ln", 7.5, 9.5, colour=MUTED)),
                    ],
                    batch,
                    package_cell(i, r),
                    qty,
                    "",
                ]
            )
        grid = Table(table, colWidths=cols, repeatRows=1)
        grid.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), c(DEEP)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.6, c(ROW_LINE)),
                    # the write-in line
                    ("LINEBELOW", (6, 1), (6, -1), 0.6, c(MUTED)),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (6, 1), (6, -1), 18),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (5, 0), (5, -1), 10),
                ]
            )
        )
        story += [Paragraph("PICK IN THIS ORDER (BIN BY BIN)", section), Spacer(1, 4), grid]
    else:
        story.append(Paragraph("Nothing to pick from stock.", style("none", 9, 12, colour=MUTED)))

    shorts = [i for i in data["items"] if i["short"] != "0"]
    if shorts:
        lines = []
        for i in shorts:
            stock = (
                f" ({t(i['short_stock'])} {t(i['stock_unit_name'])})" if i["factor"] != "1" else ""
            )
            lines.append(
                [
                    Paragraph(t(i["item_name"]), style("si", 9, 11, bold)),
                    Paragraph(
                        f"ordered {t(i['ordered'])} {t(i['unit_name'])} · "
                        f"found {t(i['picked'])} {t(i['unit_name'])}",
                        style("sf", 8.5, 11),
                    ),
                    Paragraph(
                        f"short {t(i['short'])} {t(i['unit_name'])}{stock}",
                        style("ss", 11, 13, bold, RED, "right"),
                    ),
                ]
            )
        short_t = Table(lines, colWidths=[width * 0.3, width * 0.35, width * 0.35])
        short_t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), c(SHORT_BG)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.6, c(ROW_LINE)),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(
            KeepTogether(
                [
                    Spacer(1, 12),
                    Paragraph("SHORT: NOT FOUND IN STOCK", section),
                    Spacer(1, 4),
                    short_t,
                ]
            )
        )

    sign = style("sign", 8.5, 11, align="center")
    gap = width * 0.05
    signs = Table(
        [["", "", "", "", ""], [Paragraph(x, sign) if x else "" for x in
                                ("Picked By", "", "Checked By", "", "Date and Time")]],
        colWidths=[(width - 2 * gap) / 3, gap, (width - 2 * gap) / 3, gap, (width - 2 * gap) / 3],
        rowHeights=[34, None],
    )  # fmt: skip
    signs.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (0, 0), 0.8, c(INK)),
                ("LINEBELOW", (2, 0), (2, 0), 0.8, c(INK)),
                ("LINEBELOW", (4, 0), (4, 0), 0.8, c(INK)),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(KeepTogether([Spacer(1, 24), signs]))

    # --- pages ------------------------------------------------------------------
    mark = _image(lh.get("mark"))
    printed = timezone.localtime()
    foot = (
        f"{data['number']} · Sales Order {data['order_number']} · printed "
        + f"{printed:%d-%m-%Y %-I:%M %p}".replace("AM", "am").replace("PM", "pm")
    )

    def first_page(canvas, doc) -> None:
        if mark is not None:
            iw, ih = mark.getSize()
            h = 13 * mm
            w = h * iw / ih
            canvas.drawImage(mark, (page_w - w) / 2, page_h - 9 * mm - h, w, h, mask="auto")

    def footer(canvas, number: int, total: int) -> None:
        canvas.saveState()
        canvas.setFont(regular, 7)
        canvas.setFillColor(c("#7B8794"))
        canvas.drawString(left, 7 * mm, foot)
        canvas.setFont(bold, 8)
        canvas.setFillColor(c(DEEP))
        canvas.drawRightString(page_w - right, 7 * mm, f"Page {number} of {total}")
        canvas.restoreState()

    bottom = 16 * mm
    top = 24 * mm if mark is not None else 14 * mm
    frame1 = Frame(left, bottom, width, page_h - top - bottom, 0, 0, 0, 0, id="f1")
    frame2 = Frame(left, bottom, width, page_h - 14 * mm - bottom, 0, 0, 0, 0, id="f2")
    out = io.BytesIO()
    doc = BaseDocTemplate(out, pagesize=A4, title=f"Pick List {data['number']}", author=lh["name"])
    doc.addPageTemplates(
        [
            PageTemplate(
                id="first", frames=[frame1], onPage=first_page, autoNextPageTemplate="later"
            ),
            PageTemplate(id="later", frames=[frame2]),
        ]
    )
    doc.build(story, canvasmaker=printout._numbered_canvas(footer))
    return out.getvalue()
