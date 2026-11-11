"""Creating a company and what every company starts with."""

from datetime import date

from audit import recorder
from core.ledger_groups import ensure_cash_ledger, ensure_head_office, seed_standard_groups
from core.models import Branch, Company, Ledger, LedgerGroup, fiscal_year_start
from tenancy.context import tenant_atomic


def create_company(**fields) -> Company:
    """A new company with its head office branch, standard ledger groups and
    a Cash ledger."""
    with tenant_atomic():
        fields.setdefault(
            "books_start",
            fiscal_year_start(date.today(), fields.get("fiscal_year_start_month", 4)),
        )
        company = Company(**fields)
        company.full_clean(exclude=["abbr"] if not company.abbr else None)
        company.save()
        # What every company starts with is MyERP's setup, not a change by
        # the person, so it stays out of the audit log.
        with recorder.paused():
            _starting_records(company)
    return company


def _starting_records(company: Company) -> None:
    ensure_head_office(Branch, company)
    # The head office starts with the company's address and contact.
    head = company.branches.get(is_head_office=True)
    for field in ("address", "pincode", "city", "phone", "email", "contact_person"):
        setattr(head, field, getattr(company, field))
    head.default_billing = head.default_ship_to = head.default_ship_from = True
    head.save()
    seed_standard_groups(LedgerGroup, company, Ledger)
    ensure_cash_ledger(Ledger, LedgerGroup, company)
    from core.credit_terms import seed_credit_terms
    from core.models import CreditTerm, CreditTermPart

    seed_credit_terms(CreditTerm, CreditTermPart)
    from core.models import Unit
    from core.units import seed_units

    seed_units(Unit)


def visible_companies(user):
    """Companies this person may work in: those ticked on their user, or all
    when none are ticked. Owners see every company."""
    companies = Company.objects.all()
    if user.is_owner:
        return companies
    ticked = user.companies.values_list("pk", flat=True)
    return companies.filter(pk__in=ticked) if ticked.exists() else companies
