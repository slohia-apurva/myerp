"""The standard chart-of-accounts groups every company starts with.

Tally's 15 primary groups and 13 sub-groups (decision 0005). Posting rules
find them by code, so people can add their own groups underneath without
breaking anything.
"""

# code, name, nature, affects gross profit. Balance sheet groups first.
PRIMARY = [
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
SUB = [
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


def seed_standard_groups(LedgerGroup, company) -> None:
    """Add any standard group the company lacks. Takes the model so that
    migrations can pass their historical version."""
    existing = {g.code: g for g in LedgerGroup.objects.filter(company=company).exclude(code="")}
    for sequence, (code, name, nature, gross) in enumerate(PRIMARY, start=1):
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
    for code, name, parent_code in SUB:
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


def ensure_head_office(Branch, company) -> None:
    if not Branch.objects.filter(company=company, is_head_office=True).exists():
        Branch.objects.create(
            company=company,
            name="Head office",
            state_code=company.state_code,
            gstin=company.gstin,
            is_head_office=True,
        )


def ensure_cash_ledger(Ledger, LedgerGroup, company) -> None:
    """Every company starts with a Cash ledger under Cash-in-Hand."""
    if not Ledger.objects.filter(company=company, name__iexact="Cash").exists():
        group = LedgerGroup.objects.get(company=company, code="cash_in_hand")
        Ledger.objects.create(company=company, group=group, name="Cash")
