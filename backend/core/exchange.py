"""Import, export and print for every masters screen.

One framework serves every master. Each master registers itself once with
`register(Master(...))`, naming its serializer and its save function: the very
ones its own screen uses. From those:

- the columns of the file are the serializer's writable fields, labelled as
  the audit log labels them, so a field added to a form's serializer appears
  in the file by itself (a field the framework cannot put in one cell must be
  given a `Codec` or listed in `exclude`, or registration fails loudly);
  links to other masters are written as their names; rows kept inside a
  record (a term's parts, an item's units) get an Excel sheet of their own;
- every imported row goes through the serializer and the save function, so
  it meets exactly the checks the form does (names that clash, GST codes,
  locks on masters in use, ...);
- a file is checked first (preview: every row saved, then all rolled back)
  and then imported in one transaction: if any row fails, nothing is saved.

Export and print need `masters.view`. Import needs `masters.edit` and
`masters.import`, which the Owner has and other roles get only when ticked.
"""

from __future__ import annotations

import csv
import datetime
import gzip
import io
import json
import re
from collections.abc import Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.recorder import LABELS
from core import india, printout
from core.api import EDIT, VIEW, Signed, _check, _company
from tenancy.context import require_tenant, tenant_atomic

IMPORT = "masters.import"
# Rows a file may hold, and rows that may add or change a record: a whole
# exported catalogue comes back with only a few rows changed, and the rows
# that change nothing are passed over without saving (Sidharth 2026-11-26,
# 11,157 items re-imported to fill in their TDS sections).
MAX_FILE_ROWS = 50000
# Each changed row is saved the form's way, about a tenth of a second for an
# item, and a request has 5 minutes on the server: 1,000 fits with room to spare.
MAX_ROWS = 1000
MAX_BYTES = 20 * 1024 * 1024
ID_LABEL = "ID"


# --- Columns -----------------------------------------------------------------


@dataclass(frozen=True)
class Codec:
    """How one field goes into a cell and comes back out of it.
    `to_cell(value)` turns the serializer's value into text; `from_cell(text)`
    turns non-empty cell text back into what the serializer accepts, raising
    ValueError with a message people can act on."""

    to_cell: Callable[[Any], str]
    from_cell: Callable[[str], Any]
    hint: str = ""
    choices: Callable[[], Iterable[str]] | None = None
    kind: str = ""  # see Column.kind; by default worked out from the field


@dataclass(frozen=True)
class Column:
    field: str
    label: str
    kind: str  # text, number, date, yesno, choice, other
    required: bool
    codec: Codec
    allow_null: bool = False
    read_only: bool = False  # shown in exports and prints, ignored on import
    # The record kept inside this one that the field belongs to ("party" for
    # "party.gstin"); "" for the record's own fields. A group whose cells are
    # all empty is left out of the import, as a form leaves out its hidden tab.
    group: str = ""


@dataclass(frozen=True)
class Sheet:
    """One table of the file. The master's own records are the first sheet;
    rows kept inside a record (a term's parts, an item's units) get a sheet
    each, whose first column names the record they belong to."""

    field: str  # "" for the main sheet, else the list's path ("party.addresses")
    title: str
    columns: list[Column]
    link_label: str = ""  # child sheets: the first column's heading


@dataclass(frozen=True)
class Code:
    """A master's own code (an item number, a customer number): it finds the
    record when a row's ID is empty, and an import never changes it.
    `find(text)` filters the master's records to the one with that code;
    `of(record)` is the record's code now ("" when it has none)."""

    find: Callable[[str], Q]
    of: Callable[[Any], str]


@dataclass
class Context:
    """What an import or export runs for: who, and which company when the
    master is kept per company."""

    request: Any
    company: Any = None


@dataclass
class Master:
    key: str  # in the URL, e.g. "units"
    label: str  # e.g. "Units"
    serializer: type[serializers.Serializer]
    queryset: Callable[[Context], Any]
    # Save validated data the way the screen does; instance is None for a new
    # record. Returns the saved record.
    save: Callable[[Context, Any, dict], Any]
    noun: str = "record"  # one of them, e.g. "unit"
    per_company: bool = False
    # Fields left out of the file. A child sheet's field is written
    # "units.factor".
    exclude: tuple[str, ...] = ()
    # Read-only fields worth seeing in exports and prints (item numbers, say).
    show: tuple[str, ...] = ()
    codecs: dict[str, Codec] = field(default_factory=dict)
    # Column or sheet headings where the audit label does not suit.
    labels: dict[str, str] = field(default_factory=dict)
    # Extra lines for the "How to fill" sheet, field -> text.
    hints: dict[str, str] = field(default_factory=dict)
    # The field that child sheets use to say which record a row belongs to.
    link: str = "name"
    # Columns of the printed report and PDF (field paths), when not all of
    # them; child sheets always print in full.
    report: tuple[str, ...] = ()
    # Run once after every row has saved (still inside the import's
    # transaction), e.g. to move a number series on past imported numbers.
    after: Callable[[Context], None] | None = None
    # Other programs' export files this master can read, by name: each turns
    # the file's sheets into this master's own and gives notes for the person
    # (see core/erpnext.py).
    # reader(sheets, options) -> (sheets, notes, extra): `options` are the
    # import box's own choices (a name map file, parts), `extra` goes back in
    # the answer (e.g. how many parts the file is checked in).
    sources: dict[str, Callable[[list, dict], tuple[list, list[str], dict]]] = field(
        default_factory=dict
    )
    # The master's codes, by field path (item number; customer and vendor
    # numbers): with the ID, they say which record a row changes.
    codes: dict[str, Code] = field(default_factory=dict)

    def _columns(self, fields, prefix: str = "", rel: str = "", group: str = "") -> list[Column]:
        """Columns for these serializer fields. `prefix` is the path from the
        master (for exclude, labels, codecs); `rel` the path within the sheet's
        own record. Records kept inside (one, not a list) are flattened in."""
        out = []
        for name, f in fields.items():
            path = f"{prefix}{name}"
            if path in self.exclude or isinstance(f, serializers.ListSerializer):
                continue
            if isinstance(f, serializers.Serializer):
                if not f.read_only:
                    out += self._columns(f.fields, f"{path}.", f"{rel}{name}.", f"{rel}{name}")
                continue
            if f.read_only and path not in self.show:
                continue
            codec = self.codecs.get(path) or _default_codec(f)
            if codec is None:
                raise ImproperlyConfigured(
                    f"Import/export for {self.key}: the field {path!r} "
                    f"({type(f).__name__}) needs a Codec in `codecs`, or list it in `exclude`."
                )
            out.append(
                Column(
                    field=f"{rel}{name}",
                    label=self.labels.get(path) or _label(name, f),
                    kind=codec.kind or _kind(f),
                    required=bool(f.required) and not f.read_only and not group,
                    codec=codec,
                    allow_null=bool(getattr(f, "allow_null", False)),
                    read_only=bool(f.read_only),
                    group=group,
                )
            )
        return out

    def _lists(self, fields, prefix: str = "") -> list[tuple[str, serializers.ListSerializer]]:
        """The lists kept inside the record, at any depth of records kept
        inside it: (path, field)."""
        out = []
        for name, f in fields.items():
            path = f"{prefix}{name}"
            if path in self.exclude or f.read_only:
                continue
            if isinstance(f, serializers.ListSerializer):
                out.append((path, f))
            elif isinstance(f, serializers.Serializer):
                out += self._lists(f.fields, f"{path}.")
        return out

    def sheets(self) -> list[Sheet]:
        fields = self.serializer().fields
        out = [Sheet("", self.label, self._columns(fields))]
        owner = self.noun[:1].upper() + self.noun[1:]
        for path, f in self._lists(fields):
            title = self.labels.get(path) or _label(path.rsplit(".", 1)[-1], f)
            columns = self._columns(f.child.fields, f"{path}.")
            out.append(Sheet(path, title[:31], columns, owner))
        for sheet in out:
            labels = [c.label.lower() for c in sheet.columns]
            twice = {x for x in labels if labels.count(x) > 1}
            if twice:
                raise ImproperlyConfigured(
                    f"Import/export for {self.key}: the {sheet.title} sheet has two columns "
                    f"called {', '.join(sorted(twice))}; give one a label in `labels`."
                )
        return out

    def columns(self) -> list[Column]:
        return self.sheets()[0].columns


