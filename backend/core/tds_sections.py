"""TDS sections as tenants see them: a central dated list kept by MyERP in the
platform database (like GST rates), read-only here. Suppliers, items, ledgers
and bill lines keep only a section's code; buying/tds.py works TDS out."""

import datetime

from rest_framework.exceptions import ValidationError

from tenancy.models import TdsSection


def section_on(code: str, day: datetime.date) -> TdsSection | None:
    """The row of a section in force on a day."""
    if not code:
        return None
    return (
        TdsSection.objects.filter(code=code, valid_from__lte=day, is_active=True)
        .order_by("-valid_from")
        .first()
    )


def current_sections(day: datetime.date | None = None) -> list[TdsSection]:
    """Each section once, as in force on the day (today)."""
    day = day or datetime.date.today()
    seen, out = set(), []
    rows = TdsSection.objects.filter(valid_from__lte=day, is_active=True)
    for row in rows.order_by("code", "-valid_from"):
        if row.code not in seen:
            seen.add(row.code)
            out.append(row)
    return out


def check_section(code: str, field: str = "tds_section") -> str:
    """A section picked on a supplier, item, ledger or bill must be in the list."""
    code = (code or "").strip()
    if code and not TdsSection.objects.filter(code=code, is_active=True).exists():
        raise ValidationError({field: [f"{code} is not in the TDS sections list."]})
    return code
