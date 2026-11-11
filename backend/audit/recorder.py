"""Writes the audit log.

Every save or delete of a tracked master (see TRACKED) becomes one
AuditEntry, through Django's model signals, so new code paths are covered
without remembering to call anything.

Within one web request, all saves of the same record are merged into one
entry, compared with the record as it was before the request. That keeps a
screen's single "Save" as a single entry even when the code saves the record
twice, or changes things kept beside it (a ledger's opening bills, a user's
roles), which `touch(record)` folds in.

Signals do not fire for `QuerySet.update()` or `bulk_create()`; code that
changes a tracked master must save each record instead.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db import models
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save

# Field labels as the screens show them, where Django's default
# (the field name with spaces) would read oddly.
LABELS = {
    "abbr": "Short code",
    "gstin": "GSTIN",
    "pan": "PAN",
    "tan": "TAN",
    "cin": "CIN / LLPIN",
    "state_code": "State",
    "pincode": "PIN code",
    "fiscal_year_start_month": "Financial year starts in",
    "books_start": "Books beginning from",
    "multi_currency": "Foreign currencies",
    "is_active": "Active",
    "is_head_office": "Head office",
    "default_billing": "Default billing address",
    "default_ship_to": "Default ship to",
    "default_ship_from": "Default ship from",
    "kind": "Type",
    "valid_until": "Renewal date",
    "parent": "Under",
    "group": "Under group",
    "schedule_iii": "Schedule III head",
    "affects_gross_profit": "Affects gross profit",
    "bank_branch": "Bank branch",
    "ifsc": "IFSC",
    "opening_amount": "Opening balance (₹)",
    "opening_side": "Opening Dr/Cr",
    "bill_wise": "Bill by bill",
    "opening_fc_amount": "Opening balance (foreign currency)",
    "opening_rate": "Opening rate",
    "full_name": "Full name",
    "credit_limit": "Credit limit (₹)",
    "short_name": "Short name",
    "gst_code": "GST unit code",
    "item_number": "Item number",
    "hsn": "HSN",
    "shelf_life_days": "Shelf life (days)",
    "batch_tracked": "Batches tracked",
    "qc_required": "Quality check on receipt",
    "item_type": "Type",
    "whole_numbers": "Whole numbers only",
}

# Fields that are internal or change by themselves.
SKIP = {
    "id",
    "created_at",
    "base_currency",
    "code",
    "sequence",
    "is_standard",
    "password",
    "last_login",
    "date_joined",
    "google_sub",
    "is_superuser",
    "party",  # a ledger's party shows through its party extras
    "salesman",  # likewise, by name
}

Snapshot = dict[str, tuple[str, Any]]  # field -> (label, value as shown)


@dataclass(frozen=True)
class Tracked:
    """How one model is logged."""

    key: str  # record_type in AuditEntry, e.g. "ledger"
    label: str  # e.g. "Ledger"
    company: Callable[[models.Model], int | None]
    # Things kept beside the record that people edit on the same form,
    # e.g. a ledger's opening bills: field -> (label, function giving its value).
    extras: dict[str, tuple[str, Callable[[Any], Any]]] = field(default_factory=dict)
    formats: dict[str, Callable[[Any], Any]] = field(default_factory=dict)


TRACKED: dict[type[models.Model], Tracked] = {}


def _register() -> None:
    from accounts.models import Role, User
    from core import india
    from core import modules as company_modules
    from core.models import (
        Branch,
        Certificate,
        Company,
        CreditTerm,
        Item,
        Ledger,
        LedgerGroup,
        Unit,
    )
    from core.parties import party_extras

    def state(code):
        return india.STATES.get(code, code) if code else None

    module_labels = {code: label for code, label, *_ in company_modules.MODULES}

    def names(qs) -> str | None:
        return ", ".join(sorted(str(x) for x in qs)) or None

    def bills(ledger) -> str | None:
        rows = []
        for b in ledger.opening_bills.order_by("bill_date", "ref"):
            text = f"{b.ref} of {b.bill_date:%d-%m-%Y}"
            if b.due_date:
                text += f" due {b.due_date:%d-%m-%Y}"
            if b.fc_amount:
                text += f", {b.fc_amount} at {_number(b.rate)}"
            rows.append(f"{text}, {b.get_side_display()} {b.amount}")
        return "; ".join(rows) or None

    by_company = lambda r: r.company_id  # noqa: E731
    TRACKED.update(
        {
            Company: Tracked(
                "company",
                "Company",
                lambda r: r.pk,
                formats={
                    "state_code": state,
                    "modules": lambda v: ", ".join(module_labels.get(c, c) for c in v) or None,
                    "fiscal_year_start_month": lambda m: datetime.date(2000, m, 1).strftime("%B"),
                },
            ),
            Branch: Tracked("branch", "Branch", by_company, formats={"state_code": state}),
            Certificate: Tracked("certificate", "Licence or certificate", by_company),
            LedgerGroup: Tracked("ledger_group", "Ledger group", by_company),
            Ledger: Tracked(
                "ledger",
                "Ledger",
                by_company,
                extras={"opening_bills": ("Opening bills", bills), **party_extras()},
            ),
            CreditTerm: Tracked(
                "credit_term",
                "Credit terms",
                lambda r: None,
                extras={"parts": ("Parts", lambda t: "; ".join(map(str, t.parts.all())) or None)},
            ),
            Unit: Tracked("unit", "Unit", lambda r: None),
            Item: Tracked(
                "item",
                "Item",
                lambda r: None,
                extras={
                    "units": (
                        "Units",
                        lambda i: "; ".join(
                            f"{u.unit} (stock unit)"
                            if u.contains_unit_id is None
                            else f"{u.unit} = {_number(u.contains_qty)} {u.contains_unit}"
                            f" ({_number(u.factor)} {i.stock_unit})"
                            for u in i.units.all()
                        )
                        or None,
                    )
                },
            ),
            User: Tracked(
                "user",
                "User",
                lambda r: None,
                extras={
                    "roles": ("Roles", lambda u: names(u.roles.all())),
                    "companies": ("Companies", lambda u: names(u.companies.all()) or "All"),
                },
            ),
            Role: Tracked("role", "Role", lambda r: None),
        }
    )


TYPE_LABELS: dict[str, str] = {}


def _number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _shown(f: models.Field, record: models.Model, formats) -> Any:
    """A field's value as people would read it."""
    if f.name in formats:
        value = f.value_from_object(record)
        return None if value in (None, "") else formats[f.name](value)
    if f.is_relation:
        related = getattr(record, f.name)
        return str(related) if related is not None else None
    value = f.value_from_object(record)
    if value is None or value == "":
        return None
    if f.choices:
        return getattr(record, f"get_{f.name}_display")()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        # Compare at the field's precision: 0 and 0.00 are the same amount.
        value = value.quantize(Decimal(1).scaleb(-f.decimal_places))
        return format(value, "f") if f.decimal_places == 2 else _number(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(map(str, value)) or None
    return value if isinstance(value, str | int | float) else str(value)


def snapshot(record: models.Model) -> Snapshot:
    spec = TRACKED[type(record)]
    out: Snapshot = {}
    for f in record._meta.concrete_fields:
        if f.name in SKIP or (f.is_relation and f.name == "company"):
            continue
        label = LABELS.get(f.name) or str(f.verbose_name)[:1].upper() + str(f.verbose_name)[1:]
        out[f.name] = (label, _shown(f, record, spec.formats))
    if record.pk is not None:
        for name, (label, read) in spec.extras.items():
            out[name] = (label, read(record))
    return out


def _empty(value) -> bool:
    return value in (None, "", "No", "0.00", "0")


def _changes(before: Snapshot | None, after: Snapshot) -> list[dict]:
    if before is None:  # a new record: everything that was filled in
        return [
            {"field": k, "label": label, "old": None, "new": v}
            for k, (label, v) in after.items()
            if not _empty(v)
        ]
    return [
        {"field": k, "label": label, "old": before.get(k, (label, None))[1], "new": v}
        for k, (label, v) in after.items()
        if before.get(k, (label, None))[1] != v
    ]


# --- Who is making the change, and merging saves within one request ------


@dataclass
class _Pending:
    before: Snapshot | None  # None: the record was added in this scope
    entry: Any = None  # the AuditEntry written so far, if any


@dataclass
class _Scope:
    user: Any = None
    pending: dict[tuple[str, int], _Pending] = field(default_factory=dict)
    paused: bool = False


_scope: ContextVar[_Scope | None] = ContextVar("myerp_audit_scope", default=None)


@contextmanager
def scope(user=None) -> Iterator[None]:
    """Group the changes made in this block, made by `user`.
    The audit middleware opens one per request."""
    token = _scope.set(_Scope(user=user))
    try:
        yield
    finally:
        _scope.reset(token)


@contextmanager
def paused() -> Iterator[None]:
    """Changes in this block are not logged: MyERP's own setup, such as the
    standard ledger groups every new company starts with."""
    current = _scope.get()
    token = _scope.set(_Scope(user=current.user if current else None, paused=True))
    try:
        yield
    finally:
        _scope.reset(token)


def _current_user(s: _Scope):
    user = s.user
    if user is not None and not getattr(user, "is_authenticated", False):
        return None
    return user


def _write(record, key, pending: _Pending, action: str, changes: list[dict], s: _Scope):
    from audit.models import AuditEntry

    db = record._state.db
    entry = pending.entry
    if entry is not None:
        entry._recorder_amend = True
        if not changes and action != AuditEntry.DELETE:
            entry.delete(using=db)
            pending.entry = None
            return
        entry.action = action if entry.action != AuditEntry.CREATE else entry.action
        entry.changes, entry.record_name = changes, str(record)[:200]
        entry.save(using=db)
        return
    if not changes and action == AuditEntry.UPDATE:
        return
    user = _current_user(s)
    spec = TRACKED[type(record)]
    pending.entry = AuditEntry.objects.using(db).create(
        user=user,
        user_name=(user.display_name if user else "MyERP")[:150],
        company_id=spec.company(record),
        record_type=key[0],
        record_id=key[1],
        record_name=str(record)[:200],
        action=action,
        changes=changes,
    )


def _active_scope() -> tuple[_Scope, bool]:
    """The open scope, or a one-off one for saves outside a request."""
    s = _scope.get()
    return (s, False) if s is not None else (_Scope(), True)


def _on_pre_save(sender, instance, raw=False, **kwargs):
    if raw or sender not in TRACKED:
        return
    s, _ = _active_scope()
    if s.paused:
        return
    if instance.pk is None or instance._state.adding:
        before = None
    else:
        old = sender._default_manager.using(instance._state.db).filter(pk=instance.pk).first()
        before = snapshot(old) if old is not None else None
    instance._audit_before = before


def _on_post_save(sender, instance, created, raw=False, **kwargs):
    from audit.models import AuditEntry

    if raw or sender not in TRACKED:
        return
    s, one_off = _active_scope()
    if s.paused:
        return
    key = (TRACKED[sender].key, instance.pk)
    pending = s.pending.get(key)
    if pending is None:
        pending = _Pending(before=None if created else getattr(instance, "_audit_before", None))
        if not one_off:
            s.pending[key] = pending
    action = AuditEntry.CREATE if pending.before is None else AuditEntry.UPDATE
    _write(instance, key, pending, action, _changes(pending.before, snapshot(instance)), s)


def touch(record: models.Model) -> None:
    """Fold changes made beside a record (its extras) into its entry."""
    from audit.models import AuditEntry

    sender = type(record)
    s = _scope.get()
    if sender not in TRACKED or s is None or s.paused:
        return
    key = (TRACKED[sender].key, record.pk)
    pending = s.pending.get(key)
    if pending is None:
        return  # the record itself was not saved in this request
    action = AuditEntry.CREATE if pending.before is None else AuditEntry.UPDATE
    _write(record, key, pending, action, _changes(pending.before, snapshot(record)), s)


def _on_pre_delete(sender, instance, **kwargs):
    if sender in TRACKED:
        instance._audit_last = snapshot(instance)


def _on_post_delete(sender, instance, **kwargs):
    from audit.models import AuditEntry

    if sender not in TRACKED:
        return
    s, _ = _active_scope()
    if s.paused:
        return
    last = getattr(instance, "_audit_last", None) or {}
    changes = [
        {"field": k, "label": label, "old": v, "new": None}
        for k, (label, v) in last.items()
        if not _empty(v)
    ]
    key = (TRACKED[sender].key, instance.pk)
    pending = s.pending.pop(key, None) or _Pending(before=last)
    _write(instance, key, pending, AuditEntry.DELETE, changes, s)


def _on_m2m(sender, instance, action, **kwargs):
    if action.startswith("post_") and type(instance) in TRACKED:
        touch(instance)


def connect() -> None:
    _register()
    TYPE_LABELS.update({t.key: t.label for t in TRACKED.values()})
    for model in TRACKED:
        pre_save.connect(_on_pre_save, sender=model, dispatch_uid=f"audit-pre-{model.__name__}")
        post_save.connect(_on_post_save, sender=model, dispatch_uid=f"audit-{model.__name__}")
        pre_delete.connect(_on_pre_delete, sender=model, dispatch_uid=f"audit-pd-{model.__name__}")
        post_delete.connect(
            _on_post_delete, sender=model, dispatch_uid=f"audit-del-{model.__name__}"
        )
        for m2m in model._meta.many_to_many:
            m2m_changed.connect(
                _on_m2m, sender=m2m.remote_field.through, dispatch_uid=f"audit-m2m-{m2m}"
            )