def _get(record: dict, path: str):
    for part in path.split("."):
        if not isinstance(record, dict):
            return None
        record = record.get(part)
    return record


def _put(record: dict, path: str, value) -> None:
    *parts, last = path.split(".")
    for part in parts:
        record = record.setdefault(part, {})
    record[last] = value


# The import or export running now, for lookups that depend on the company.
_running: ContextVar[Context | None] = ContextVar("myerp_exchange_context", default=None)


MASTERS: dict[str, Master] = {}


def _state_from(text: str) -> str:
    low = text.strip().lower()
    for code, name in india.STATES.items():
        if low in (code, name.lower()):
            return code
    raise ValueError(f"{text!r} is not an Indian state; leave it empty for a party abroad")


# An Indian state, written by name (or its two-digit GST code).
STATE = Codec(
    lambda code: india.STATES.get(code, code or ""),
    _state_from,
    hint="The state's name or its two-digit GST code",
)


def register(master: Master) -> None:
    main = master.sheets()[0]  # fail at start-up, not when someone exports
    missing = set(master.codes) - {c.field for c in main.columns}
    if missing:
        raise ImproperlyConfigured(
            f"Import/export for {master.key}: the codes {sorted(missing)} are not columns."
        )
    MASTERS[master.key] = master


def _label(name: str, f) -> str:
    if name in LABELS:
        return LABELS[name]
    text = str(f.label or name.replace("_", " "))
    return text[:1].upper() + text[1:]


def _kind(f) -> str:
    if isinstance(f, serializers.BooleanField):
        return "yesno"
    if isinstance(f, serializers.ChoiceField):
        return "choice"
    if isinstance(f, serializers.DateField):
        return "date"
    if isinstance(f, serializers.DecimalField | serializers.IntegerField | serializers.FloatField):
        return "number"
    if type(f) in (serializers.CharField, serializers.EmailField, serializers.RegexField):
        return "text"
    return "other"


YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0"}


def _yesno(text: str) -> bool:
    low = text.strip().lower()
    if low in YES:
        return True
    if low in NO:
        return False
    raise ValueError(f"write Yes or No, not {text!r}")


def _number(text: str) -> str:
    clean = re.sub(r"[,\s₹%]", "", text)
    try:
        Decimal(clean)
    except InvalidOperation:
        raise ValueError(f"{text!r} is not a number") from None
    return clean


DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y")


def _date(text: str) -> str:
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"{text!r} is not a date; write it as DD-MM-YYYY")


def _pick(choices: dict, text: str):
    low = text.strip().lower()
    for value, label in choices.items():
        if low in (str(value).lower(), str(label).lower()):
            return value
    raise ValueError(f"{text!r} is not one of: {', '.join(map(str, choices.values()))}")


def _choice_codec(f: serializers.ChoiceField) -> Codec:
    def to_cell(value) -> str:
        return "" if value in (None, "") else str(f.choices.get(value, value))

    return Codec(
        to_cell, lambda t: _pick(f.choices, t), choices=lambda: [str(v) for v in f.choices.values()]
    )


def _choice_list_codec(f: serializers.ChoiceField) -> Codec:
    """A list of choices in one cell, separated by commas."""

    def to_cell(values) -> str:
        return ", ".join(str(f.choices.get(v, v)) for v in values or [])

    def from_cell(text: str) -> list:
        return [_pick(f.choices, part) for part in text.split(",") if part.strip()]

    return Codec(
        to_cell,
        from_cell,
        hint="Several may be written, separated by commas",
        choices=lambda: [str(v) for v in f.choices.values()],
        kind="list",
    )


# Names of related records, looked up once per export or import.
_names: dict[Any, dict] = {}


def _relation_codec(f: serializers.PrimaryKeyRelatedField) -> Codec | None:
    """A link to another master, written as that record's name (or its short
    name, where it has one)."""
    queryset = f.queryset
    if queryset is None:
        return None
    model = queryset.model
    have = {x.name for x in model._meta.get_fields()}
    if "name" not in have:
        return None
    alt = "short_name" if "short_name" in have else None
    what = str(model._meta.verbose_name)

    per_company = "company" in have

    def scoped():
        ctx = _running.get()
        if per_company and ctx is not None and ctx.company is not None:
            return queryset.filter(company=ctx.company)
        return queryset.all()

    def names() -> dict:
        if model not in _names:
            _names[model] = dict(model.objects.values_list("pk", "name"))
        return _names[model]

    def to_cell(pk) -> str:
        return "" if pk is None else str(names().get(pk, pk))

    def from_cell(text: str):
        found = scoped().filter(name__iexact=text.strip()).first()
        if found is None and alt:
            found = scoped().filter(**{f"{alt}__iexact": text.strip()}).first()
        if found is None:
            raise ValueError(f"there is no {what} called {text!r}")
        return found.pk

    hint = f"The {what}'s name" + (" or short name" if alt else "")
    return Codec(to_cell, from_cell, hint=hint, kind="other")


def _plain(value) -> str:
    return "" if value is None else str(value)


