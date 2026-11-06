import re

from django.db import migrations

from core.ledger_groups import ensure_head_office

# The group tree as it was when this migration was written (frozen: later
# migrations restructure it, e.g. 0011 for Schedule III).
# code, name, nature, affects gross profit. Balance sheet groups first.
PRIMARY_V1 = [
    ("capital_account", "Capital Account", "liability", False),
    ("loans_liability", "Loans (Liability)", "liability", False),
    ("current_liabilities", "Current Liabilities", "liability", False),
    ("fixed_assets", "Fixed Assets", "asset", False),
    ("investments", "Investments", "asset", False),
    ("current_assets", "Current Assets", "asset", False),
    ("branch_divisions", "Branch / Divisions", "liability", False),
    ("misc_expenses_asset", "Misc. Expenses (ASSET)", "asset", False),
    ("suspense", "Suspense A/c", "liability", False),
    ("sales_accounts", "Sales Accounts", "income", True),
    ("purchase_accounts", "Purchase Accounts", "expense", True),
    ("direct_incomes", "Direct Incomes", "income", True),
    ("direct_expenses", "Direct Expenses", "expense", True),
    ("indirect_incomes", "Indirect Incomes", "income", False),
    ("indirect_expenses", "Indirect Expenses", "expense", False),
]

# code, name, parent code
SUB_V1 = [
    ("reserves_surplus", "Reserves & Surplus", "capital_account"),
    ("bank_od", "Bank OD A/c", "loans_liability"),
    ("secured_loans", "Secured Loans", "loans_liability"),
    ("unsecured_loans", "Unsecured Loans", "loans_liability"),
    ("duties_taxes", "Duties & Taxes", "current_liabilities"),
    ("provisions", "Provisions", "current_liabilities"),
    ("sundry_creditors", "Sundry Creditors", "current_liabilities"),
    ("bank_accounts", "Bank Accounts", "current_assets"),
    ("cash_in_hand", "Cash-in-Hand", "current_assets"),
    ("deposits_asset", "Deposits (Asset)", "current_assets"),
    ("loans_advances_asset", "Loans & Advances (Asset)", "current_assets"),
    ("stock_in_hand", "Stock-in-Hand", "current_assets"),
    ("sundry_debtors", "Sundry Debtors", "current_assets"),
]


def seed_standard_groups_v1(LedgerGroup, company) -> None:
    """Add any standard group the company lacks. Takes the model so that
    migrations can pass their historical version."""
    existing = {g.code: g for g in LedgerGroup.objects.filter(company=company).exclude(code="")}
    for sequence, (code, name, nature, gross) in enumerate(PRIMARY_V1, start=1):
        if code not in existing:
            existing[code] = LedgerGroup.objects.create(
                company=company,
                code=code,
                name=name,
                nature=nature,
                affects_gross_profit=gross,
                is_standard=True,
                sequence=sequence,
            )
    for code, name, parent_code in SUB_V1:
        if code not in existing:
            parent = existing[parent_code]
            existing[code] = LedgerGroup.objects.create(
                company=company,
                code=code,
                name=name,
                parent=parent,
                nature=parent.nature,
                affects_gross_profit=parent.affects_gross_profit,
                is_standard=True,
            )




def fill_existing(apps, schema_editor):
    """Companies made before this change get a short code, a head office
    branch and the standard ledger groups, like new ones."""
    Company = apps.get_model("core", "Company")
    Branch = apps.get_model("core", "Branch")
    LedgerGroup = apps.get_model("core", "LedgerGroup")
    taken = set()
    for company in Company.objects.order_by("pk"):
        words = re.findall(r"[A-Za-z0-9]+", company.name)
        base = "".join(w[0] for w in words).upper()[:8]
        if len(base) < 2:
            base = (words[0][:3] if words else "CO").upper()
        abbr, n = base, 2
        while abbr in taken:
            abbr, n = f"{base}{n}", n + 1
        taken.add(abbr)
        company.abbr = abbr
        company.save(update_fields=["abbr"])
        ensure_head_office(Branch, company)
        seed_standard_groups_v1(LedgerGroup, company)


class Migration(migrations.Migration):
    dependencies = [("core", "0002_companies_branches_ledger_groups")]

    operations = [migrations.RunPython(fill_existing, migrations.RunPython.noop)]
