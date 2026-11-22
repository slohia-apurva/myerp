"""Print and PDF: every list screen's columnar report as a PDF.

A screen sends what it shows: a title, the company or group it is for, and
one or more tables (sheets) of column headings and rows of text. Masters send
the same tables as their export (core/exchange.py). The PDF is landscape A4,
headings repeat on every page, numbers sit on the right, and each page says
"Page n of m".

The browser's own print (Print button) shows the same report from the same
tables; this file only makes the PDF.
"""

from __future__ import annotations

import datetime
import io
import re
from pathlib import Path

from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from core.api import Signed

MAX_ROWS = 20000
GREEN = "#1F5E3B"
SLATE = "#52606D"
LINE = "#CBD2D9"
HEAD_FILL = "#E3F2E8"

# Fonts with the rupee sign. DejaVu comes with Linux (fonts-dejavu-core in the
# image); without it the built-in Helvetica is used and ₹ is written "Rs".
FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu")
_fonts: tuple[str, str] | None = None


def _font_names() -> tuple[str, str]:
    global _fonts
    if _fonts is None:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        _fonts = ("Helvetica", "Helvetica-Bold")
        for folder in FONT_DIRS:
            regular, bold = Path(folder, "DejaVuSans.ttf"), Path(folder, "DejaVuSans-Bold.ttf")
            if regular.exists() and bold.exists():
                pdfmetrics.registerFont(TTFont("MyERP", str(regular)))
                pdfmetrics.registerFont(TTFont("MyERP-Bold", str(bold)))
                _fonts = ("MyERP", "MyERP-Bold")
                break
    return _fonts


NUMBER = re.compile(r"^-?[₹]?\s?[\d,]+(\.\d+)?( (Dr|Cr))?$")


def numeric(column: list[str]) -> bool:
    values = [v for v in column if v and v != "—"]
    return bool(values) and all(NUMBER.match(v) for v in values)


def indian(value: str) -> str:
    """12345678.50 -> 1,23,45,678.50, as amounts are written in India."""
    m = re.fullmatch(r"(-?)(\d+)(\.\d+)?", value)
    if not m:
        return value
    sign, whole, frac = m.group(1), m.group(2), m.group(3) or ""
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    return f"{sign}{whole}{frac}"


def _clean(sheets) -> list[dict]:
    if not isinstance(sheets, list) or not sheets:
        raise ValidationError({"sheets": ["Send at least one table."]})
    out, total = [], 0
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise ValidationError({"sheets": ["Each table needs columns and rows."]})
        columns = [str(c) for c in sheet.get("columns") or []]
        rows = [[("" if v is None else str(v)) for v in r] for r in sheet.get("rows") or []]
        if not columns:
            raise ValidationError({"sheets": ["Each table needs its column headings."]})
        total += len(rows)
        rows = [(r + [""] * len(columns))[: len(columns)] for r in rows]
        text = [i for i in sheet.get("text") or [] if isinstance(i, int)]
        out.append(
            {"title": str(sheet.get("title") or ""), "columns": columns, "rows": rows, "text": text}
        )
    if total > MAX_ROWS:
        raise ValidationError({"sheets": [f"Print at most {MAX_ROWS} rows at a time."]})
    return out


