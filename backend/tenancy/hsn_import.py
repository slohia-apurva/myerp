"""Loading the central HSN / SAC list from a CSV or tab-separated file."""

import csv
import io

from django.core.exceptions import ValidationError

from tenancy.models import HsnCode

MAX_LEN = 500


def parse(text: str) -> list[tuple[str, str]]:
    """(code, description) rows. Lines whose first cell is not a 2-8 digit
    code (headings, blanks) are skipped."""
    dialect = "excel-tab" if "\t" in text.splitlines()[0] else "excel"
    return _rows(list(csv.reader(io.StringIO(text), dialect=dialect)))


def parse_excel(data: bytes) -> list[tuple[str, str]]:
    """The same rows from every sheet of an Excel file (code in the first
    column, description in the second); heading rows are skipped. A
    description Excel took for a formula (text starting with "=") is read as
    the text that was typed."""
    from openpyxl import load_workbook

    def cell(v) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v).replace("_x000D_", " ")

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets = [
        [[cell(v) for v in row] for row in sheet.iter_rows(values_only=True)] for sheet in book
    ]
    broken = [
        (s, r)
        for s, lines in enumerate(sheets)
        for r, cells in enumerate(lines)
        if len(cells) > 1
        and cells[0].strip()
        and (not cells[1].strip() or cells[1].startswith("#"))
    ]
    if broken:
        typed = load_workbook(io.BytesIO(data), read_only=True)
        for s, sheet in enumerate(typed):
            wanted = {r for i, r in broken if i == s}
            if not wanted:
                continue
            for r, row in enumerate(sheet.iter_rows(values_only=True)):
                if r in wanted and len(row) > 1 and row[1] is not None:
                    text = str(getattr(row[1], "text", row[1])).lstrip("=").strip()
                    if text:
                        sheets[s][r][1] = text
    return _rows([cells for lines in sheets for cells in lines])


def _rows(lines: list[list[str]]) -> list[tuple[str, str]]:
    rows = []
    for cells in lines:
        if not cells:
            continue
        code = cells[0].strip().replace(" ", "")
        rest = [c.strip() for c in cells[1:]]
        while rest and not rest[-1]:
            rest.pop()
        if code.isdigit() and 2 <= len(code) <= 8:
            rows.append((code, " ".join(", ".join(rest).split())))
    return rows


def load(rows: list[tuple[str, str]]) -> dict:
    """Add new codes and refresh descriptions of ones already there. A bad
    row stops the whole load, so the list is never half loaded. A code of 3,
    5 or 7 digits is not a valid HSN code, and a row with no description cannot
    be shown: such rows are left out and named in the result."""
    wanted: dict[str, str] = {}
    skipped: list[str] = []
    problems: list[str] = []
    seen: set[str] = set()
    repeated: list[str] = []
    for n, (code, description) in enumerate(rows, 1):
        if code in seen and code not in repeated:
            repeated.append(code)
        seen.add(code)
        if code.isdigit() and len(code) not in (2, 4, 6, 8):
            skipped.append(code)
            problems.append(f"{code}: not 2, 4, 6 or 8 digits")
            continue
        try:
            HsnCode(hsn_code=code, description=description).clean()
        except ValidationError as exc:
            raise ValueError(f"Row {n} ({code or 'blank'}): {exc.messages[0]}") from exc
        if not description:
            skipped.append(code)
            problems.append(f"{code}: no description")
            continue
        wanted[code] = description[:MAX_LEN]
    have = {h.hsn_code: h for h in HsnCode.objects.filter(hsn_code__in=wanted)}
    new, changed = [], []
    for code, description in wanted.items():
        if code in have:
            if have[code].description != description:
                have[code].description = description
                changed.append(have[code])
        else:
            new.append(HsnCode(hsn_code=code, description=description))
    HsnCode.objects.bulk_create(new)
    HsnCode.objects.bulk_update(changed, ["description"])
    return {
        "added": len(new),
        "updated": len(changed),
        "unchanged": len(wanted) - len(new) - len(changed),
        "skipped": skipped,
        "problems": problems,
        "repeated": repeated,
    }