def _default_codec(f) -> Codec | None:
    if isinstance(f, serializers.BooleanField):
        return Codec(lambda v: "Yes" if v else "No", _yesno, choices=lambda: ["Yes", "No"])
    if isinstance(f, serializers.ChoiceField) and not isinstance(
        f, serializers.MultipleChoiceField
    ):
        return _choice_codec(f)
    if isinstance(f, serializers.ListField) and isinstance(f.child, serializers.ChoiceField):
        return _choice_list_codec(f.child)
    if isinstance(f, serializers.PrimaryKeyRelatedField):
        return _relation_codec(f)
    if isinstance(f, serializers.SlugRelatedField):
        return Codec(_plain, lambda t: t.strip(), hint=f"Its {f.slug_field.replace('_', ' ')}")
    if isinstance(f, serializers.DateField):
        return Codec(
            lambda v: datetime.date.fromisoformat(v).strftime("%d-%m-%Y") if v else "",
            _date,
            hint="DD-MM-YYYY",
        )
    if isinstance(f, serializers.DecimalField | serializers.IntegerField | serializers.FloatField):
        return Codec(_plain, _number)
    if type(f) in (serializers.CharField, serializers.EmailField, serializers.RegexField):
        return Codec(_plain, lambda t: t)
    if f.read_only:
        return Codec(_plain, lambda t: t)  # shown only
    return None  # anything else: the master must say how


def _hint(col: Column, master: Master, sheet: Sheet) -> str:
    if col.read_only:
        return "Filled in by MyERP; left as it is on import"
    path = f"{sheet.field}.{col.field}" if sheet.field else col.field
    parts = []
    if path in master.hints:
        parts.append(master.hints[path])
    if col.codec.hint:
        parts.append(col.codec.hint)
    if col.codec.choices is not None:
        parts.append("One of: " + ", ".join(col.codec.choices()))
    return ". ".join(parts)


# --- Files -------------------------------------------------------------------


@dataclass
class Table:
    sheet: Sheet
    headers: list[str]
    kinds: list[str]
    rows: list[list[str]]


def _tables_out(master: Master, ctx: Context, blank: bool, only: Q | None = None) -> list[Table]:
    """Every sheet of the master as rows of text: the main sheet starts with
    the ID, child sheets with the record they belong to. `only` keeps just
    those records (an import comparing its rows with them)."""
    _names.clear()
    _running.set(ctx)
    sheets = master.sheets()
    data = []
    if not blank:
        records = master.queryset(ctx)
        if only is not None:
            records = records.filter(only)
        # "list": the serializers skip their per-record "in use" checks, which an
        # export never shows (12,000 items took over 300 s, 2026-11-24).
        data = master.serializer(
            records, many=True, context={"request": ctx.request, "list": True}
        ).data
    main = sheets[0]
    link = next((c for c in main.columns if c.field == master.link), None)
    tables = [
        Table(
            main,
            [ID_LABEL] + [c.label for c in main.columns],
            ["number"] + [c.kind for c in main.columns],
            [
                [str(r["id"])] + [c.codec.to_cell(_get(r, c.field)) for c in main.columns]
                for r in data
            ],
        )
    ]
    for sheet in sheets[1:]:
        rows = []
        for r in data:
            owner = link.codec.to_cell(r.get(master.link)) if link else str(r["id"])
            for child in _get(r, sheet.field) or []:
                rows.append(
                    [owner] + [c.codec.to_cell(_get(child, c.field)) for c in sheet.columns]
                )
        tables.append(
            Table(
                sheet,
                [sheet.link_label] + [c.label for c in sheet.columns],
                ["text"] + [c.kind for c in sheet.columns],
                rows,
            )
        )
    return tables


def _xlsx(master: Master, tables: list[Table]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    # Written row by row ("write only"): about twice as fast for 12,000 items.
    wb = Workbook(write_only=True)
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="E3F2E8")

    def heading(ws, cells):
        out = []
        for text in cells:
            cell = WriteOnlyCell(ws, value=text)
            cell.font, cell.fill = bold, fill
            out.append(cell)
        return out

    for table in tables:
        ws = wb.create_sheet(table.sheet.title[:31])
        texts = []
        for i, header in enumerate(table.headers, start=1):
            width = max([len(header)] + [len(r[i - 1]) for r in table.rows[:500]]) + 2
            letter = get_column_letter(i)
            ws.column_dimensions[letter].width = min(max(width, 8), 50)
            # Keep codes such as HSN 0401 or PIN 011001 as text, not numbers.
            text = table.kinds[i - 1] != "number"
            if text:
                ws.column_dimensions[letter].number_format = "@"
            texts.append(text)
        ws.freeze_panes = "B2"
        ws.append(heading(ws, table.headers))
        for row in table.rows:
            cells = []
            for text, value in zip(texts, row, strict=True):
                if not text:
                    cells.append(_number_cell(value))
                elif value:
                    cell = WriteOnlyCell(ws, value=value)
                    cell.number_format = "@"
                    cells.append(cell)
                else:
                    cells.append(None)
            ws.append(cells)

    help_ws = wb.create_sheet(HELP_SHEET)
    for letter, width in zip("ABCD", (22, 28, 10, 90), strict=True):
        help_ws.column_dimensions[letter].width = width
    help_ws.append(heading(help_ws, ["Sheet", "Column", "Must fill", "What to write"]))
    main = tables[0].sheet
    help_ws.append(
        [
            main.title,
            ID_LABEL,
            "No",
            "Keep the ID to change that record. Leave it empty to add a new one.",
        ]
    )
    for c in main.columns:
        help_ws.append([main.title, c.label, "Yes" if c.required else "No", _hint(c, master, main)])
    for table in tables[1:]:
        sheet = table.sheet
        help_ws.append(
            [
                sheet.title,
                sheet.link_label,
                "Yes",
                f"Which {master.noun} the row belongs to: its "
                f"{_main_label(master).lower()}, or its ID. "
                f"A {master.noun} in the first sheet gets exactly the rows listed here; "
                "delete this sheet to leave them as they are.",
            ]
        )
        for c in sheet.columns:
            help_ws.append(
                [sheet.title, c.label, "Yes" if c.required else "No", _hint(c, master, sheet)]
            )
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


HELP_SHEET = "How to fill"


def _main_label(master: Master) -> str:
    col = next((c for c in master.columns() if c.field == master.link), None)
    return col.label if col else ID_LABEL


def _number_cell(text: str):
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return text
    return int(value) if value == value.to_integral_value() else float(value)


