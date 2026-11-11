"""No duplicate masters (Sidharth, 2026-11-11).

Two records of the same master must never mean the same thing. Names are
compared ignoring capitals and extra spaces ("Acme  Foods " is "ACME Foods"),
within the right scope: the whole group for shared masters (customers and
suppliers, items, item groups, brands, units, credit terms, roles), the company for its own
(ledgers, ledger groups, branches, courier accounts). Registration numbers
(GSTIN, PAN, bank account numbers, barcodes) are unique too.

Every check is made twice: by the database (a unique constraint on
Lower(name), so no path can slip past) and by the master's save function,
which refuses with a plain message naming the record already there. The
refusal also carries `existing` ({kind, id, name, company}) so the screen can
offer a link to open that record. Imports run the same save functions, so a
file can neither add a duplicate nor hold the same record twice.

Names are tidied (trimmed, runs of spaces made one) on every save by the
pre_save hook below, so the database constraint also covers spacing.
"""

from django.db.models import Model, QuerySet
from django.db.models.signals import pre_save
from rest_framework.exceptions import ValidationError


def tidy(text: str | None) -> str:
    """Trim and make every run of spaces one space."""
    return " ".join((text or "").split())


# Model label -> the name fields tidied on every save.
TIDY_FIELDS: dict[str, tuple[str, ...]] = {
    "core.Company": ("name",),
    "core.Branch": ("name",),
    "core.LedgerGroup": ("name",),
    "core.Ledger": ("name",),
    "core.Party": ("name",),
    "core.CreditTerm": ("name",),
    "core.Unit": ("name", "short_name"),
    "core.Item": ("name",),
    "core.ItemGroup": ("name",),
    "core.Brand": ("name",),
    "core.Certificate": ("name",),
    "shipping.CourierAccount": ("name",),
    "accounts.Role": ("name",),
}


def _tidy_names(sender, instance, **kwargs) -> None:
    for field in TIDY_FIELDS.get(sender._meta.label, ()):
        value = getattr(instance, field)
        if isinstance(value, str):
            setattr(instance, field, tidy(value))


def connect() -> None:
    pre_save.connect(_tidy_names, dispatch_uid="core.duplicates.tidy_names")


def existing(record: Model, kind: str, name: str | None = None, company=None) -> dict:
    """What the screen needs to link to the record that is already there."""
    found = {"kind": kind, "id": record.pk, "name": name if name is not None else str(record)}
    if company is None:
        company = getattr(record, "company_id", None)
    if company is not None:
        found["company"] = company
    return found


def refuse(field: str, message: str, record: Model, kind: str, **kwargs) -> None:
    raise ValidationError({field: [message], "existing": existing(record, kind, **kwargs)})


def same_name(qs: QuerySet, value: str, field: str = "name", exclude=None):
    """The record in `qs` whose `field` matches `value` (capitals and spaces
    ignored), leaving out the record being saved; None when there is none."""
    clash = qs.filter(**{f"{field}__iexact": tidy(value)})
    if exclude is not None:
        clash = clash.exclude(pk=exclude)
    return clash.first()


def check_name(
    qs: QuerySet,
    value: str,
    *,
    kind: str,
    message: str,
    field: str = "name",
    exclude=None,
) -> None:
    """Refuse `value` if a record in `qs` already has that name. `message`
    may use {name} for the existing record's name."""
    clash = same_name(qs, value, field, exclude)
    if clash is not None:
        refuse(field, message.format(name=getattr(clash, field)), clash, kind)
