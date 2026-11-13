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
    column, description in the second); heading rows are skipped."""
    from openpyxl import load_workbook

    def cell(v) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v).replace("_x000D_", " ")

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    cells = [[cell(v) for v in row] for sheet in book for row in sheet.iter_rows(values_only=True)]
    return _rows(cells)


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
    5 or 7 digits (a leading zero lost in the source file) is not a valid HSN
    code: it is left out and named in the result."""
    wanted: dict[str, str] = {}
    skipped: list[str] = []
    for n, (code, description) in enumerate(rows, 1):
        if code.isdigit() and len(code) not in (2, 4, 6, 8):
            skipped.append(code)
            continue
        try:
            HsnCode(hsn_code=code, description=description).clean()
        except ValidationError as exc:
            raise ValueError(f"Row {n} ({code or 'blank'}): {exc.messages[0]}") from exc
        if not description:
            raise ValueError(f"Row {n} ({code}): the description is blank.")
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
    }
