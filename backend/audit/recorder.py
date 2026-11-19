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
    "terms_set": "Terms and conditions",
    "purchase_terms": "Purchase terms",
    "sales_terms": "Sales terms",
    "credentials_updated_at": "API credentials saved on",
    "abbr": "Short code",
    "gstin": "GSTIN",
    "pan": "PAN",
    "tan": "TAN",
    "cin": "CIN / LLPIN",
    "state_code": "State",
    "pincode": "PIN code",
    "city": "City",
    "fiscal_year_start_month": "Financial year starts in",
    "books_start": "Books beginning from",
    "multi_currency": "Foreign currencies",
    "is_active": "Active",
    "is_head_office": "Head office",
    "default_billing": "Default billing address",
    "default_ship_to": "Default ship to",
    "default_ship_from": "Default ship from",
    "no_stock": "No stock",
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
    "description": "Description",
    "gst_code": "GST unit code",
    "item_number": "Item number",
    "hsn": "HSN",
    "delivery_hsn": "Delivery HSN",
    "mrp": "MRP",
    "usp": "USP",
    "best_before_value": "Best before",
    "best_before_unit": "Best before in",
    "batch_no": "Batch No",
    "lead_time_days": "Lead time (days)",
    "safety_stock_qty": "Safety stock qty",
    "min_order_qty": "Minimum order qty",
    "max_stock_qty": "Max stock qty",
    "batch_tracked": "Batches tracked",
    "qc_required": "Quality check on receipt",
    "default_request_type": "Default material request type",
    "item_type": "Type",
    "maintain_stock": "Maintain stock",
    "allow_purchase": "Allow purchase",
    "allow_sales": "Allow sales",
    "whole_numbers": "Whole numbers only",
    "carrier_id": "Courier in MyERP's list",
    "account_code": "Account or customer code",
    "awb": "Tracking number (AWB)",
    "booked_on": "Booked on",
    "ship_to_city": "Ship to city",
    "ship_to_pincode": "Ship to PIN code",
    "weight_kg": "Weight (kg)",
    "cod_amount": "Amount to collect (₹)",
    "expected_on": "Expected delivery",
    "cancel_reason": "Reason cancelled",
    "supplier_ref": "Supplier's quote ref",
    "order_date": "Order date",
    "expected_date": "Expected delivery",
    "branch": "Deliver to",
    "terms": "Terms for the supplier",
    "agent": "Buying agent",
    "purchaser": "Buying agent (purchaser)",
    "mail_agent_user": "Mail the purchaser",
    "bill_to": "Bill to",
}

