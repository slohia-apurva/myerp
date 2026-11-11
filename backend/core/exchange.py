"""Import, export and print for every masters screen.

One framework serves every master. Each master registers itself once with
`register(Master(...))`, naming its serializer and its save function: the very
ones its own screen uses. From those:

- the columns of the file are the serializer's writable fields, labelled as
  the audit log labels them, so a field added to a form's serializer appears
  in the file by itself (a field the framework cannot put in one cell must be
  given a `Codec` or listed in `exclude`, or registration fails loudly);
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
import io
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.recorder import LABELS
from core.api import EDIT, VIEW, Signed, _check, _company
from tenancy.context import require_tenant, tenant_atomic

IMPORT = "masters.import"
MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024
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
    exclude: tuple[str, ...] = ()
    codecs: dict[str, Codec] = field(default_factory=dict)
    # Extra lines for the "How to fill" sheet, field -> text.
    hints: dict[str, str] = field(default_factory=dict)

    def columns(self) -> list[Column]:
        out = []
        for name, f in self.serializer().fields.items():
            if f.read_only or name in self.exclude:
                continue
            codec = self.codecs.get(name) or _default_codec(f)
            if codec is None:
                raise ImproperlyConfigured(
                    f"Import/export for {self.key}: the field {name!r} "
                    f"({type(f).__name__}) needs a Codec in `codecs`, or list it in `exclude`."
                )
            out.append(
                Column(
                    field=name,
                    label=_label(name, f),
                    kind=codec.kind or _kind(f),
                    required=bool(f.required),
                    codec=codec,
                    allow_null=bool(getattr(f, "allow_null", False)),
                )
            )
        return out


MASTERS: dict[str, Master] = {}


def register(master: Master) -> None:
    master.columns()  # fail at start-up, not when someone exports
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
    clean = re.sub(r"[,\s₹]", "", text)
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


def _choice_codec(f: serializers.ChoiceField) -> Codec:
    def to_cell(value) -> str:
        return "" if value in (None, "") else str(f.choices.get(value, value))

    def from_cell(text: str):
        low = text.strip().lower()
        for value, label in f.choices.items():
            if low in (str(value).lower(), str(label).lower()):
                return value
        raise ValueError(f"{text!r} is not one of: {', '.join(map(str, f.choices.values()))}")

    return Codec(to_cell, from_cell, choices=lambda: [str(v) for v in f.choices.values()])


def _plain(value) -> str:
    return "" if value is None else str(value)


def _default_codec(f) -> Codec | None:
    if isinstance(f, serializers.BooleanField):
        return Codec(lambda v: "Yes" if v else "No", _yesno, choices=lambda: ["Yes", "No"])
    if isinstance(f, serializers.ChoiceField) and not isinstance(
        f, serializers.MultipleChoiceField
    ):
        return _choice_codec(f)
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
    return None  # relations, lists, nested forms: the master must say how


def _hint(col: Column, master: Master) -> str:
    parts = []
    if col.field in master.hints:
        parts.append(master.hints[col.field])
    if col.codec.choices is not None:
        parts.append("One of: " + ", ".join(col.codec.choices()))
    if col.codec.hint:
        parts.append(col.codec.hint)
    return ". ".join(parts)


# --- Files -------------------------------------------------------------------


def _rows_out(master: Master, ctx: Context, blank: bool) -> tuple[list[Column], list[list[str]]]:
    columns = master.columns()
    if blank:
        return columns, []
    records = master.queryset(ctx)
    data = master.serializer(records, many=True, context={"request": ctx.request}).data
    rows = [[str(r["id"])] + [c.codec.to_cell(r.get(c.field)) for c in columns] for r in data]
    return columns, rows


def _xlsx(master: Master, columns: list[Column], rows: list[list[str]]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = master.label[:31]
    headers = [ID_LABEL] + [c.label for c in columns]
    ws.append(headers)
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="E3F2E8")
    for cell in ws[1]:
        cell.font, cell.fill = bold, fill
    kinds = ["number"] + [c.kind for c in columns]
    for row in rows:
        pairs = zip(kinds, row, strict=True)
        ws.append([_number_cell(v) if k == "number" else v for k, v in pairs])
    for i, header in enumerate(headers, start=1):
        width = max([len(header)] + [len(r[i - 1]) for r in rows[:500]]) + 2
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = min(max(width, 8), 50)
        # Keep codes such as HSN 0401 or PIN 011001 as text, not numbers.
        kind = "number" if i == 1 else columns[i - 2].kind
        if kind != "number":
            ws.column_dimensions[letter].number_format = "@"
            for cell in ws[letter][1:]:
                cell.number_format = "@"
    ws.freeze_panes = "B2"

    help_ws = wb.create_sheet("How to fill")
    help_ws.append(["Column", "Must fill", "What to write"])
    for cell in help_ws[1]:
        cell.font, cell.fill = bold, fill
    help_ws.append(
        [ID_LABEL, "No", "Keep the ID to change that record. Leave it empty to add a new one."]
    )
    for c in columns:
        help_ws.append([c.label, "Yes" if c.required else "No", _hint(c, master)])
    help_ws.column_dimensions["A"].width = 28
    help_ws.column_dimensions["B"].width = 10
    help_ws.column_dimensions["C"].width = 90
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _number_cell(text: str):
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return text
    return int(value) if value == value.to_integral_value() else float(value)


def _csv(columns: list[Column], rows: list[list[str]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([ID_LABEL] + [c.label for c in columns])
    writer.writerows(rows)
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


def read_table(name: str, content: bytes) -> list[list[str]]:
    """The file's first sheet as rows of text (header row first)."""
    if content[:2] == b"PK":  # .xlsx files are zip archives
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ParseError("This Excel file could not be read.") from exc
        ws = wb.worksheets[0]
        return [[_cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)]
    if name.lower().endswith((".xls", ".ods")):
        raise ParseError("Save the file as Excel (.xlsx) or CSV and try again.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text))]


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


def run_import(master: Master, ctx: Context, table: list[list[str]], commit: bool) -> dict:
    """Check (and, when `commit`, save) every row. Nothing is saved unless all
    rows pass. Returns a summary with the problems row by row."""
    columns = master.columns()
    by_header = {}
    for c in columns:
        by_header[c.label.lower()] = c
        by_header[c.field.lower()] = c
    while table and not any(table[0]):
        table = table[1:]
    if not table:
        raise ParseError("The file is empty.")
    header, body = table[0], table[1:]
    id_at, at = None, {}
    unknown = []
    for i, name in enumerate(header):
        key = name.strip().lower()
        if not key:
            continue
        if key == ID_LABEL.lower():
            id_at = i
        elif key in by_header:
            at[by_header[key].field] = i
        else:
            unknown.append(name)
    if unknown:
        raise ParseError(
            f"These columns are not {master.label} columns: {', '.join(unknown)}. "
            "Start from an exported file or the blank template."
        )
    if not at:
        raise ParseError("The first row must hold the column names, as in the exported file.")
    if len(body) > MAX_ROWS:
        raise ParseError(f"Import at most {MAX_ROWS} rows at a time.")
    labels = {c.field: c.label for c in columns}
    picked = [c for c in columns if c.field in at]

    results, errors = [], []
    counts = {"new": 0, "changed": 0, "same": 0}
    with tenant_atomic():
        for n, row in enumerate(body, start=2):
            if not any(cell.strip() for cell in row):
                continue
            cell = lambda i, row=row: row[i].strip() if i is not None and i < len(row) else ""  # noqa: E731
            problems, data = [], {}
            for c in picked:
                text = cell(at[c.field])
                if not text:
                    if c.kind == "text":
                        data[c.field] = ""
                    elif c.allow_null:
                        data[c.field] = None
                    continue  # keep what is there, or the form's default
                try:
                    data[c.field] = c.codec.from_cell(text)
                except ValueError as exc:
                    problems.append(f"{c.label}: {exc}")
            instance = None
            ref = cell(id_at)
            if ref:
                try:
                    instance = master.queryset(ctx).select_for_update().get(pk=int(ref))
                except (ValueError, ObjectDoesNotExist):
                    problems.append(
                        f"ID: there is no {master.noun} with ID {ref}. "
                        "Leave the ID empty to add a new one."
                    )
            if problems:
                errors.append({"row": n, "messages": problems})
                continue
            try:
                with tenant_atomic():
                    action, name = _save_row(master, ctx, instance, data)
            except ValidationError as exc:
                errors.append({"row": n, "messages": _messages(exc.detail, labels)})
                continue
            except (DjangoValidationError, IntegrityError) as exc:
                errors.append({"row": n, "messages": [f"Could not save: {exc}"]})
                continue
            counts[action] += 1
            results.append({"row": n, "action": action, "name": name})
        saved = commit and not errors
        if not saved:
            transaction.set_rollback(True, using=require_tenant().db_alias)
    return {
        "rows": len(results) + len(errors),
        **counts,
        "errors": errors,
        "results": results,
        "saved": saved,
    }


def _save_row(master: Master, ctx: Context, instance, data: dict) -> tuple[str, str]:
    context = {"request": ctx.request}
    before = None
    if instance is not None:
        before = dict(master.serializer(instance, context=context).data)
    serializer = master.serializer(
        instance, data=data, partial=instance is not None, context=context
    )
    serializer.is_valid(raise_exception=True)
    record = master.save(ctx, instance, dict(serializer.validated_data))
    if instance is None:
        return "new", str(record)
    record.refresh_from_db()
    after = dict(master.serializer(record, context=context).data)
    return ("same" if after == before else "changed"), str(record)


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


class ExportView(APIView):
    """GET ?as=xlsx|csv|json [&blank=1] [&company=ID]."""

    permission_classes = [Signed]

    def get(self, request, key: str):
        _check(request, VIEW)
        master = _master(key)
        ctx = _context(request, master)
        blank = request.query_params.get("blank") == "1"
        columns, rows = _rows_out(master, ctx, blank)
        fmt = request.query_params.get("as", "xlsx")
        if fmt == "json":
            return Response(
                {
                    "title": master.label,
                    "scope": _scope_name(ctx),
                    "columns": [c.label for c in columns],
                    "rows": [r[1:] for r in rows],
                }
            )
        stem = f"{key}-{'template' if blank else datetime.date.today().isoformat()}"
        if fmt == "csv":
            body, mime, ext = _csv(columns, rows), "text/csv; charset=utf-8", "csv"
        else:
            body = _xlsx(master, columns, rows)
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
            raise ParseError("The file is too big; import at most 5 MB at a time.")
        table = read_table(upload.name, upload.read())
        return Response(run_import(master, ctx, table, request.data.get("commit") == "1"))