def _csv(table: Table) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(table.headers)
    writer.writerows(table.rows)
    return out.getvalue().encode("utf-8-sig")  # the BOM makes Excel read ₹ and Hindi right


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime.datetime | datetime.date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_tables(name: str, content: bytes) -> list[tuple[str, list[list[str]]]]:
    """The file's sheets as (title, rows of text), header row first. A CSV
    file is one sheet."""
    if content[:2] == b"PK":  # .xlsx files are zip archives
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ParseError("This Excel file could not be read.") from exc
        return [
            (ws.title, [[_cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)])
            for ws in wb.worksheets
        ]
    if name.lower().endswith((".xls", ".ods")):
        raise ParseError("Save the file as Excel (.xlsx) or CSV and try again.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")
    return [("", [[c.strip() for c in row] for row in csv.reader(io.StringIO(text))])]


def read_table(name: str, content: bytes) -> list[list[str]]:
    """The first sheet only."""
    return read_tables(name, content)[0][1]


# --- Import ------------------------------------------------------------------


def _messages(detail, labels: dict[str, str], prefix: str = "") -> list[str]:
    """DRF error detail as plain lines, each starting with the column."""
    if isinstance(detail, dict):
        out = []
        for key, value in detail.items():
            if key == "existing":
                continue  # the link to a duplicate's record is for the screen
            if key in ("non_field_errors", "__all__"):
                out += _messages(value, labels, prefix)
            elif isinstance(key, int):
                out += _messages(value, labels, f"{prefix}line {key + 1}: ")
            else:
                out += _messages(value, labels, f"{prefix}{labels.get(key, key)}: ")
        return out
    if isinstance(detail, list):
        out = []
        for i, value in enumerate(detail):
            if isinstance(value, dict | list) and value:
                out += _messages(value, labels, f"{prefix}line {i + 1}: ")
            elif value:
                out += _messages(value, labels, prefix)
        return out
    return [f"{prefix}{detail}"]


def _headers(sheet: Sheet, header: list[str], first: str | None) -> tuple[int | None, dict]:
    """Where each column is: (position of the first column, field -> position).
    `first` is the ID (main sheet) or the record link (child sheets)."""
    by_header = {}
    for c in sheet.columns:
        by_header[c.label.lower()] = c
        by_header[c.field.lower()] = c
    first_at, at, unknown = None, {}, []
    for i, name in enumerate(header):
        key = name.strip().lower()
        if not key:
            continue
        if first and key == first.lower():
            first_at = i
        elif key in by_header:
            if not by_header[key].read_only:
                at[by_header[key].field] = i
        else:
            unknown.append(name)
    if unknown:
        raise ParseError(
            f"These columns are not {sheet.title} columns: {', '.join(unknown)}. "
            "Start from an exported file or the blank template."
        )
    return first_at, at


def _cells(columns: list[Column], at: dict, row: list[str]) -> tuple[dict, list[str], set]:
    """A row's cells as the form would send them, what is wrong with them,
    and which records kept inside (column groups) have anything filled in."""
    problems, data, filled = [], {}, set()
    for c in columns:
        if c.field not in at:
            continue
        i = at[c.field]
        text = row[i].strip() if i < len(row) else ""
        if not text:
            if c.kind == "text":
                _put(data, c.field, "")
            elif c.kind == "list":
                _put(data, c.field, [])
            elif c.allow_null:
                _put(data, c.field, None)
            continue  # keep what is there, or the form's default
        filled.add(c.group)
        try:
            _put(data, c.field, c.codec.from_cell(text))
        except ValueError as exc:
            problems.append(f"{c.label}: {exc}")
    return data, problems, filled


