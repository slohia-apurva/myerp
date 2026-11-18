"""The purchase order as a PDF made on the server, to attach to a mail (Sidharth,
2026-11-15). It follows the approved print (frontend PoPrint.tsx, mockups
13/14/18-20): letterhead band, Supplier / Bill To / Ship To boxes, the order's
details, the items (and charges) with headings repeated on every page, the tax
summary, totals, amount in words, import documents, terms in groups and the
signature. Later pages carry a short heading; each page "Page n of m".

The browser print stays the one people print from; this copy is for mail."""

from __future__ import annotations

import base64
import datetime
import io
from collections import OrderedDict
from decimal import Decimal

from django.utils import timezone

from core import printout

INK = "#1F2933"
DEEP = "#14532D"
LEAF = "#2E9E62"
MUTED = "#616E7C"
CARD = "#F3FAF6"
ALT = "#F6FAF8"
SUB = "#E3F2E9"
CARD_LINE = "#D6EBDD"


def _dmy(iso) -> str:
    return "-".join(reversed(str(iso)[:10].split("-"))) if iso else ""


def _plain(v) -> str:
    d = Decimal(str(v or 0))
    text = f"{d:,f}"
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return _indian_int(text)


def _indian_int(text: str) -> str:
    """1,234,567.5 → 12,34,567.5 (Indian grouping)."""
    sign = "-" if text.startswith("-") else ""
    text = text.lstrip("-").replace(",", "")
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return sign + whole + (f".{frac}" if frac else "")


def _bytes(data_url: str | None) -> bytes | None:
    if not data_url or "," not in data_url:
        return None
    try:
        return base64.b64decode(data_url.split(",", 1)[1])
    except ValueError:
        return None


def _image(data_url: str | None):
    from reportlab.lib.utils import ImageReader

    raw = _bytes(data_url)
    try:
        return ImageReader(io.BytesIO(raw)) if raw else None
    except Exception:  # noqa: BLE001  (a bad picture only leaves the space empty)
        return None