# Fields that are internal or change by themselves.
SKIP = {
    "id",
    "credentials",  # never logged: only the date they were saved shows
    "created_at",
    "base_currency",
    "code",
    "sequence",
    "is_standard",
    "password",
    "last_login",
    "date_joined",
    "google_sub",
    "print_image",  # an image: shows through the company's "Printed image" extra
    "print_image_type",
    "signature",  # an image: shows through the user's "Signature" extra
    "signature_type",
    "is_superuser",
    "party",  # a ledger's party shows through its party extras
    "salesman",  # likewise, by name
    # A shipment's tracking: its events are their own history.
    "status",
    "last_event_at",
    "last_place",
    "delivered_at",
    "received_by",
    "created_by",
    # A purchase order's totals follow from its items; its submit shows as the status.
    "interstate",
    "supplier_address",  # shown by its name, as an extra
    "import_details",  # shown in words, as an extra
    "taxable_total",
    "cgst_total",
    "sgst_total",
    "igst_total",
    "round_off",
    "submitted_at",
    "mail_to",  # shown by name as "Mail to"
    "whatsapp_to",  # shown by name as "WhatsApp to"
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
    # Labels for this model's fields where the shared LABELS do not suit.
    labels: dict[str, str] = field(default_factory=dict)


TRACKED: dict[type[models.Model], Tracked] = {}


def _register() -> None:
    from accounts.models import Role, User
    from buying.models import (
        DebitNote,
        GoodsReceipt,
        PurchaseInvoice,
        PurchaseOrder,
        PurchaseReturn,
        TdsAdjustment,
    )
    from core import india
    from core import modules as company_modules
    from core.models import (
        Batch,
        Branch,
        Brand,
        Certificate,
        Company,
        CreditTerm,
        FiscalYear,
        Item,
        ItemGroup,
        Ledger,
        LedgerGroup,
        NumberFormat,
        PartyContact,
        PriceList,
        SalesPerson,
        TermsSet,
        Unit,
        WarehouseLocation,
    )
    from core.parties import party_extras
    from insurance.models import InsurancePolicy
    from selling.models import PickList, SalesOrder
    from shipping.models import CourierAccount, Shipment

    def state(code):
        return india.STATES.get(code, code) if code else None

    def carrier_name(pk):
        from tenancy.models import Carrier

        return Carrier.objects.filter(pk=pk).values_list("name", flat=True).first() or pk

    def attachment_labels():
        from core import attachments

        return attachments.LABELS

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
                extras={
                    "print_image": (
                        "Printed image",
                        lambda c: (
                            f"Own image, {len(c.print_image) // 1024 + 1} KB"
                            if c.print_image
                            else "Standard"
                        ),
                    ),
                },
                formats={
                    "state_code": state,
                    "modules": lambda v: ", ".join(module_labels.get(c, c) for c in v) or None,
                    "fiscal_year_start_month": lambda m: datetime.date(2000, m, 1).strftime("%B"),
                    "attachments_required": lambda v: (
                        ", ".join(attachment_labels().get(c, c) for c in v) or None
                    ),
                },
            ),
            Branch: Tracked("branch", "Branch", by_company, formats={"state_code": state}),
            Certificate: Tracked("certificate", "Licence or certificate", by_company),
            LedgerGroup: Tracked("ledger_group", "Ledger group", by_company),
            NumberFormat: Tracked(
                "number_format",
                "Document series",
                by_company,
                extras={
                    "counters": (
                        "Last numbers",
                        lambda f: "; ".join(
                            f"{c.year.name}: {c.last}"
                            for c in f.counters.select_related("year").order_by("year__start_date")
                            if c.last
                        )
                        or None,
                    )
                },
            ),
            WarehouseLocation: Tracked(
                "warehouse_location",
                "Rack, bin or area",
                lambda r: r.branch.company_id,
            ),
            FiscalYear: Tracked(
                "fiscal_year",
                "Fiscal year",
                by_company,
                extras={
                    "periods": (
                        "Locked months",
                        lambda y: ", ".join(
                            f"{p.start_date:%b %Y}" for p in y.periods.filter(is_locked=True)
                        )
                        or "None",
                    )
                },
            ),
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
            PriceList: Tracked(
                "price_list",
                "Price list",
                lambda r: None,
                extras={"prices": ("Prices", lambda p: f"{p.lines.count()} lines")},
            ),
            TermsSet: Tracked(
                "terms",
                "Terms and conditions",
                lambda r: None,
                extras={
                    "default_for": (
                        "Default for",
                        lambda t: ", ".join(
                            c.name
                            for c in Company.objects.filter(
                                **{"purchase_terms" if t.kind == "purchase" else "sales_terms": t}
                            )
                        )
                        or None,
                    )
                },
            ),
            Unit: Tracked("unit", "Unit", lambda r: None),
            ItemGroup: Tracked("item_group", "Item group", lambda r: None),
            Batch: Tracked("batch", "Batch", lambda r: None),
            Brand: Tracked("brand", "Brand", lambda r: None),
            SalesPerson: Tracked("sales_person", "Person", lambda r: None),
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
                    ),
                    "gst_rates": (
                        "GST rates",
                        lambda i: "; ".join(map(str, i.gst_rates.all())) or None,
                    ),
                },
            ),
            User: Tracked(
                "user",
                "User",
                lambda r: None,
                extras={
                    "roles": ("Roles", lambda u: names(u.roles.all())),
                    "companies": ("Companies", lambda u: names(u.companies.all()) or "All"),
                    "signature": (
                        "Signature",
                        lambda u: (
                            f"Image, {len(u.signature) // 1024 + 1} KB" if u.signature else None
                        ),
                    ),
                },
            ),
            Role: Tracked("role", "Role", lambda r: None),
            CourierAccount: Tracked(
                "courier_account",
                "Transporter",
                by_company,
                formats={"carrier_id": carrier_name},
            ),
            InsurancePolicy: Tracked(
                "insurance_policy",
                "Insurance policy",
                by_company,
                labels={
                    "number": "Policy number",
                    "kind": "Type of insurance",
                    "sum_insured": "Starting sum insured",
                    "transit_limit": "Limit per transit",
                    "insured_basis": "Insured value",
                    "alert_below": "Alert when balance falls below",
                    "when_out": "When cover runs out",
                    "declare_to": "Send declaration to",
                },
                extras={
                    "top_ups": (
                        "Top-ups",
                        lambda p: "; ".join(
                            f"{t.date:%d-%m-%Y} {t.endorsement_no or 'top-up'} ₹{t.amount:,.2f}"
                            for t in p.top_ups.all()
                        )
                        or None,
                    )
                },
            ),
            Shipment: Tracked(
                "shipment",
                "Shipment",
                by_company,
                extras={"customer": ("Customer", lambda s: s.party.name if s.party else None)},
                formats={"carrier_id": carrier_name},
            ),
            GoodsReceipt: Tracked(
                "goods_receipt",
                "Goods receipt",
                by_company,
                labels={
                    "branch": "Receiving warehouse",
                    "challan_no": "Supplier's challan / invoice no",
                    "challan_date": "Challan / invoice date",
                    "lr_no": "LR / docket no",
                    "eway_bill_no": "E-way bill no",
                    "qc_cartons": "Cartons (CFC) condition",
                    "qc_batch_print": "Batch code printed on packs",
                    "qc_by": "Quality checked by",
                },
                extras={
                    "receipt_status": ("Status", lambda r: r.get_status_display()),
                    "items": (
                        "Items",
                        lambda r: "; ".join(
                            f"{ln.item} {_number(ln.accepted_qty)} {ln.unit.short_name}"
                            for ln in r.lines.select_related("item", "unit")
                        )
                        or None,
                    ),
                },
            ),
            PurchaseReturn: Tracked(
                "purchase_return",
                "Purchase return",
                by_company,
                labels={
                    "lr_no": "LR / docket no",
                    "eway_bill_no": "E-way bill no",
                    "branch": "Branch",
                },
                extras={
                    "return_status": ("Status", lambda r: r.get_status_display()),
                    "items": (
                        "Items",
                        lambda r: "; ".join(
                            f"{ln.item} {_number(ln.qty)} {ln.unit.short_name}"
                            for ln in r.lines.select_related("item", "unit")
                        )
                        or None,
                    ),
                },
            ),
            DebitNote: Tracked(
                "debit_note",
                "Debit note",
                by_company,
                labels={
                    "supplier_note_no": "Supplier's credit note no",
                    "supplier_note_date": "Supplier's credit note date",
                    "branch": "Branch",
                },
                extras={
                    "note_status": ("Status", lambda n: n.get_status_display()),
                    "items": (
                        "Items",
                        lambda n: "; ".join(
                            f"{ln.item} {_number(ln.qty)} @ {_number(ln.rate)}"
                            for ln in n.lines.select_related("item")
                        )
                        or None,
                    ),
                },
            ),
            TdsAdjustment: Tracked(
                "tds_adjustment",
                "TDS adjustment",
                by_company,
                labels={"adj_date": "Date", "branch": "Branch", "total": "TDS adjusted"},
                extras={
                    "adjustment_status": ("Status", lambda a: a.get_status_display()),
                    "bills": (
                        "Bills",
                        lambda a: "; ".join(
                            f"{ln.invoice.number} {_number(ln.amount)}"
                            for ln in a.lines.select_related("invoice")
                        )
                        or None,
                    ),
                },
            ),
            PurchaseInvoice: Tracked(
                "purchase_invoice",
                "Purchase invoice",
                by_company,
                labels={
                    "bill_no": "Supplier invoice no",
                    "bill_date": "Supplier invoice date",
                    "bill_total": "Supplier's bill total",
                },
                extras={
                    "invoice_status": ("Status", lambda i: i.get_status_display()),
                    "items": (
                        "Items",
                        lambda i: "; ".join(
                            f"{ln.item} {_number(ln.qty)} @ {_number(ln.rate)}"
                            for ln in i.lines.select_related("item")
                        )
                        or None,
                    ),
                },
            ),
            SalesOrder: Tracked(
                "sales_order",
                "Sales order",
                by_company,
                labels={"branch": "Despatch from", "area": "Despatch area"},
                extras={
                    "order_status": ("Status", lambda o: o.get_status_display()),
                    "bill_address_label": (
                        "Billing address",
                        lambda o: (o.bill_address or {}).get("label") or None,
                    ),
                    "ship_address_label": (
                        "Ship to",
                        lambda o: (o.ship_address or {}).get("label") or None,
                    ),
                    "charges": (
                        "Charges",
                        lambda o: "; ".join(
                            f"{c.item} {c.amount}"
                            + (f" + GST {_number(c.gst_rate)}%" if c.gst_rate else "")
                            for c in o.charges.select_related("item")
                        )
                        or None,
                    ),
                    "mail_contacts": (
                        "Mail to",
                        lambda o: ", ".join(
                            f"{c.name} <{c.email}>"
                            for c in PartyContact.objects.filter(pk__in=o.mail_to)
                        )
                        or None,
                    ),
                    "items": (
                        "Items",
                        lambda o: "; ".join(
                            f"{ln.item} {_number(ln.qty)} {ln.unit.short_name}"
                            f" at {_number(ln.rate)}"
                            for ln in o.lines.select_related("item", "unit")
                        )
                        or None,
                    ),
                },
            ),
            PickList: Tracked(
                "pick_list",
                "Pick list",
                by_company,
                extras={
                    "pick_status": ("Status", lambda p: p.get_status_display()),
                    "rows": (
                        "Picked from",
                        lambda p: "; ".join(
                            f"{r.item} {_number(r.qty)} from {r.location}"
                            + (f" batch {r.batch}" if r.batch_id else "")
                            for r in p.lines.select_related("item", "location", "batch")
                        )
                        or None,
                    ),
                },
            ),
            PurchaseOrder: Tracked(
                "purchase_order",
                "Purchase order",
                by_company,
                extras={
                    # "status" itself is skipped (a shipment's comes from tracking).
                    "order_status": ("Status", lambda o: o.get_status_display()),
                    "import_terms": ("Import details", _import_words),
                    "charges": (
                        "Charges",
                        lambda o: "; ".join(
                            f"{c.item} {c.amount}"
                            + (f" + GST {_number(c.gst_rate)}%" if c.gst_rate else "")
                            + {
                                "no": " (not in stock cost)",
                                "qty": " (stock cost by quantity)",
                                "value": " (stock cost by value)",
                            }.get(c.add_to_stock, "")
                            for c in o.charges.select_related("item")
                        )
                        or None,
                    ),
                    "supplier_address_label": (
                        "Supplier address",
                        lambda o: (o.supplier_address or {}).get("label") or None,
                    ),
                    "mail_contacts": (
                        "Mail to",
                        lambda o: ", ".join(
                            f"{c.name} <{c.email}>"
                            for c in PartyContact.objects.filter(pk__in=o.mail_to)
                        )
                        or None,
                    ),
                    "whatsapp_contacts": (
                        "WhatsApp to",
                        lambda o: ", ".join(
                            f"{c.name} ({c.phone})"
                            for c in PartyContact.objects.filter(pk__in=o.whatsapp_to)
                        )
                        or None,
                    ),
                    "items": (
                        "Items",
                        lambda o: "; ".join(
                            f"{ln.item} {_number(ln.qty)} {ln.unit.short_name}"
                            f" at {_number(ln.rate)}"
                            + (f" less {_number(ln.discount_pct)}%" if ln.discount_pct else "")
                            for ln in o.lines.select_related("item", "unit")
                        )
                        or None,
                    ),
                },
            ),
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
        plain = str(f.verbose_name)[:1].upper() + str(f.verbose_name)[1:]
        label = spec.labels.get(f.name) or LABELS.get(f.name) or plain
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


def _import_words(o) -> str | None:
    from buying.imports import labelled

    d = labelled(o.import_details or {})
    parts = [
        " ".join(x for x in (d.get("incoterm"), d.get("named_place")) if x),
        d.get("mode_label", ""),
        " to ".join(x for x in (d.get("port_loading"), d.get("port_discharge")) if x),
        d.get("payment_label", ""),
        ", ".join(d.get("documents_labels") or []),
    ]
    return "; ".join(p for p in parts if p) or None


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
