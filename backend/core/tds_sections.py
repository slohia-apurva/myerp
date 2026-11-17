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
    # In code order whatever the database's collation (it may skip brackets).
    return sorted(out, key=lambda row: row.code)


def check_section(code: str, field: str = "tds_section") -> str:
    """A section picked on a supplier, item, ledger or bill must be in the list."""
    code = (code or "").strip()
    if code and not TdsSection.objects.filter(code=code, is_active=True).exists():
        raise ValidationError({field: [f"{code} is not in the TDS sections list."]})
    return code


def label(sec: TdsSection) -> str:
    """A picker's text, with both numbers so either finds it: '393(1) Sl. 6(i)
    Contractors (old 194C)' from the Income-tax Act 2025, else '194C Contractors'."""
    if sec.new_code:
        return f"{sec.new_code} {sec.name} (old {sec.code})"
    return f"{sec.code} {sec.name}"


def shown(code: str, day: datetime.date) -> str:
    """A section as a bill of that date shows it: '393(1) Sl. 6(i) (194C)' from
    1 April 2026, '194C' before (the row in force then has no new number)."""
    sec = section_on(code, day)
    if sec is not None and sec.new_code:
        return f"{sec.new_code} ({code})"
    return code


def payment_code(sec: TdsSection, individual: bool) -> str:
    """The challan's payment code, by the deductee type where the Act gives two."""
    if individual and sec.payment_code_individual:
        return sec.payment_code_individual
    return sec.payment_code
