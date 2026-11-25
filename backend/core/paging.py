"""One page of 25 of a long master list (Sidharth, 2026-11-24: "max 25 rows per
page", column searches on the server, inactive records hidden behind "Show
Inactive", click a heading to sort). The Items screen came first (core/items.py);
other lists use this.

A list's GET with ?page=N answers {count, page, pages, page_size, results}:
* each column search box sends its text under the column's search name, and
  every word typed must appear in one of that column's fields;
* inactive rows are left out unless ?inactive=1, and then come last;
* ?sort=key sorts A to Z by that column, ?sort=-key Z to A, empty values last.
"""

from __future__ import annotations

from collections.abc import Callable

from django.db.models import F, Q, QuerySet

PAGE_SIZE = 25


def words(text: str) -> list[str]:
    return [w for w in text.replace("%", " ").split() if w]


def search(rows: QuerySet, params, columns: dict[str, list[str]]) -> QuerySet:
    """`columns` maps a search name to the fields it looks in."""
    for name, fields in columns.items():
        for word in words(params.get(name, "")):
            match = Q()
            for field in fields:
                match |= Q(**{f"{field}__icontains": word})
            rows = rows.filter(match)
    return rows


def one_page(
    rows: QuerySet,
    params,
    serialize: Callable[[QuerySet], list],
    *,
    sorts: dict[str, str],
    then: tuple[str, ...] = ("name", "pk"),
) -> dict:
    if params.get("inactive") != "1":
        rows = rows.filter(is_active=True)
    key = params.get("sort", "")
    field = sorts.get(key.removeprefix("-"))
    by = []
    if field:
        expr = F(field)
        by = [expr.desc(nulls_last=True) if key.startswith("-") else expr.asc(nulls_last=True)]
    rows = rows.order_by("-is_active", *by, *then)
    count = rows.count()
    last = max(1, -(-count // PAGE_SIZE))
    try:
        page = min(max(1, int(params.get("page", 1))), last)
    except ValueError:
        page = 1
    return {
        "count": count,
        "page": page,
        "pages": last,
        "page_size": PAGE_SIZE,
        "results": serialize(rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]),
    }