def order_pdf(o: dict) -> bytes:
    """`o` is the order as the order screen gets it (buying.api._order_out)."""
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
        LongTable,
        NextPageTemplate,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.platypus import Image as Picture

    regular, bold = printout._font_names()
    rupee = regular != "Helvetica"
    # So <b> inside a paragraph uses the bold face of our font.
    addMapping(regular, 0, 0, regular)
    addMapping(regular, 1, 0, bold)
    addMapping(regular, 0, 1, regular)
    addMapping(regular, 1, 1, bold)
    c = colors.HexColor

    def t(value) -> str:
        value = "" if value is None else str(value)
        value = value if rupee else value.replace("₹", "Rs ")
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def style(name, size=8, lead=None, font=None, colour=INK, align=None, **more):
        s = ParagraphStyle(
            name,
            fontName=font or regular,
            fontSize=size,
            leading=lead or size * 1.4,
            textColor=c(colour),
            **more,
        )
        if align == "right":
            s.alignment = TA_RIGHT
        elif align == "center":
            s.alignment = TA_CENTER
        return s

    body = style("body", 8)
    body_r = style("bodyr", 8, align="right")
    bold_s = style("bold", 8, font=bold)
    bold_r = style("boldr", 8, font=bold, align="right")
    muted = style("muted", 7.5, colour=MUTED)
    lab = style("lab", 6.5, font=bold, colour=LEAF)
    head = style("head", 7.5, font=bold, colour="#FFFFFF")
    head_r = style("headr", 7.5, font=bold, colour="#FFFFFF", align="right")
    sub_s = style("sub", 6.5, font=bold, colour=DEEP)

    lh = o["letterhead"]
    imp = o.get("import_details") or {}
    inr = o["currency"] == "INR"
    is_import = not inr or bool(imp)
    sym = o.get("currency_symbol") or ""
    lines = o.get("lines") or []
    charges = o.get("charges") or []
    gst = not is_import and (
        any(Decimal(x["gst_rate"] or 0) for x in lines)
        or any(Decimal(x["gst_rate"] or 0) for x in charges)
    )
    igst = Decimal(o["igst_total"] or 0) > 0

    def money(v) -> str:
        d = Decimal(str(v or 0)).quantize(Decimal("0.01"))
        return _indian_int(f"{d:f}") if inr else f"{d:,.2f}"

    def rate(v) -> str:
        d = Decimal(str(v or 0))
        places = Decimal("0.01") if inr and d == d.quantize(Decimal("0.01")) else Decimal("0.0001")
        q = d.quantize(places)
        return _indian_int(f"{q:f}") if inr else f"{q:,f}"

    page_w, page_h = A4
    left = right = 11 * mm
    width = page_w - left - right

    # --- first page heading -------------------------------------------------
    brand = Table(
        [
            [
                Paragraph(
                    t(lh["name"][:1]),
                    style("logo", 14, 16, bold, "#FFFFFF", "center"),
                ),
                Paragraph(t(lh["name"]), style("co", 12, 15, bold)),
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
    addr_lines = [x.strip().rstrip(",") for x in (lh.get("address") or "").split("\n") if x.strip()]
    lh_rows = []
    if addr_lines:
        first, rest = addr_lines[0], addr_lines[1:]
        second = ", ".join([*rest, lh.get("city") or ""]).strip(", ")
        if lh.get("pincode"):
            second += f" - {lh['pincode']}"
        lh_rows.append(f"Regd Office: {first}{',' if second else ''}")
        if second:
            lh_rows.append(second)
    contact = " · ".join(x for x in [lh.get("phone") and f"Ph {lh['phone']}", lh.get("email")] if x)
    if contact:
        lh_rows.append(contact)

    def facts(pairs):
        shown = [(k, v) for k, v in pairs if v]
        return " · ".join(f"<b>{k}</b> {t(v)}" for k, v in shown)

    lh_html = [t(x) for x in lh_rows]
    for pairs in (
        [("GSTIN", lh.get("gstin")), ("PAN", lh.get("pan"))],
        [("CIN", lh.get("cin")), ("FSSAI", lh.get("fssai")), ("IEC", is_import and lh.get("iec"))],
    ):
        if f := facts(pairs):
            lh_html.append(f)
    lh_par = Paragraph("<br/>".join(lh_html), style("lh", 7.5, 11, colour=MUTED))
    title_cell = [
        Paragraph("PURCHASE ORDER", style("h1", 16, 19, bold, DEEP, "right")),
        Paragraph(
            t(o["number"] or "Draft · number on Submit"), style("no", 11, 15, bold, INK, "right")
        ),
        Paragraph(f"Date {_dmy(o['order_date'])}", style("dt", 10, 13, align="right")),
    ]
    band = Table(
        [[[brand, Spacer(1, 5), lh_par], title_cell]],
        colWidths=[width * 0.6, width * 0.4],
    )
    band.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LINEBELOW", (0, 0), (-1, 0), 2.2, c(LEAF)),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    ab = o.get("addresses") or {}
    labels = {
        "gstin": "GSTIN",
        "taxid": "Tax ID",
        "fssai": "FSSAI",
        "iec": "IEC",
        "contact": "Contact",
        "phone": "Phone",
        "email": "Email",
    }

    def card(title: str, name: str, place: dict | None, keys: list[str], label=False, iec=""):
        parts = [Paragraph(title.upper(), lab)]
        if not place:
            parts.append(Paragraph(f"<b>{t(name)}</b>", body))
            return parts
        nm = (place.get("title") or name) if label else name
        rows = [f"<b>{t(nm)}</b>"]
        rows += [t(x) for x in (place.get("address") or "").split("\n") if x.strip()]
        if place.get("city") or place.get("pincode"):
            rows.append(t(" - ".join(x for x in [place.get("city"), place.get("pincode")] if x)))
        india = not place.get("country") or place.get("country") == "India"
        if india:
            state = place.get("state") and f"{place['state']} ({place.get('state_code', '')})"
            rows.append(t(" - ".join(x for x in [state, "India"] if x)))
        else:
            rows.append(t(place.get("country")))
        parts.append(Paragraph("<br/>".join(rows), style("addr", 7.5, 10.5)))
        fact_rows = []
        for k in keys:
            v = (
                place.get("gstin")
                if k == "taxid"
                else iec
                if k == "iec"
                else (place.get("email") or "").replace(", ", ",\n")
                if k == "email"
                else place.get(k)
            )
            if v:
                fact_rows.append(
                    [
                        Paragraph(labels[k], style("dtl", 7, 9.5, bold, DEEP)),
                        Paragraph(t(v).replace("\n", "<br/>"), style("dd", 7, 9.5)),
                    ]
                )
        if fact_rows:
            ft = Table(fact_rows, colWidths=[42, None])
            ft.setStyle(
                TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (-1, 0), 0.6, c(CARD_LINE)),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                        ("TOPPADDING", (0, 0), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                        ("TOPPADDING", (0, 0), (-1, 0), 4),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            parts.append(Spacer(1, 3))
            parts.append(ft)
        return parts

    if is_import:
        k_sup, k_bill, k_ship = (
            ["taxid", "contact", "phone", "email"],
            ["gstin", "iec", "contact", "phone"],
            ["gstin", "contact", "phone"],
        )
    else:
        k_sup = k_bill = k_ship = ["gstin", "fssai", "contact", "phone", "email"]
    gap = 10
    cw = (width - 2 * gap) / 3
    cards = Table(
        [
            [
                card("Supplier", o["supplier_name"], ab.get("supplier"), k_sup),
                "",
                card("Bill To", lh["name"], ab.get("bill_to"), k_bill, iec=lh.get("iec") or ""),
                "",
                card(
                    "Ship To",
                    (ab.get("ship_to") or {}).get("name") or lh["name"],
                    ab.get("ship_to"),
                    k_ship,
                    label=True,
                ),
            ]
        ],
        colWidths=[cw, gap, cw, gap, cw],
    )
    cards.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), c(CARD)),
                ("BACKGROUND", (2, 0), (2, 0), c(CARD)),
                ("BACKGROUND", (4, 0), (4, 0), c(CARD)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("LEFTPADDING", (3, 0), (3, 0), 0),
                ("RIGHTPADDING", (3, 0), (3, 0), 0),
            ]
        )
    )

    our = t(o.get("created_by_name") or "")
    if o.get("created_by_phone"):
        our += f"<br/>{t(o['created_by_phone'])}"

    def il(k):
        return imp.get(f"{k}_label") or ""

    if is_import:
        meta = [
            ("Currency", t(f"{o['currency']} ({sym})")),
            (
                "Incoterms",
                t(" ".join(x for x in [imp.get("incoterm"), imp.get("named_place")] if x)),
            ),
            ("Mode of Shipment", t(il("mode"))),
            ("Country of Origin", t(imp.get("origin") or "")),
            ("Port of Loading", t(imp.get("port_loading") or "")),
            ("Port of Discharge", t(imp.get("port_discharge") or "")),
            ("Latest Shipment", t(_dmy(imp.get("latest_shipment")))),
            ("Payment", t(" · ".join(x for x in [il("payment"), o.get("credit_term_name")] if x))),
            ("Partial Shipment", t(il("partial"))),
            ("Transhipment", t(il("transhipment"))),
            ("Insurance By", t(il("insurance_by"))),
            ("Our Contact", our),
        ]
        per_row = 4
    else:
        meta = [
            ("Expected", t(_dmy(o.get("expected_date")))),
            ("Credit Term", t(o.get("credit_term_name") or "")),
            ("Transporter", t(o.get("transporter_name") or "")),
            ("Your Quote", t(o.get("supplier_ref") or "")),
            ("Our Contact", our),
        ]
        per_row = 5
    meta = [(k, v) for k, v in meta if v]
    meta_rows = []
    for i in range(0, len(meta), per_row):
        chunk = meta[i : i + per_row]
        cells = [[Paragraph(k.upper(), lab), Paragraph(v, body)] for k, v in chunk]
        meta_rows.append(cells + [""] * (per_row - len(chunk)))
    meta_table = None
    if meta_rows:
        meta_table = Table(meta_rows, colWidths=[width / per_row] * per_row)
        meta_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

    # --- items ------------------------------------------------------------------
    units = {x["unit_name"] for x in lines}
    unit = next(iter(units)) if len(units) == 1 else ""
    qty_total = sum((Decimal(x["qty"]) for x in lines), Decimal(0))
    items_value = sum((Decimal(x["taxable"]) for x in lines), Decimal(0))
    charges_value = sum((Decimal(x["amount"]) for x in charges), Decimal(0))
    hsn_head = "HSN / SAC" if charges else "HSN"
    heads = ["#", "Item and Description", hsn_head, "Qty", "Unit", f"Rate {sym}"]
    if gst:
        heads.append("GST %")
    heads.append(f"{'Taxable Amount' if gst else 'Amount'} {sym}")
    ncol = len(heads)
    right_cols = {3, 5, ncol - 1} | ({6} if gst else set())
    data = [[Paragraph(t(h), head_r if i in right_cols else head) for i, h in enumerate(heads)]]
    styles = []
    for i, x in enumerate(lines):
        text = f"<b>{t(x['item_name'])} · {t(x['item_number'])}</b>"
        if x.get("supplier_code"):
            text += f"<br/><font size=7 color='#3E4C59'>Your code {t(x['supplier_code'])}</font>"
        if x.get("description"):
            d = t(x["description"]).replace("\n", "<br/>")
            text += f"<br/><font size=7 color='#3E4C59'>{d}</font>"
        r = rate(x["rate"])
        if Decimal(x.get("discount_pct") or 0) > 0:
            r += f"<br/><font size=7 color='#3E4C59'>less {_plain(x['discount_pct'])}%</font>"
        row = [
            Paragraph(str(i + 1), body),
            Paragraph(text, body),
            Paragraph(t(x["hsn"]), body),
            Paragraph(_plain(x["qty"]), body_r),
            Paragraph(t(x["unit_name"]), body),
            Paragraph(r, body_r),
        ]
        if gst:
            row.append(Paragraph(_plain(x["gst_rate"]), body_r))
        row.append(Paragraph(money(x["taxable"]), body_r))
        if i % 2:
            styles.append(("BACKGROUND", (0, len(data)), (-1, len(data)), c(ALT)))
        data.append(row)
    total_row = len(data)
    data.append(
        [
            "",
            Paragraph("Items Total" if charges else "Total", bold_s),
            "",
            Paragraph(_plain(qty_total) if charges and unit else "", bold_r),
            Paragraph(unit if charges else "", bold_s),
        ]
        + [""] * (ncol - 6)
        + [Paragraph(money(items_value), bold_r)]
    )
    styles.append(("LINEABOVE", (1, total_row), (-1, total_row), 0.8, c(DEEP)))
    if charges:
        sub_row = len(data)
        data.append([Paragraph("CHARGES", sub_s)] + [""] * (ncol - 1))
        styles += [
            ("SPAN", (0, sub_row), (-1, sub_row)),
            ("BACKGROUND", (0, sub_row), (-1, sub_row), c(SUB)),
        ]

        def basis(x) -> str:
            if x["basis"] == "fixed":
                return "Fixed"
            if x["basis"] == "percent":
                return f"{_plain(x['rate'])}% of items"
            return f"{sym}{money(x['rate'])} per {unit or 'unit'} × {_plain(qty_total)} {unit}"

        for i, x in enumerate(charges):
            n = len(data)
            row = [
                Paragraph(str(len(lines) + i + 1), body),
                Paragraph(f"<b>{t(x['item_name'])}</b>", body),
                Paragraph(t(x.get("sac") or ""), body),
                Paragraph(t(basis(x)), style("basis", 7.5, colour=MUTED, align="right")),
                "",
                "",
            ]
            if gst:
                row.append(Paragraph(_plain(x["gst_rate"]), body_r))
            row.append(Paragraph(money(x["amount"]), body_r))
            styles.append(("SPAN", (3, n), (5, n)))
            if i % 2:
                styles.append(("BACKGROUND", (0, n), (-1, n), c(ALT)))
            data.append(row)
        n = len(data)
        data.append(
            ["", Paragraph("Charges Total", bold_s)]
            + [""] * (ncol - 3)
            + [Paragraph(money(charges_value), bold_r)]
        )
        styles += [("SPAN", (1, n), (ncol - 2, n)), ("LINEABOVE", (1, n), (-1, n), 0.8, c(DEEP))]
    fixed = {0: 16, 2: 44, 3: 50, 4: 34, 5: 56, ncol - 1: 70}
    if gst:
        fixed[6] = 34
    item_w = width - sum(fixed.values())
    widths = [fixed.get(i, item_w) for i in range(ncol)]
    items = LongTable(data, colWidths=widths, repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), c(DEEP)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                *styles,
            ]
        )
    )

    # --- tax summary and totals -------------------------------------------------
    left_parts = []
    if gst:
        tax: OrderedDict[tuple, dict] = OrderedDict()
        for x in [
            *({"code": y["hsn"], **y} for y in lines),
            *({"code": y.get("sac") or "", "taxable": y["amount"], **y} for y in charges),
        ]:
            key = (x["code"], Decimal(x["gst_rate"] or 0))
            row = tax.setdefault(
                key,
                {"taxable": Decimal(0), "cgst": Decimal(0), "sgst": Decimal(0), "igst": Decimal(0)},
            )
            for k in ("cgst", "sgst", "igst"):
                row[k] += Decimal(x[k] or 0)
            row["taxable"] += Decimal(x["taxable"] if "taxable" in x else x["amount"])
        rates = {k[1] for k in tax}
        one = next(iter(rates)) if len(rates) == 1 else None
        half = f" {_plain(one / 2)}%" if one is not None else ""
        whole = f" {_plain(one)}%" if one is not None else ""

        def cs(name):
            return f"{name}{whole if name == 'IGST' else half}" if one is not None else f"{name} ₹"

        th = [hsn_head, "Taxable ₹"] + (["GST %"] if one is None else [])
        th += [cs("IGST")] if igst else [cs("CGST"), cs("SGST")]
        th.append("Tax ₹")
        mh = style("taxh", 7.5, colour=MUTED)
        mhr = style("taxhr", 7.5, colour=MUTED, align="right")
        tdata = [[Paragraph(t(h), mh if i == 0 else mhr) for i, h in enumerate(th)]]
        for (code, r), v in tax.items():
            row = [Paragraph(t(code), body), Paragraph(money(v["taxable"]), body_r)]
            if one is None:
                row.append(Paragraph(_plain(r), body_r))
            row += (
                [Paragraph(money(v["igst"]), body_r)]
                if igst
                else [Paragraph(money(v["cgst"]), body_r), Paragraph(money(v["sgst"]), body_r)]
            )
            row.append(Paragraph(money(v["cgst"] + v["sgst"] + v["igst"]), body_r))
            tdata.append(row)
        tstyle = [
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        if one is None:
            n = len(tdata)
            tot = [Paragraph("Total", bold_s), Paragraph(money(o["taxable_total"]), bold_r), ""]
            tot += (
                [Paragraph(money(o["igst_total"]), bold_r)]
                if igst
                else [
                    Paragraph(money(o["cgst_total"]), bold_r),
                    Paragraph(money(o["sgst_total"]), bold_r),
                ]
            )
            all_tax = sum(Decimal(o[k] or 0) for k in ("cgst_total", "sgst_total", "igst_total"))
            tot.append(Paragraph(money(all_tax), bold_r))
            tdata.append(tot)
            tstyle.append(("LINEABOVE", (0, n), (-1, n), 0.8, c(DEEP)))
        tax_table = Table(tdata, hAlign="LEFT")
        tax_table.setStyle(TableStyle(tstyle))
        left_parts += [Paragraph("TAX SUMMARY", lab), tax_table, Spacer(1, 8)]
    left_parts += [
        Paragraph("AMOUNT IN WORDS", lab),
        Paragraph(t(o.get("amount_words") or ""), body),
    ]
    if is_import:
        left_parts.append(
            Paragraph(
                "No GST on this order: import IGST and customs duty are paid on the bill of entry.",
                muted,
            )
        )
    tot_rows = []
    if charges:
        tot_rows += [("Items", money(items_value), False), ("Charges", money(charges_value), False)]
    if gst:
        tot_rows.append(("Taxable", money(o["taxable_total"]), bool(charges)))
        if igst:
            tot_rows.append(
                (f"IGST{whole}" if one is not None else "IGST", money(o["igst_total"]), False)
            )
        else:
            tot_rows.append(
                (f"CGST{half}" if one is not None else "CGST", money(o["cgst_total"]), False)
            )
            tot_rows.append(
                (f"SGST{half}" if one is not None else "SGST", money(o["sgst_total"]), False)
            )
    if inr:
        tot_rows.append(("Round Off", money(o["round_off"]), False))
    grand = f"Total{'' if inr else ' (' + o['currency'] + ')'}"
    tdata = [
        [Paragraph(t(k), bold_s if b else body), Paragraph(t(v), bold_r if b else body_r)]
        for k, v, b in tot_rows
    ]
    gi = len(tdata)
    tdata.append(
        [
            Paragraph(t(grand), style("g", 10.5, 13, bold)),
            Paragraph(t(f"{sym}{money(o['total'])}"), style("gr", 10.5, 13, bold, DEEP, "right")),
        ]
    )
    totals = Table(tdata, colWidths=[86, 94])
    totals.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), c(CARD)),
                ("LINEABOVE", (0, gi), (-1, gi), 1.5, c(LEAF)),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
            ]
        )
    )
    sums = Table([[left_parts, totals]], colWidths=[width - 196, 196])
    sums.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 16),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )

    # --- import documents, terms and signature ---------------------------------
    story_tail = [KeepTogether(sums)]
    docs = imp.get("documents_labels") or []
    if is_import and (docs or imp.get("packing")):
        dl = []
        if docs:
            dl = [Paragraph("DOCUMENTS REQUIRED", lab)] + [
                Paragraph(f"{i}. {t(d)}", body) for i, d in enumerate(docs, 1)
            ]
        pk = []
        if imp.get("packing"):
            pk = [
                Paragraph("PACKING AND MARKING", lab),
                Paragraph(t(imp["packing"]).replace("\n", "<br/>"), body),
            ]
        block = Table([[dl, pk]], colWidths=[width / 2, width / 2])
        block.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 14),
                ]
            )
        )
        story_tail.append(KeepTogether(block))

    groups = [["Terms and Conditions", []]]
    for raw in (o.get("terms") or "").split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s.endswith(":"):
            if len(groups) == 1 and not groups[0][1]:
                groups[0][0] = s[:-1]
            else:
                groups.append([s[:-1], []])
        else:
            groups[-1][1].append(s)
    shown = [g for g in groups if g[1]]
    terms_parts = []
    for title, items_ in shown:
        terms_parts.append(Paragraph(t(title).upper(), lab))
        terms_parts += [Paragraph(f"{i}. {t(x)}", body) for i, x in enumerate(items_, 1)]
        terms_parts.append(Spacer(1, 4))

    if o["status"] == "draft" or not o.get("submitted_at"):
        approved = "Not yet approved"
    else:
        when = o["submitted_at"]
        if isinstance(when, str):
            when = datetime.datetime.fromisoformat(when)
        when = timezone.localtime(when)
        who = f" by {o['submitted_by_name']}" if o.get("submitted_by_name") else ""
        approved = f"Approved{who} on {when:%d-%m-%Y %H:%M}"
    sign_img = _image(o.get("submitted_by_signature"))
    sign = [Paragraph(f"For {t(lh['name'])}", style("for", 8, align="center"))]
    if sign_img is not None:
        iw, ih = sign_img.getSize()
        h = 30
        w = min(150, h * iw / ih)
        sign.append(
            Picture(io.BytesIO(_bytes(o["submitted_by_signature"])), width=w, height=w * ih / iw)
        )
    else:
        sign.append(Spacer(1, 30))
    line = Table(
        [
            [Paragraph("Authorised Signatory", style("as", 8, align="center"))],
            [Paragraph(t(approved), style("ap", 7.5, colour=MUTED, align="center"))],
        ],
        colWidths=[200],
    )
    line.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.7, c("#333333")),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    sign.append(line)
    end = Table([[terms_parts or "", sign]], colWidths=[width - 216, 216])
    end.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (0, 0), "TOP"),
                ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    story_tail.append(end)

    # --- pages --------------------------------------------------------------------
    mark = _image(lh.get("mark"))
    watermark = {"draft": "DRAFT", "cancelled": "CANCELLED"}.get(o["status"], "")
    foot = (
        "Draft purchase order · not valid until submitted"
        if o["status"] == "draft"
        else f"{o['number']} · Computer-generated purchase order"
    )
    short_h = 26 * mm

    def background(canvas, doc) -> None:
        canvas.saveState()
        if watermark:
            canvas.setFont(bold, 110 if watermark == "DRAFT" else 72)
            canvas.setFillColor(c("#DC2626"), alpha=0.1)
            canvas.translate(page_w / 2, page_h / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, -30, watermark)
        canvas.restoreState()

    def first_page(canvas, doc) -> None:
        background(canvas, doc)
        if mark is not None:
            iw, ih = mark.getSize()
            h = 13 * mm
            w = h * iw / ih
            canvas.drawImage(mark, (page_w - w) / 2, page_h - 9 * mm - h, w, h, mask="auto")

    def later_page(canvas, doc) -> None:
        background(canvas, doc)
        canvas.saveState()
        top = page_h - 12 * mm
        canvas.setFillColor(c(LEAF))
        canvas.roundRect(left, top - 24, 24, 24, 5, stroke=0, fill=1)
        canvas.setFillColor(c("#FFFFFF"))
        canvas.setFont(bold, 14)
        canvas.drawCentredString(left + 12, top - 17, lh["name"][:1])
        canvas.setFillColor(c(INK))
        canvas.setFont(bold, 12)
        canvas.drawString(left + 32, top - 16, lh["name"])
        x = page_w - right
        canvas.setFillColor(c(DEEP))
        canvas.setFont(bold, 11)
        canvas.drawRightString(x, top - 8, "PURCHASE ORDER")
        canvas.setFillColor(c(INK))
        canvas.setFont(bold, 9)
        canvas.drawRightString(x, top - 19, f"{o['number'] or 'Draft'} · {_dmy(o['order_date'])}")
        canvas.setFillColor(c(MUTED))
        canvas.setFont(regular, 8)
        canvas.drawRightString(x, top - 29, f"{o['supplier_name']} · continued")
        canvas.setStrokeColor(c(LEAF))
        canvas.setLineWidth(2.2)
        canvas.line(left, top - 35, page_w - right, top - 35)
        canvas.restoreState()

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
    frame1 = Frame(left, bottom, width, page_h - 12 * mm - bottom, 0, 0, 0, 0, id="f1")
    frame2 = Frame(left, bottom, width, page_h - 12 * mm - short_h - bottom, 0, 0, 0, 0, id="f2")
    out = io.BytesIO()
    doc = BaseDocTemplate(
        out,
        pagesize=A4,
        title=f"{o['number'] or 'Draft purchase order'} - {o['supplier_name']}",
        author=lh["name"],
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=[frame1], onPage=first_page),
            PageTemplate(id="later", frames=[frame2], onPage=later_page),
        ]
    )
    story = [NextPageTemplate("later"), band, Spacer(1, 12), cards, Spacer(1, 10)]
    if meta_table is not None:
        story.append(meta_table)
    story += [items, *story_tail]
    doc.build(story, canvasmaker=printout._numbered_canvas(footer))
    return out.getvalue()