def _body(rows: list[list[str]]) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Header and the non-blank rows with their row numbers as Excel shows them."""
    start = 0
    while start < len(rows) and not any(rows[start]):
        start += 1
    if start == len(rows):
        return [], []
    body = [
        (n, row)
        for n, row in enumerate(rows[start + 1 :], start=start + 2)
        if any(cell.strip() for cell in row)
    ]
    return rows[start], body


def run_import(
    master: Master,
    ctx: Context,
    table,
    commit: bool,
    keep_codes: bool = True,
    only_rows: set[int] | None = None,
) -> dict:
    """Check (and, when `commit`, save) every row. Nothing is saved unless all
    rows pass. `table` is the first sheet's rows, or every sheet as given by
    `read_tables`. A row changes the record with its ID or, when the ID is
    empty, with its code (the master's `codes`); a row with neither adds one.
    With `keep_codes` (always, except for another program's file, which
    gives codes on purpose) a row may not change a record's code. Returns a
    summary with the problems row by row, and what each row changes.
    `only_rows`: one step of a stepped import, just those rows of the main
    sheet (the file's layout was checked when it was read)."""
    _names.clear()
    _running.set(ctx)
    tables = table if table and isinstance(table[0], tuple) else [("", table)]
    sheets = master.sheets()
    main = sheets[0]
    header, body = _body(tables[0][1])
    if not header:
        raise ParseError("The file is empty.")
    id_at, at = _headers(main, header, ID_LABEL)
    if not at:
        raise ParseError("The first row must hold the column names, as in the exported file.")
    if len(body) > MAX_FILE_ROWS:
        raise ParseError(f"Import at most {MAX_FILE_ROWS} rows at a time.")
    if only_rows is not None:
        body = [(n, row) for n, row in body if n in only_rows]
    code_at = _code_columns(master, main, header)
    # Rows exactly as MyERP would export them now: nothing to check or save.
    same, known = (
        _unchanged(master, ctx, tables, header, body, id_at, at, code_at)
        if keep_codes
        else ({}, {})
    )
    if len(body) - len(same) > MAX_ROWS:
        raise ParseError(
            f"Add or change at most {MAX_ROWS} {master.noun}s at a time; this file adds or "
            f"changes {len(body) - len(same)}. Rows left as exported do not count."
        )

    errors: list[dict] = []

    def problem(sheet: Sheet, n: int, messages: list[str]) -> None:
        errors.append({"sheet": sheet.title, "row": n, "messages": messages})

    # Rows of the child sheets, by the record they belong to.
    by_title = {title.strip().lower(): rows for title, rows in tables[1:]}
    # Lines are read into values only for the records that are saved: the lines
    # of rows left as exported are never needed (and reading each unit or rate
    # name takes a query).
    children: list[tuple[Sheet, dict[str, list[tuple[int, list[str]]]], dict]] = []
    for sheet in sheets[1:]:
        rows = by_title.get(sheet.title.lower())
        if rows is None:
            continue
        child_header, child_body = _body(rows)
        link_at, child_at = _headers(sheet, child_header, sheet.link_label)
        if link_at is None:
            raise ParseError(
                f"The {sheet.title} sheet must start with a {sheet.link_label} column."
            )
        grouped: dict[str, list[tuple[int, list[str]]]] = {}
        for n, row in child_body:
            owner = row[link_at].strip().lower() if link_at < len(row) else ""
            if not owner:
                if only_rows is None:
                    problem(
                        sheet,
                        n,
                        [f"{sheet.link_label}: say which {master.noun} this row belongs to"],
                    )
                continue
            grouped.setdefault(owner, []).append((n, row))
        children.append((sheet, grouped, child_at))
    unclaimed = {(s.field, k) for s, g, _ in children for k in g}

    labels = {c.field: c.label for c in main.columns}
    groups = {c.group for c in main.columns} - {""}
    results = []
    counts = {"new": 0, "changed": 0, "same": 0}
    with tenant_atomic():
        for n, row in body:
            if n in same:
                counts["same"] += 1
                unclaimed -= {(sheet.field, k) for sheet, _, _ in children for k in same[n]}
                continue
            data, bad, filled = _cells(main.columns, at, row)
            instance = None
            ref = row[id_at].strip() if id_at is not None and id_at < len(row) else ""
            if ref:
                try:
                    instance = master.queryset(ctx).select_for_update(of=("self",)).get(pk=int(ref))
                except (ValueError, ObjectDoesNotExist):
                    bad.append(
                        f"ID: there is no {master.noun} with ID {ref}. "
                        "Leave the ID empty to add a new one."
                    )
            codes = {path: row[i].strip() if i < len(row) else "" for path, i in code_at.items()}
            instance, wrong = _by_code(master, ctx, instance, ref, codes, keep_codes)
            bad += wrong
            keys = {ref.lower()} if ref else set()
            own = data.get(master.link)
            if own is None and instance is not None:
                own = getattr(instance, master.link, None)
            if own:
                keys.add(str(own).strip().lower())
            lines: dict[str, list[int]] = {}
            for sheet, grouped, child_at in children:
                found = []
                for m, line in sorted(x for k in keys for x in grouped.get(k, [])):
                    line_data, line_bad, _ = _cells(sheet.columns, child_at, line)
                    if line_bad:
                        problem(sheet, m, line_bad)
                    else:
                        found.append((m, line_data))
                unclaimed -= {(sheet.field, k) for k in keys}
                group = sheet.field.rpartition(".")[0]
                if found:
                    filled.add(group)
                if not group or group in filled:
                    _put(data, sheet.field, [d for _, d in found])
                lines[sheet.field] = [m for m, _ in found]
            for group in groups - filled:
                # Nothing filled in for a record kept inside (a cash ledger's
                # customer details): leave it out, as the form does.
                *parents, last = group.split(".")
                holder = data
                for part in parents:
                    holder = holder.get(part, {})
                holder.pop(last, None)
            if bad:
                problem(main, n, bad)
                continue
            try:
                with tenant_atomic():
                    action, name, changes = _save_row(
                        master, ctx, instance, data, sheets, known.get(n)
                    )
            except ValidationError as exc:
                _report(exc.detail, main, sheets, n, lines, labels, problem)
                continue
            except (DjangoValidationError, IntegrityError) as exc:
                problem(main, n, [f"Could not save: {exc}"])
                continue
            counts[action] += 1
            code = next((v for v in codes.values() if v), "")
            results.append(
                {"row": n, "action": action, "name": name, "code": code, "changes": changes}
            )
        for sheet, grouped, _ in children if only_rows is None else []:
            for key in sorted(k for f, k in unclaimed if f == sheet.field):
                for m, _ in grouped[key]:
                    problem(
                        sheet,
                        m,
                        [
                            f"{sheet.link_label}: {key!r} is not in the {main.title} sheet. "
                            f"Add the {master.noun} there too."
                        ],
                    )
        if not errors and master.after is not None:
            master.after(ctx)
        saved = commit and not errors
        if not saved:
            transaction.set_rollback(True, using=require_tenant().db_alias)
    errors.sort(key=lambda e: (e["sheet"] != main.title, e["sheet"], e["row"]))
    return {
        "rows": len(results)
        + len(same)
        + len({e["row"] for e in errors if e["sheet"] == main.title}),
        **counts,
        "errors": errors,
        "results": results,
        "saved": saved,
    }


def _same_text(kind: str, a: str, b: str) -> bool:
    """A cell as read back from Excel against the exported text: Excel may give
    a number back as 18 for "18.000000"."""
    a, b = a.strip(), b.strip()
    if a == b:
        return True
    if kind == "number" and a and b:
        try:
            return Decimal(a) == Decimal(b)
        except InvalidOperation:
            return False
    return False


def _unchanged(
    master, ctx, tables, header, body, id_at, at, code_at
) -> tuple[dict[int, set[str]], dict[int, list[dict]]]:
    """Each row of the file that names a record (by its ID or code) against the
    text an export gives for it now. Rows that would change nothing (the same
    text in every column the file has, the same lines on every list sheet the
    file has): row number -> the keys its list-sheet lines are filed under.
    The other rows: row number -> what they change, as {field, old, new}."""
    # Only the records the file names: a part of a big list must not read
    # the whole list (12,000 items took 26 s on staging, 2026-11-26).
    ids = {
        int(row[id_at].strip())
        for _, row in body
        if id_at is not None and id_at < len(row) and row[id_at].strip().isdigit()
    }
    only = Q(pk__in=ids)
    for _, row in body:
        if id_at is not None and id_at < len(row) and row[id_at].strip():
            continue
        for path, i in code_at.items():
            text = row[i].strip() if i < len(row) else ""
            if text:
                only |= master.codes[path].find(text)
    current = _tables_out(master, ctx, blank=False, only=only)
    main = current[0]
    col_at = {c.field: i + 1 for i, c in enumerate(main.sheet.columns)}
    kinds = {c.field: c.kind for c in main.sheet.columns}
    by_id = {r[0]: r for r in main.rows}
    by_code = {
        (path, r[col_at[path]].strip().lower()): r
        for path in code_at
        for r in main.rows
        if r[col_at[path]].strip()
    }
    link_col = col_at.get(master.link)

    # Lines of the list sheets, in the file and now, by sheet and owner.
    by_title = {title.strip().lower(): rows for title, rows in tables[1:]}
    lists = []
    for table in current[1:]:
        rows = by_title.get(table.sheet.title.lower())
        if rows is None:
            continue  # not in the file: an import leaves those lines alone
        child_header, child_body = _body(rows)
        link_at, child_at = _headers(table.sheet, child_header, table.sheet.link_label)
        if link_at is None:
            return {}, {}  # the import itself says what is wrong
        fields = list(child_at)
        positions = {c.field: i + 1 for i, c in enumerate(table.sheet.columns)}
        child_kinds = {c.field: c.kind for c in table.sheet.columns}
        given: dict[str, list[list[str]]] = {}
        for _, row in child_body:
            owner = row[link_at].strip().lower() if link_at < len(row) else ""
            given.setdefault(owner, []).append(
                [row[child_at[f]] if child_at[f] < len(row) else "" for f in fields]
            )
        now: dict[str, list[list[str]]] = {}
        for row in table.rows:
            now.setdefault(row[0].strip().lower(), []).append([row[positions[f]] for f in fields])
        kinds_in_order = [child_kinds[f] for f in fields]
        lists.append((table.sheet, given, now, kinds_in_order))

    labels = {c.field: c.label for c in main.sheet.columns}
    same: dict[int, set[str]] = {}
    known: dict[int, list[dict]] = {}
    for n, row in body:

        def cell(i, row=row) -> str:
            return row[i].strip() if i is not None and i < len(row) else ""

        ref = cell(id_at)
        record = by_id.get(ref) if ref else None
        if ref and record is None:
            continue
        for path, i in code_at.items():
            code = cell(i).lower()
            if record is None and code:
                record = by_code.get((path, code))
        if record is None:
            continue
        changes = [
            {"field": labels[f], "old": record[col_at[f]], "new": cell(i)}
            for f, i in at.items()
            if not _same_text(kinds[f], cell(i), record[col_at[f]])
            # a code found the record whatever its capitals, and never changes
            and not (f in code_at and cell(i).lower() == record[col_at[f]].strip().lower())
        ]
        keys = {ref.lower()} if ref else set()
        if link_col is not None:
            keys.add(record[link_col].strip().lower())
        owner = record[link_col].strip().lower() if link_col is not None else record[0]
        for sheet, given, now, child_kinds in lists:
            mine = [line for k in keys for line in given.get(k, [])]
            theirs = now.get(owner, [])
            if len(mine) != len(theirs):
                text = f"{len(theirs)} lines before, {len(mine)} now"
            else:
                n_changed = sum(
                    any(not _same_text(k, a, b) for k, a, b in zip(child_kinds, x, y, strict=True))
                    for x, y in zip(mine, theirs, strict=True)
                )
                if not n_changed:
                    continue
                text = f"{n_changed} line{'s' if n_changed != 1 else ''} changed"
            changes.append({"field": sheet.title, "old": "", "new": text})
        if changes:
            known[n] = changes
        else:
            same[n] = keys
    return same, known


# --- Import in steps (Sidharth, 2026-11-26: a big file with a progress bar) ---

COMPARE_STEP = 1000  # rows compared with MyERP per request
SAVE_STEP = 100  # rows checked and saved per request: well inside a request's time
SAMPLE = 10  # changes shown before "Import" (Sidharth 2026-11-26: the first 10)


def _job_tables(job) -> list[tuple[str, list[list[str]]]]:
    return [tuple(t) for t in json.loads(gzip.decompress(bytes(job.tables)))]


def start_import(master: Master, ctx: Context, user, name: str, content: bytes) -> dict:
    """Read the file and check only its layout: the sheets and columns are the
    master's, and every line of a list sheet names a record of the main sheet.
    Keeps the file as an ImportJob for the steps that follow."""
    from core.models import ImportJob

    tables = read_tables(name, content)
    sheets = master.sheets()
    main = sheets[0]
    header, body = _body(tables[0][1])
    if not header:
        raise ParseError("The file is empty.")
    id_at, at = _headers(main, header, ID_LABEL)
    if not at:
        raise ParseError("The first row must hold the column names, as in the exported file.")
    if len(body) > MAX_FILE_ROWS:
        raise ParseError(f"Import at most {MAX_FILE_ROWS} rows at a time.")
    errors: list[dict] = []
    link_at = at.get(master.link)
    keys = set()
    for _, row in body:
        if id_at is not None and id_at < len(row) and row[id_at].strip():
            keys.add(row[id_at].strip().lower())
        if link_at is not None and link_at < len(row) and row[link_at].strip():
            keys.add(row[link_at].strip().lower())
    by_title = {title.strip().lower(): rows for title, rows in tables[1:]}
    counted = [{"title": main.title, "rows": len(body)}]
    for sheet in sheets[1:]:
        rows = by_title.get(sheet.title.lower())
        if rows is None:
            continue
        child_header, child_body = _body(rows)
        first, _ = _headers(sheet, child_header, sheet.link_label)
        if first is None:
            raise ParseError(
                f"The {sheet.title} sheet must start with a {sheet.link_label} column."
            )
        counted.append({"title": sheet.title, "rows": len(child_body)})
        for n, row in child_body:
            owner = row[first].strip() if first < len(row) else ""
            if not owner:
                why = f"{sheet.link_label}: say which {master.noun} this row belongs to"
            elif link_at is not None and owner.lower() not in keys:
                why = (
                    f"{sheet.link_label}: {owner.lower()!r} is not in the {main.title} sheet. "
                    f"Add the {master.noun} there too."
                )
            else:
                continue
            errors.append({"sheet": sheet.title, "row": n, "messages": [why]})
    if errors:
        return {"job": None, "errors": errors[:500], "sheets": counted}
    ImportJob.objects.filter(user=ctx.request.user).delete()  # one at a time
    job = ImportJob.objects.create(
        user=ctx.request.user,
        master=master.key,
        company=ctx.company,
        file_name=name[:200],
        tables=gzip.compress(json.dumps(tables).encode(), compresslevel=5),
        rows=len(body),
        summary={"new": 0, "changed": 0, "same": 0, "results": []},
    )
    return {"job": job.pk, "errors": [], "sheets": counted, "rows": len(body)}


def compare_step(master: Master, ctx: Context, job) -> dict:
    """Compare the next rows with MyERP: which add a record, which change one
    (and what), which change nothing. Nothing is checked or saved."""
    _names.clear()
    _running.set(ctx)
    tables = _job_tables(job)
    main = master.sheets()[0]
    header, body = _body(tables[0][1])
    id_at, at = _headers(main, header, ID_LABEL)
    code_at = _code_columns(master, main, header)
    part = body[job.compared : job.compared + COMPARE_STEP]
    same, known = _unchanged(master, ctx, tables, header, part, id_at, at, code_at)
    summary = job.summary
    name_at = at.get(master.link)
    for n, row in part:
        if n in same:
            summary["same"] += 1
            continue
        ref = row[id_at].strip() if id_at is not None and id_at < len(row) else ""
        action = "changed" if n in known or ref else "new"
        summary[action] += 1
        job.todo.append(n)
        if len(summary["results"]) < SAMPLE:

            def cell(i, row=row) -> str:
                return row[i].strip() if i is not None and i < len(row) else ""

            summary["results"].append(
                {
                    "row": n,
                    "action": action,
                    "name": cell(name_at),
                    "code": next((cell(i) for i in code_at.values() if cell(i)), ""),
                    "changes": known.get(n, []),
                }
            )
    job.compared += len(part)
    job.save(update_fields=["compared", "todo", "summary"])
    return _progress(job)


def save_step(master: Master, ctx: Context, job) -> dict:
    """Check and save the next rows that add or change a record, the form's way.
    A problem in any of them saves none of this step and stops the import; the
    steps before stay saved (importing the same file again passes them over)."""
    step = job.todo[job.done : job.done + SAVE_STEP]
    out = run_import(master, ctx, _job_tables(job), True, only_rows=set(step))
    if out["errors"]:
        return {**_progress(job), "errors": out["errors"]}
    job.done += len(step)
    job.summary["saved_new"] = job.summary.get("saved_new", 0) + out["new"]
    job.summary["saved_changed"] = job.summary.get("saved_changed", 0) + out["changed"]
    job.save(update_fields=["done", "summary"])
    return _progress(job)


def _progress(job) -> dict:
    summary = job.summary
    return {
        "job": job.pk,
        "rows": job.rows,
        "compared": job.compared,
        "new": summary["new"],
        "changed": summary["changed"],
        "same": summary["same"],
        "results": summary["results"],
        "total": len(job.todo),
        "done": job.done,
        "saved_new": summary.get("saved_new", 0),
        "saved_changed": summary.get("saved_changed", 0),
        "errors": [],
    }


def _report(detail, main: Sheet, sheets: list[Sheet], n: int, lines, labels, problem) -> None:
    """Put a save's errors on the rows they are about: a child row's own
    problem goes on its line of the child sheet, the rest on the record's row,
    each starting with its column."""
    lists = {s.field: s for s in sheets[1:]}
    groups = {c.group for c in main.columns} - {""}
    own: list[str] = []

    def walk(detail, prefix: str) -> None:
        if not isinstance(detail, dict):
            own.extend(_messages(detail, {}))
            return
        for key, value in detail.items():
            if key == "existing":
                continue  # the link to a duplicate's record is for the screen
            if key in ("non_field_errors", "__all__", "detail"):
                own.extend(_messages(value, {}))
                continue
            path = f"{prefix}{key}"
            sheet = lists.get(path)
            if sheet is not None:
                rows = lines.get(path, [])
                child_labels = {c.field: c.label for c in sheet.columns}
                items = value.items() if isinstance(value, dict) else enumerate(value)
                for i, item in items:
                    if isinstance(i, int) and isinstance(item, dict | list) and item:
                        if i < len(rows):
                            problem(sheet, rows[i], _messages(item, child_labels))
                        else:
                            own.extend(f"{sheet.title}: {m}" for m in _messages(item, child_labels))
                    elif item:
                        own.extend(f"{sheet.title}: {m}" for m in _messages(item, {}))
                continue
            if path in groups and isinstance(value, dict):
                walk(value, f"{path}.")
                continue
            own.extend(_messages(value, {}, f"{labels.get(path, key)}: "))

    walk(detail, "")
    if own:
        problem(main, n, own)


def _save_row(
    master: Master,
    ctx: Context,
    instance,
    data: dict,
    sheets: list[Sheet],
    known: list[dict] | None = None,
) -> tuple[str, str, list[dict]]:
    """Save one row the screen's way: ("new" | "changed" | "same", the
    record's name, what changed as [{field, old, new}]). `known`: what the row
    changes, found by comparing it with an export (then the record is not read
    again before and after, which took a third of the time)."""
    if known is not None and instance is not None:
        serializer = master.serializer(
            instance, data=data, partial=True, context={"request": ctx.request}
        )
        serializer.is_valid(raise_exception=True)
        record = master.save(ctx, instance, dict(serializer.validated_data))
        return "changed", str(record), known
    context = {"request": ctx.request}
    # Before and after as an export shows them: without the per-record "in use"
    # checks, a dozen queries an item that no column holds (the save still
    # refuses a change to a key field in use).
    shown = {**context, "list": True}
    before = None
    if instance is not None:
        before = dict(master.serializer(instance, context=shown).data)
    serializer = master.serializer(
        instance, data=data, partial=instance is not None, context=context
    )
    serializer.is_valid(raise_exception=True)
    record = master.save(ctx, instance, dict(serializer.validated_data))
    if instance is None:
        return "new", str(record), []
    record = master.queryset(ctx).get(pk=record.pk)
    after = dict(master.serializer(record, context=shown).data)
    if after == before:
        return "same", str(record), []
    return "changed", str(record), _changes(sheets, before, after)


def _changes(sheets: list[Sheet], before: dict, after: dict) -> list[dict]:
    """What a row changed, as the file shows it: each changed column of the
    main sheet with its old and new text, and each list (units, parts) whose
    lines changed."""
    out = []
    for c in sheets[0].columns:
        old = c.codec.to_cell(_get(before, c.field))
        new = c.codec.to_cell(_get(after, c.field))
        if old != new:
            out.append({"field": c.label, "old": old, "new": new})
    for sheet in sheets[1:]:

        def lines(record, sheet=sheet):
            return [
                [c.codec.to_cell(_get(x, c.field)) for c in sheet.columns]
                for x in _get(record, sheet.field) or []
            ]

        old, new = lines(before), lines(after)
        if old != new:
            if len(old) == len(new):
                n = sum(a != b for a, b in zip(old, new, strict=True))
                text = f"{n} line{'s' if n != 1 else ''} changed"
            else:
                text = f"{len(old)} lines before, {len(new)} now"
            out.append({"field": sheet.title, "old": "", "new": text})
    return out


def _code_columns(master: Master, main: Sheet, header: list[str]) -> dict[str, int]:
    """Where the master's code columns are in the file: field path -> position."""
    names = {h.strip().lower(): i for i, h in enumerate(header)}
    out = {}
    for c in main.columns:
        if c.field in master.codes:
            i = names.get(c.label.lower(), names.get(c.field.lower()))
            if i is not None:
                out[c.field] = i
    return out


def _by_code(
    master: Master, ctx: Context, instance, ref: str, codes: dict[str, str], keep: bool
) -> tuple[Any, list[str]]:
    """The record a row is about, found by its code when the ID is empty, and
    what is wrong with the row's codes: a code is never changed by an import."""
    problems = []
    if instance is None and not ref:
        for path, text in codes.items():
            if not text:
                continue
            found = (
                master.queryset(ctx)
                .filter(master.codes[path].find(text))
                .select_for_update(of=("self",))
                .first()
            )
            if found is not None:
                instance = found
                break
    if instance is None or not keep:
        return instance, problems
    for path, text in codes.items():
        now = master.codes[path].of(instance) or ""
        if text and now and text.lower() != now.lower():
            label = next(c.label for c in master.columns() if c.field == path)
            where = f"the ID {ref} is" if ref else "this row is"
            problems.append(
                f"{label}: {where} the {master.noun} {now}, and its {label.lower()} "
                f"never changes. Put back {now}, or leave the ID and {label} empty to "
                f"add a new {master.noun}."
            )
    return instance, problems


# --- Views -------------------------------------------------------------------


def _master(key: str) -> Master:
    master = MASTERS.get(key)
    if master is None:
        raise NotFound("No such master.")
    return master


def _context(request, master: Master) -> Context:
    company = None
    if master.per_company:
        raw = request.query_params.get("company") or request.data.get("company")
        if not raw or not str(raw).isdigit():
            raise ValidationError({"company": ["Pick a company."]})
        company = _company(request, int(raw))
    return Context(request=request, company=company)


def _scope_name(ctx: Context) -> str:
    return ctx.company.name if ctx.company else require_tenant().name


def _printed(master: Master, tables: list[Table]) -> list[dict]:
    """The tables as a printed report: the master's report columns (or all),
    without the ID and without columns that are empty in every row."""
    out = []
    for n, t in enumerate(tables):
        headers, rows = (t.headers[1:], [r[1:] for r in t.rows]) if n == 0 else (t.headers, t.rows)
        if n == 0 and master.report:
            wanted = {c.label for c in t.sheet.columns if c.field in master.report}
            keep = [i for i, h in enumerate(headers) if h in wanted]
            headers, rows = [headers[i] for i in keep], [[r[i] for i in keep] for r in rows]
        if n > 0 and not rows:
            continue  # no parts, bills or contacts at all: nothing to print
        if rows:
            keep = [i for i in range(len(headers)) if any(r[i] for r in rows)]
            headers, rows = [headers[i] for i in keep], [[r[i] for i in keep] for r in rows]
        right = [printout.numeric([r[i] for r in rows]) for i in range(len(headers))]
        rows = [[printout.indian(v) if right[i] else v for i, v in enumerate(r)] for r in rows]
        out.append({"title": t.sheet.title, "columns": headers, "rows": rows, "right": right})
    return out


class ExportView(APIView):
    """GET ?as=xlsx|csv|json|pdf [&blank=1] [&company=ID]."""

    permission_classes = [Signed]

    def get(self, request, key: str):
        _check(request, VIEW)
        master = _master(key)
        ctx = _context(request, master)
        blank = request.query_params.get("blank") == "1"
        tables = _tables_out(master, ctx, blank)
        fmt = request.query_params.get("as", "xlsx")
        if fmt == "json":
            return Response(
                {
                    "title": master.label,
                    "scope": _scope_name(ctx),
                    "sheets": _printed(master, tables),
                }
            )
        stem = f"{key}-{'template' if blank else datetime.date.today().isoformat()}"
        if fmt == "pdf":
            return printout.pdf_response(
                master.label,
                _scope_name(ctx),
                _printed(master, tables),
                stem,
            )
        if fmt == "csv":
            body, mime, ext = _csv(tables[0]), "text/csv; charset=utf-8", "csv"
        else:
            body = _xlsx(master, tables)
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
        response = HttpResponse(body, content_type=mime)
        response["Content-Disposition"] = f'attachment; filename="{stem}.{ext}"'
        return response


class ImportView(APIView):
    """POST a file (multipart "file"); "commit" = "1" saves, else only checks."""

    permission_classes = [Signed]
    parser_classes = [MultiPartParser]

    def post(self, request, key: str):
        _check(request, EDIT)
        if not request.user.can(IMPORT):
            raise PermissionDenied("Your role does not allow importing from a file.")
        master = _master(key)
        ctx = _context(request, master)
        upload = request.FILES.get("file")
        if upload is None:
            raise ParseError("Choose a file to import.")
        if upload.size > MAX_BYTES:
            raise ParseError(
                f"The file is too big; import at most {MAX_BYTES // 1024 // 1024} MB at a time."
            )
        tables = read_tables(upload.name, upload.read())
        notes: list[str] = []
        extra: dict = {}
        source = request.data.get("source") or ""
        if source:
            if not require_tenant().migration_tools:
                raise PermissionDenied(
                    "Migration Tools are switched off for your group. Ask MyERP support."
                )
            reader = master.sources.get(source)
            if reader is None:
                raise ParseError(f"{master.label} cannot be imported from that kind of file.")
            name_map = request.FILES.get("map")
            if name_map is not None and name_map.size > MAX_BYTES:
                raise ParseError("The name map file is too big.")
            options = {
                "map": read_tables(name_map.name, name_map.read()) if name_map else None,
                "skip_disabled": request.data.get("skip_disabled") == "1",
                "delivery_hsn": str(request.data.get("delivery_hsn") or "").strip(),
                "part": request.data.get("part") or "0",
            }
            tables, notes, extra = reader(tables, options)
        out = run_import(
            master, ctx, tables, request.data.get("commit") == "1", keep_codes=not source
        )
        return Response({**out, "notes": notes, **extra})


class ImportStartView(APIView):
    """POST a file (multipart "file"): its layout is checked and it is kept
    for the steps of a stepped import. Returns the job, or the layout's problems."""

    permission_classes = [Signed]
    parser_classes = [MultiPartParser]

    def post(self, request, key: str):
        master, ctx = _import_allowed(request, key)
        upload = request.FILES.get("file")
        if upload is None:
            raise ParseError("Choose a file to import.")
        if upload.size > MAX_BYTES:
            raise ParseError(
                f"The file is too big; import at most {MAX_BYTES // 1024 // 1024} MB at a time."
            )
        with tenant_atomic():
            return Response(start_import(master, ctx, request.user, upload.name, upload.read()))


class ImportStepView(APIView):
    """POST .../import/<job>/compare/ or .../save/: the next step. DELETE
    .../import/<job>/ drops the kept file."""

    permission_classes = [Signed]

    def _job(self, request, key: str, job_id: int):
        from core.models import ImportJob

        master, ctx = _import_allowed(request, key)
        job = (
            ImportJob.objects.select_for_update()
            .filter(pk=job_id, user=request.user, master=key, company=ctx.company)
            .first()
        )
        if job is None:
            raise NotFound("This import has ended. Choose the file and check it again.")
        return master, ctx, job

    def post(self, request, key: str, job_id: int, step: str):
        with tenant_atomic():
            master, ctx, job = self._job(request, key, job_id)
            if step == "compare":
                return Response(compare_step(master, ctx, job))
            if step == "save":
                if job.compared < job.rows:
                    raise ParseError("Check the whole file before importing it.")
                return Response(save_step(master, ctx, job))
        raise NotFound()

    def delete(self, request, key: str, job_id: int):
        with tenant_atomic():
            _, _, job = self._job(request, key, job_id)
            job.delete()
        return Response(status=204)


def _import_allowed(request, key: str) -> tuple[Master, Context]:
    _check(request, EDIT)
    if not request.user.can(IMPORT):
        raise PermissionDenied("Your role does not allow importing from a file.")
    master = _master(key)
    return master, _context(request, master)
