"""Running numbers for records such as customers and vendors (decision 0021)."""

import re

from rest_framework.exceptions import ValidationError

from core.models import FiscalYear, NumberCounter, NumberFormat, NumberSeries

DEFAULTS = {"customer": "CUST-", "vendor": "VEND-", "item": "ITEM-", "bom": "BOM-"}


def format_number(series: NumberSeries, n: int) -> str:
    return f"{series.prefix}{n:0{series.width}d}"


def next_number(key: str, taken=lambda number: False) -> str:
    """The next free number of this series. Call inside tenant_atomic: the
    row lock keeps two saves from getting the same one. `taken` skips numbers
    someone already typed in by hand."""
    series, _ = NumberSeries.objects.select_for_update().get_or_create(
        key=key, defaults={"prefix": DEFAULTS.get(key, "")}
    )
    while True:
        series.last += 1
        number = format_number(series, series.last)
        if not taken(number):
            break
    series.save(update_fields=["last"])
    return number


NUMBERED = re.compile(r"(.*?)(\d+)")


def follow_numbers(key: str, numbers) -> None:
    """Move a master series on past numbers that came in from a file (item
    codes kept from another system, say IT-012465), so the next number made
    here carries on after the highest. When no record holds a number of the
    series' own pattern any more, the series takes the pattern most of the
    records have. Call inside tenant_atomic."""
    series, _ = NumberSeries.objects.select_for_update().get_or_create(
        key=key, defaults={"prefix": DEFAULTS.get(key, "")}
    )
    count: dict[tuple[str, int], int] = {}
    top: dict[tuple[str, int], int] = {}
    for number in numbers:
        m = NUMBERED.fullmatch(number or "")
        if not m or len(m[1]) > 10 or not 3 <= len(m[2]) <= 8:
            continue
        shape = (m[1], len(m[2]))
        count[shape] = count.get(shape, 0) + 1
        top[shape] = max(top.get(shape, 0), int(m[2]))
    own = (series.prefix, series.width)
    if own in count:
        if top[own] > series.last:
            series.last = top[own]
            series.save(update_fields=["last"])
        return
    if not count:
        return
    shape = max(count, key=lambda s: (count[s], top[s]))
    series.prefix, series.width = shape
    series.last = top[shape]
    series.save(update_fields=["prefix", "width", "last"])


# --- Document series: per company (and branch), restarting every fiscal year --

# (key, label, short code in the number, GST invoice?) A GST invoice number is at most
# 16 characters of letters, digits, "/" and "-" (CGST Rule 46).
DOCUMENT_TYPES = [
    ("sales_invoice", "Sales invoice", "SI", True),
    ("credit_note", "Credit note", "CN", True),
    ("debit_note", "Debit note", "DN", True),
    ("sales_order", "Sales order", "SO", False),
    ("pick_list", "Pick list", "PL", False),
    ("delivery_challan", "Delivery challan", "DC", False),
    ("purchase_order", "Purchase order", "PO", False),
    ("goods_receipt", "Goods receipt (GRN)", "GRN", False),
    ("purchase_invoice", "Purchase invoice", "PI", False),
    ("purchase_return", "Purchase return", "PR", False),
    ("tds_adjustment", "TDS adjustment", "TDSA", False),
    ("payment", "Payment", "PAY", False),
    ("receipt", "Receipt", "RCT", False),
    ("journal", "Journal voucher", "JV", False),
    ("contra", "Contra voucher", "CV", False),
    ("stock_transfer", "Stock transfer", "ST", False),
    ("stock_receipt", "Stock receipt (customer's goods)", "SR", False),
    ("stock_delivery", "Stock delivery (customer's goods)", "SD", False),
    ("own_use", "Own use", "OU", False),
    ("production_order", "Production order", "PRD", False),
]
DOC_TYPES = {code: (label, short, gst) for code, label, short, gst in DOCUMENT_TYPES}
DOC_CHOICES = [(code, label) for code, label, *_ in DOCUMENT_TYPES]
MAX_GST_NUMBER = 16
PREFIX_CHARS = re.compile(r"[A-Za-z0-9/._-]*")


