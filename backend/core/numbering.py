"""Running numbers for records such as customers and vendors (decision 0021)."""

from core.models import NumberSeries

DEFAULTS = {"customer": "CUST-", "vendor": "VEND-"}


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
