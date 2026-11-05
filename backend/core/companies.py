"""Creating a company and what every company starts with."""

from core.ledger_groups import ensure_cash_ledger, ensure_head_office, seed_standard_groups
from core.models import Branch, Company, Ledger, LedgerGroup
from tenancy.context import tenant_atomic


def create_company(**fields) -> Company:
    """A new company with its head office branch, standard ledger groups and
    a Cash ledger."""
    with tenant_atomic():
        company = Company(**fields)
        company.full_clean(exclude=["abbr"] if not company.abbr else None)
        company.save()
        ensure_head_office(Branch, company)
        seed_standard_groups(LedgerGroup, company)
        ensure_cash_ledger(Ledger, LedgerGroup, company)
    return company


def visible_companies(user):
    """Companies this person may work in: those ticked on their user, or all
    when none are ticked. Owners see every company."""
    companies = Company.objects.all()
    if user.is_owner:
        return companies
    ticked = user.companies.values_list("pk", flat=True)
    return companies.filter(pk__in=ticked) if ticked.exists() else companies