def pdf(title: str, scope: str, sheets: list[dict], mark: bytes | None = None) -> bytes:
    """The report as a PDF file; `mark` is the small image printed at the top
    centre of the first page (core/print_mark.py), if any."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        TableStyle,
    )

    sheets = _clean(sheets)
    regular, bold = _font_names()
    rupee = regular != "Helvetica"

    def text(value: str) -> str:
        value = value if rupee else value.replace("₹", "Rs ")
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    cell = ParagraphStyle("cell", fontName=regular, fontSize=8, leading=10)
    cell_right = ParagraphStyle("cellr", parent=cell, alignment=TA_RIGHT)
    head = ParagraphStyle("head", fontName=bold, fontSize=8, leading=10, textColor=SLATE)
    head_right = ParagraphStyle("headr", parent=head, alignment=TA_RIGHT)
    h1 = ParagraphStyle("h1", fontName=bold, fontSize=15, leading=19, textColor=GREEN)
    h2 = ParagraphStyle("h2", fontName=bold, fontSize=11, leading=14, textColor=GREEN)
    sub = ParagraphStyle("sub", fontName=regular, fontSize=9, leading=12, textColor=SLATE)

    page = landscape(A4)
    margin = 12 * mm
    width = page[0] - 2 * margin
    printed = datetime.date.today().strftime("%d %b %Y")
    story = [
        Paragraph(text(title), h1),
        Paragraph(text(" · ".join(x for x in (scope, f"printed {printed}") if x)), sub),
        Spacer(1, 4 * mm),
    ]
    for n, sheet in enumerate(sheets):
        columns, rows = sheet["columns"], sheet["rows"]
        if n > 0 or len(sheets) > 1 and sheet["title"] and sheet["title"] != title:
            if n > 0:
                story.append(Spacer(1, 6 * mm))
            story.append(Paragraph(text(sheet["title"]), h2))
            story.append(Spacer(1, 2 * mm))
        # "text": columns that only look like numbers (an HSN code such as 0902).
        words = set(sheet.get("text", ()))
        right = [i not in words and numeric([r[i] for r in rows]) for i in range(len(columns))]
        rows = [[indian(v) if right[i] else v for i, v in enumerate(r)] for r in rows]
        # Width by content: the longest of the heading and the first rows,
        # within limits, scaled to the page.
        # Never narrower than the longest word, so words do not break.
        want, least = [], []
        for i, c in enumerate(columns):
            texts = [c] + [r[i] for r in rows[:300]]
            want.append(min(max(max(len(t) for t in texts), 4), 40))
            least.append(max(len(w) for t in texts for w in (t.split() or [""])) + 1)
        unit = width / sum(want)
        widths = [max(w * unit, n * 5.4) for w, n in zip(want, least, strict=True)]
        if sum(widths) > width:
            widths = [w * width / sum(widths) for w in widths]
        data = [
            [Paragraph(text(c), head_right if right[i] else head) for i, c in enumerate(columns)]
        ]
        for r in rows:
            data.append(
                [Paragraph(text(v), cell_right if right[i] else cell) for i, v in enumerate(r)]
            )
        if not rows:
            data.append([Paragraph("Nothing to show.", cell)] + [""] * (len(columns) - 1))
        table = LongTable(data, colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEAD_FILL)),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(table)

    out = io.BytesIO()
    picture = ImageReader(io.BytesIO(mark)) if mark else None

    def footer(canvas, number: int, total: int) -> None:
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor(SLATE))
        line = f"{title} · {scope}" if scope else title
        canvas.drawString(margin, 7 * mm, line if rupee else line.replace("₹", "Rs "))
        canvas.drawRightString(page[0] - margin, 7 * mm, f"Page {number} of {total}")
        if picture is not None and number == 1:
            # First page only, centred in the top margin beside the title.
            iw, ih = picture.getSize()
            h = 11 * mm
            w = h * iw / ih
            canvas.drawImage(picture, (page[0] - w) / 2, page[1] - 3.5 * mm - h, w, h, mask="auto")
        canvas.restoreState()

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
    doc.build(story, canvasmaker=_numbered_canvas(footer))
    return out.getvalue()


def _numbered_canvas(footer):
    """A canvas that draws each page's footer once the page count is known."""
    from reportlab.pdfgen.canvas import Canvas

    class Numbered(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):  # noqa: N802  (reportlab's name)
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for number, state in enumerate(self._pages, start=1):
                self.__dict__.update(state)
                footer(self, number, total)
                super().showPage()
            super().save()

    return Numbered


def pdf_response(title: str, scope: str, sheets: list[dict], stem: str) -> HttpResponse:
    from core import print_mark

    mark = print_mark.mark(print_mark.group_company())
    response = HttpResponse(pdf(title, scope, sheets, mark), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{_slug(stem)}.pdf"'
    return response


def _group_name() -> str:
    """The group's name, for a report that is not for one company."""
    from tenancy.context import current_tenant

    tenant = current_tenant()
    return tenant.name if tenant else ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "report"


class PdfView(APIView):
    """POST {title, scope, sheets: [{title, columns, rows}]} -> a PDF of what
    the screen shows. The data comes from the screen the person is looking
    at, so being signed in is enough."""

    permission_classes = [Signed]

    def post(self, request):
        title = str(request.data.get("title") or "Report")[:120]
        scope = str(request.data.get("scope") or "")[:200] or _group_name()
        stem = f"{title}-{datetime.date.today().isoformat()}"
        return pdf_response(title, scope, request.data.get("sheets"), stem)
