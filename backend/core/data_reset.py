"""The Owner's "Reset data" tool: clear a company (or the whole group) back
to a clean start, in three levels.

* entries  - vouchers, stock entries and the like. Masters and opening
  balances stay. (Nothing posts entries yet; each entry module registers
  itself here with `register_entries` as it is built.)
* masters  - entries plus what people added to ONE company: ledgers (with
  their opening balances), their own ledger groups, branches other than the
  head office, licences and certificates, and customers or suppliers no other
  company uses. MyERP's own starting records (standard groups, head office,
  Cash) are kept or put back.
* all      - the whole group back to blank: every company as above, plus the
  shared items, the credit terms and units people added, and the running
  numbers. Companies, users and roles stay so the Owner can still sign in.

Safeguards: Owner only; refused unless settings.ALLOW_DATA_RESET is on (never
for live books); the Owner types the company name (or RESET ALL DATA) to
confirm; a backup file of everything removed is returned and must be saved by
the browser; and the reset is written to the company's Activity.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime

from django.conf import settings
from django.core import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from core.api import Signed
from core.credit_terms import STANDARD_TERMS
from core.ledger_groups import ensure_cash_ledger
from core.models import (
    Branch,
    Brand,
    Certificate,
    Company,
    CreditTerm,
    Item,
    ItemGroup,
    Ledger,
    LedgerGroup,
    LedgerOpeningBill,
    NumberSeries,
    Party,
    PartyAddress,
    PartyContact,
    PartyDocument,
    PartyDocumentFile,
    PartyItemName,
    PartyProduct,
    PriceList,
    SalesPerson,
    TermsSet,
    Unit,
    WarehouseLocation,
)
from core.units import STANDARD_UNITS
from tenancy.context import tenant_atomic

LEVELS = {
    "entries": "Entries only",
    "masters": "Entries and the masters added to this company",
    "all": "Whole group back to blank",
}
ALL_PHRASE = "RESET ALL DATA"

# Entry modules register here: (label, count(company), delete(company)).
# `company` is None when the whole group is being cleared.
_ENTRIES: list[tuple[str, Callable, Callable]] = []


def register_entries(label: str, count: Callable, delete: Callable) -> None:
    _ENTRIES.append((label, count, delete))


def _scope_ledgers(company):
    return Ledger.objects.filter(company=company) if company else Ledger.objects.all()


def _own_groups(company):
    groups = LedgerGroup.objects.filter(is_standard=False)
    return groups.filter(company=company) if company else groups


def _own_branches(company):
    branches = Branch.objects.filter(is_head_office=False)
    return branches.filter(company=company) if company else branches


def _locations(company):
    """Racks, bins and areas to clear. The head office keeps its default store."""
    rows = WarehouseLocation.objects.exclude(is_default=True, branch__is_head_office=True)
    return rows.filter(branch__company=company) if company else rows


def _certificates(company):
    return Certificate.objects.filter(company=company) if company else Certificate.objects.all()


def _orphan_parties(company):
    """Parties that no ledger outside the cleared scope still uses."""
    inside = _scope_ledgers(company).values("pk")
    return Party.objects.exclude(ledgers__in=Ledger.objects.exclude(pk__in=inside))


def _custom_terms():
    return CreditTerm.objects.exclude(name__in=[n for n, _ in STANDARD_TERMS])


def _custom_units():
    return Unit.objects.exclude(name__in=[u[0] for u in STANDARD_UNITS])


def _plan(level: str, company):
    """(label, queryset or None) for every kind of record the level removes,
    in the order they are deleted."""
    rows: list[tuple[str, object]] = []
    if level in ("masters", "all"):
        rows += [
            ("Opening bills", LedgerOpeningBill.objects.filter(ledger__in=_scope_ledgers(company))),
            ("Ledgers", _scope_ledgers(company)),
            ("Customers and suppliers", _orphan_parties(company)),
            ("Ledger groups you added", _own_groups(company)),
            ("Licences and certificates", _certificates(company)),
            ("Racks, bins and areas", _locations(company)),
            ("Branches other than the head office", _own_branches(company)),
        ]
    if level == "all":
        rows += [
            ("Items", Item.objects.all()),
            ("Item groups", ItemGroup.objects.all()),
            ("Brands", Brand.objects.all()),
            ("Salesmen and purchasers", SalesPerson.objects.all()),
            ("Price lists", PriceList.objects.all()),
            ("Terms and conditions", TermsSet.objects.all()),
            ("Credit terms you added", _custom_terms()),
            ("Units you added", _custom_units()),
        ]
    return rows


def preview(level: str, company) -> list[dict]:
    """What the level would remove, as [{"label", "count"}]."""
    scope = None if level == "all" else company
    out = [{"label": label, "count": count(scope)} for label, count, _ in _ENTRIES]
    out += [{"label": label, "count": qs.count()} for label, qs in _plan(level, scope)]
    return out


def _backup(level: str, scope) -> str:
    objects = []
    for _, qs in _plan(level, scope):
        objects += list(qs)
    if level == "masters" or level == "all":
        parties = list(_orphan_parties(scope))
        objects += list(PartyAddress.objects.filter(party__in=parties))
        objects += list(PartyContact.objects.filter(party__in=parties))
        objects += list(PartyProduct.objects.filter(party__in=parties))
        objects += list(PartyItemName.objects.filter(party__in=parties))
        objects += list(PartyDocument.objects.filter(party__in=parties))
        objects += list(PartyDocumentFile.objects.filter(document__party__in=parties))
    if level == "all":
        objects += list(NumberSeries.objects.all())
    return serializers.serialize("json", objects)


def run(level: str, company, user) -> dict:
    """Clear the level. Runs inside the caller's tenant_atomic; returns the
    counts removed and the backup as text."""
    from audit import recorder

    scope = None if level == "all" else company
    counts = preview(level, company)
    backup = _backup(level, scope)
    companies = list(Company.objects.all()) if level == "all" else [company]
    with recorder.paused():
        for _, _, delete in _ENTRIES:
            delete(scope)
        if level in ("masters", "all"):
            _delete_masters(scope)
        if level == "all":
            Item.objects.all().delete()
            Brand.objects.all().delete()
            SalesPerson.objects.all().delete()
            # Deepest groups first: a group cannot go while one sits under it.
            while (tips := ItemGroup.objects.filter(children__isnull=True)).exists():
                tips.delete()
            _custom_terms().delete()
            _custom_units().delete()
            NumberSeries.objects.update(last=0)
        for c in companies:
            ensure_cash_ledger(Ledger, LedgerGroup, c)
    removed = (
        ", ".join(f"{r['count']} {r['label'].lower()}" for r in counts if r["count"]) or "nothing"
    )
    for c in companies:
        AuditEntry.objects.create(
            user=user,
            user_name=user.full_name or user.email,
            company=c,
            record_type="company",
            record_id=c.pk,
            record_name=c.name,
            action=AuditEntry.UPDATE,
            changes=[
                {
                    "field": "data_reset",
                    "label": "Data reset",
                    "old": None,
                    "new": f"{LEVELS[level]}: removed {removed}. A backup file was saved.",
                }
            ],
        )
    return {"removed": counts, "backup": backup}


def _delete_masters(scope) -> None:
    parties = list(_orphan_parties(scope).values_list("pk", flat=True))
    LedgerOpeningBill.objects.filter(ledger__in=_scope_ledgers(scope)).delete()
    _scope_ledgers(scope).delete()
    Party.objects.filter(pk__in=parties).delete()
    _certificates(scope).delete()
    # Bins before the racks they stand on.
    _locations(scope).filter(kind="bin").delete()
    _locations(scope).delete()
    _own_branches(scope).delete()
    # Deepest groups first: a group cannot go while one sits under it.
    while (groups := _own_groups(scope).filter(children__isnull=True)).exists():
        groups.delete()


class DataResetView(APIView):
    """GET: whether the tool is on, the companies, and (with ?level=&company=)
    what a level would remove. POST {level, company, confirm}: do it."""

    permission_classes = [Signed]

    def _owner(self, request):
        if not request.user.is_owner:
            raise PermissionDenied("Only an Owner can reset data.")

    def _target(self, request, data):
        level = data.get("level")
        if level not in LEVELS:
            raise ValidationError({"level": ["Choose what to clear."]})
        company = None
        if level != "all":
            company = Company.objects.filter(pk=data.get("company")).first()
            if company is None:
                raise ValidationError({"company": ["Choose a company."]})
        return level, company

    def get(self, request):
        self._owner(request)
        out = {
            "allowed": settings.ALLOW_DATA_RESET,
            "levels": [{"value": k, "label": v} for k, v in LEVELS.items()],
            "companies": [{"id": c.pk, "name": c.name} for c in Company.objects.order_by("name")],
            "all_phrase": ALL_PHRASE,
        }
        if request.query_params.get("level"):
            level, company = self._target(request, request.query_params)
            out["preview"] = preview(level, company)
        return Response(out)

    @tenant_atomic()
    def post(self, request):
        self._owner(request)
        if not settings.ALLOW_DATA_RESET:
            raise PermissionDenied(
                "Resetting data is switched off here. It is for staging and trial runs, "
                "not live books."
            )
        level, company = self._target(request, request.data)
        want = company.name if company else ALL_PHRASE
        if (request.data.get("confirm") or "").strip() != want:
            raise ValidationError({"confirm": [f"Type {want} exactly to confirm."]})
        done = run(level, company, request.user)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        scope = "all" if level == "all" else f"company-{company.pk}"
        return Response(
            {
                "removed": done["removed"],
                "filename": f"myerp-backup-{scope}-{level}-{stamp}.json",
                "backup": json.loads(done["backup"]),
            }
        )