def short_year(year_name: str) -> str:
    """2026-27 -> 2627, 2026 -> 26: the year as it goes into a document number."""
    two = re.fullmatch(r"(\d{4})-(\d{2})", year_name)
    if two:
        return two.group(1)[2:] + two.group(2)
    one = re.fullmatch(r"\d{4}", year_name)
    return year_name[2:] if one else re.sub(r"[^A-Za-z0-9]", "", year_name)


def render(prefix: str, year_name: str, width: int, n: int) -> str:
    """{FY} in a prefix is the year's name (2026-27), {YY} its short form (2627)."""
    prefix = prefix.replace("{FY}", year_name).replace("{YY}", short_year(year_name))
    return f"{prefix}{n:0{width}d}"


def check_format(doc_type: str, prefix: str, width: int, year_name: str = "2026-27") -> None:
    """Raise ValueError (a sentence people can act on) if the numbers this
    format makes would be unusable."""
    if doc_type not in DOC_TYPES:
        raise ValueError("Pick a kind of document.")
    if not prefix or not PREFIX_CHARS.fullmatch(prefix.replace("{FY}", "").replace("{YY}", "")):
        raise ValueError(
            "The prefix holds letters, digits, / . _ - and {YY} (2627) or {FY} (2026-27)."
        )
    if not 3 <= width <= 8:
        raise ValueError("The number part is 3 to 8 digits long.")
    if DOC_TYPES[doc_type][2]:
        sample = render(prefix, year_name, width, 1)
        if len(sample) > MAX_GST_NUMBER or not re.fullmatch(r"[A-Za-z0-9/-]+", sample):
            raise ValueError(
                f"A GST invoice number is at most {MAX_GST_NUMBER} characters of letters, "
                f"digits, / and -. This makes {sample} ({len(sample)} characters)."
            )


def ensure_formats(company) -> None:
    """Give a company the standard format of every kind of document."""
    have = set(
        NumberFormat.objects.filter(company=company, branch__isnull=True).values_list(
            "doc_type", flat=True
        )
    )
    for code, *_ in DOCUMENT_TYPES:
        if code not in have:
            NumberFormat.objects.create(company=company, doc_type=code, **_default(company, code))


def _default(company, doc_type: str) -> dict:
    """AO/SI/2627/00001: company code, document, year and five digits. A GST
    invoice number holds 16 characters at most, so a longer company code gets
    fewer digits (or none of its code) to fit."""
    short = DOC_TYPES[doc_type][1]
    for prefix in (f"{company.abbr}/{short}/{{YY}}/", f"{short}/{{YY}}/"):
        for width in (5, 4, 3):
            try:
                check_format(doc_type, prefix, width)
            except ValueError:
                continue
            return {"prefix": prefix, "width": width}
    return {"prefix": f"{short}/{{YY}}/", "width": 3}


def format_for(company, doc_type: str, branch=None) -> NumberFormat:
    """The branch's own format if it has one, else the company's."""
    if doc_type not in DOC_TYPES:
        raise ValueError(f"Unknown kind of document {doc_type!r}.")
    ensure_formats(company)
    if branch is not None:
        own = NumberFormat.objects.filter(company=company, doc_type=doc_type, branch=branch).first()
        if own:
            return own
    return NumberFormat.objects.get(company=company, doc_type=doc_type, branch__isnull=True)


def next_document_number(company, doc_type: str, day, branch=None) -> str:
    """The next number of this kind of document for an entry dated `day`;
    each fiscal year counts from 0001. Call inside tenant_atomic: the row
    lock keeps two saves from getting the same number. (Check the date with
    fiscal.assert_open first.)"""
    year = FiscalYear.objects.filter(
        company=company, is_active=True, start_date__lte=day, end_date__gte=day
    ).first()
    if year is None:
        raise ValidationError({"date": [f"No fiscal year is set up for {day:%d-%m-%Y}."]})
    fmt = format_for(company, doc_type, branch)
    NumberCounter.objects.get_or_create(format=fmt, year=year)
    counter = NumberCounter.objects.select_for_update().get(format=fmt, year=year)
    counter.last += 1
    counter.save(update_fields=["last"])
    return render(fmt.prefix, year.name, fmt.width, counter.last)
