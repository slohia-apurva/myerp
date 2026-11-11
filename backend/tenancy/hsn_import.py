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
    rows = []
    for cells in csv.reader(io.StringIO(text), dialect=dialect):
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
    row stops the whole load, so the list is never half loaded."""
    wanted: dict[str, str] = {}
    for n, (code, description) in enumerate(rows, 1):
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
    }
