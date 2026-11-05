"""The standard chart-of-accounts groups every company starts with.

Tally-style tree (decision 0005) laid out as Schedule III of the Companies
Act, 2013 (decision 0015): every standard group sits under the balance sheet
or profit and loss head it is reported in, and carries that head's
Schedule III wording. Familiar names (Sundry Debtors, Bank Accounts) are
kept for the groups people post to. Posting rules find groups by code, so
people can add their own groups underneath without breaking anything.
"""

A, L, INC, E = "asset", "liability", "income", "expense"

# code, name, parent code (None = primary), nature, affects gross profit,
# Schedule III head. Listed in report order; parents before children.
TREE = [
    # Equity and liabilities
    (
        "capital_account",
        "Capital Account",
        None,
        L,
        False,
        "Equity: share capital / partners' capital",
    ),
    (
        "reserves_surplus",
        "Reserves & Surplus",
        "capital_account",
        L,
        False,
        "Equity: other equity (reserves and surplus)",
    ),
    (
        "non_current_liabilities",
        "Non-current Liabilities",
        None,
        L,
        False,
        "Non-current liabilities",
    ),
    (
        "long_term_borrowings",
        "Long-term Borrowings",
        "non_current_liabilities",
        L,
        False,
        "Non-current liabilities: borrowings",
    ),
    ("secured_loans", "Secured Loans", "long_term_borrowings", L, False, "Borrowings: secured"),
    (
        "unsecured_loans",
        "Unsecured Loans",
        "long_term_borrowings",
        L,
        False,
        "Borrowings: unsecured",
    ),
    (
        "deferred_tax_liability",
        "Deferred Tax Liability",
        "non_current_liabilities",
        L,
        False,
        "Non-current liabilities: deferred tax liabilities (net)",
    ),
    (
        "other_long_term_liabilities",
        "Other Long-term Liabilities",
        "non_current_liabilities",
        L,
        False,
        "Non-current liabilities: other long-term liabilities",
    ),
    (
        "long_term_provisions",
        "Long-term Provisions",
        "non_current_liabilities",
        L,
        False,
        "Non-current liabilities: long-term provisions",
    ),
    ("current_liabilities", "Current Liabilities", None, L, False, "Current liabilities"),
    (
        "short_term_borrowings",
        "Short-term Borrowings",
        "current_liabilities",
        L,
        False,
        "Current liabilities: borrowings",
    ),
    (
        "bank_od",
        "Bank OD / Cash Credit",
        "short_term_borrowings",
        L,
        False,
        "Borrowings: loans repayable on demand from banks",
    ),
    (
        "sundry_creditors",
        "Sundry Creditors",
        "current_liabilities",
        L,
        False,
        "Current liabilities: trade payables (MSME and others, from the supplier's Udyam status)",
    ),
    (
        "duties_taxes",
        "Duties & Taxes",
        "current_liabilities",
        L,
        False,
        "Current liabilities: other current liabilities (statutory dues)",
    ),
    (
        "other_current_liabilities",
        "Other Current Liabilities",
        "current_liabilities",
        L,
        False,
        "Current liabilities: other current liabilities",
    ),
    (
        "provisions",
        "Short-term Provisions",
        "current_liabilities",
        L,
        False,
        "Current liabilities: short-term provisions",
    ),
    # Assets
    ("non_current_assets", "Non-current Assets", None, A, False, "Non-current assets"),
    (
        "fixed_assets",
        "Fixed Assets",
        "non_current_assets",
        A,
        False,
        "Property, plant and equipment",
    ),
    (
        "capital_wip",
        "Capital Work-in-Progress",
        "non_current_assets",
        A,
        False,
        "Capital work-in-progress",
    ),
    (
        "intangible_assets",
        "Intangible Assets",
        "non_current_assets",
        A,
        False,
        "Intangible assets (and those under development)",
    ),
    ("investments", "Investments", "non_current_assets", A, False, "Non-current investments"),
    (
        "deferred_tax_asset",
        "Deferred Tax Asset",
        "non_current_assets",
        A,
        False,
        "Deferred tax assets (net)",
    ),
    (
        "long_term_loans_advances",
        "Long-term Loans & Advances",
        "non_current_assets",
        A,
        False,
        "Long-term loans and advances",
    ),
    (
        "deposits_asset",
        "Deposits (Asset)",
        "long_term_loans_advances",
        A,
        False,
        "Long-term loans and advances: security deposits",
    ),
    (
        "other_non_current_assets",
        "Other Non-current Assets",
        "non_current_assets",
        A,
        False,
        "Other non-current assets",
    ),
    ("current_assets", "Current Assets", None, A, False, "Current assets"),
    (
        "current_investments",
        "Current Investments",
        "current_assets",
        A,
        False,
        "Current investments",
    ),
    ("stock_in_hand", "Stock-in-Hand", "current_assets", A, False, "Inventories"),
    ("sundry_debtors", "Sundry Debtors", "current_assets", A, False, "Trade receivables"),
    (
        "cash_in_hand",
        "Cash-in-Hand",
        "current_assets",
        A,
        False,
        "Cash and cash equivalents: cash on hand",
    ),
    (
        "bank_accounts",
        "Bank Accounts",
        "current_assets",
        A,
        False,
        "Cash and cash equivalents: balances with banks",
    ),
    (
        "other_bank_balances",
        "Other Bank Balances",
        "current_assets",
        A,
        False,
        "Bank balances other than cash and cash equivalents (FDs over 3 months, margin money)",
    ),
    (
        "loans_advances_asset",
        "Short-term Loans & Advances",
        "current_assets",
        A,
        False,
        "Short-term loans and advances",
    ),
    (
        "other_current_assets",
        "Other Current Assets",
        "current_assets",
        A,
        False,
        "Other current assets",
    ),
    # Control groups; their balances net to nil in the company's statements
    (
        "branch_divisions",
        "Branch / Divisions",
        None,
        L,
        False,
        "not shown (inter-branch balances net to nil)",
    ),
    ("suspense", "Suspense A/c", None, L, False, "not shown (cleared before closing the year)"),
    # Profit and loss
    (
        "sales_accounts",
        "Sales Accounts",
        None,
        INC,
        True,
        "Revenue from operations: sale of products and services",
    ),
    (
        "direct_incomes",
        "Other Operating Revenue",
        None,
        INC,
        True,
        "Revenue from operations: other operating revenue (scrap, export incentives)",
    ),
    ("indirect_incomes", "Other Income", None, INC, False, "Other income"),
    (
        "purchase_accounts",
        "Purchase Accounts",
        None,
        E,
        True,
        "Purchases (with change in inventories)",
    ),
    (
        "material_purchases",
        "Purchase of Materials",
        "purchase_accounts",
        E,
        True,
        "Cost of materials consumed",
    ),
    (
        "stock_in_trade_purchases",
        "Purchase of Stock-in-Trade",
        "purchase_accounts",
        E,
        True,
        "Purchases of stock-in-trade",
    ),
    (
        "direct_expenses",
        "Direct Expenses",
        None,
        E,
        True,
        "Other expenses: manufacturing (power, fuel, job work, freight inward)",
    ),
    ("indirect_expenses", "Indirect Expenses", None, E, False, "Expenses"),
    (
        "employee_benefits",
        "Employee Benefits Expense",
        "indirect_expenses",
        E,
        False,
        "Employee benefits expense",
    ),
    ("finance_costs", "Finance Costs", "indirect_expenses", E, False, "Finance costs"),
    (
        "depreciation",
        "Depreciation & Amortisation",
        "indirect_expenses",
        E,
        False,
        "Depreciation and amortisation expense",
    ),
    ("other_expenses", "Other Expenses", "indirect_expenses", E, False, "Other expenses"),
    ("tax_expense", "Tax Expense", None, E, False, "Tax expense: current and deferred tax"),
]

# Standard groups that no longer exist and where their contents go.
RETIRED = {
    "loans_liability": "long_term_borrowings",
    "misc_expenses_asset": "other_non_current_assets",
}


def seed_standard_groups(LedgerGroup, company, Ledger=None) -> None:
    """Bring the company's standard groups to the tree above: add missing
    ones, and rename, re-parent and re-label existing ones by code. A group
    someone added with the same name as a new standard group is adopted.
    Retired groups hand their sub-groups and ledgers on and are removed.
    Takes the models so that migrations can pass their historical versions."""
    groups = LedgerGroup.objects.filter(company=company)
    by_code = {g.code: g for g in groups.exclude(code="")}
    for sequence, (code, name, parent_code, nature, gross, head) in enumerate(TREE, start=1):
        group = by_code.get(code)
        if group is None:
            group = groups.filter(name__iexact=name, code="").first() or LedgerGroup(
                company=company
            )
        clash = groups.filter(name__iexact=name).exclude(pk=group.pk).first()
        if clash is not None:
            clash.name = f"{clash.name} (own)"
            clash.save(update_fields=["name"])
        group.code = code
        group.name = name
        group.parent = by_code[parent_code] if parent_code else None
        group.nature = nature
        group.affects_gross_profit = gross
        group.schedule_iii = head
        group.is_standard = True
        group.sequence = sequence
        group.save()
        by_code[code] = group
    for old, new in RETIRED.items():
        retired = by_code.get(old)
        if retired is None:
            continue
        target = by_code[new]
        LedgerGroup.objects.filter(parent=retired).update(parent=target)
        if Ledger is not None:
            Ledger.objects.filter(group=retired).update(group=target)
        retired.delete()


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


# code, name, symbol: currencies Indian exporters and importers use most.
CURRENCIES = [
    ("INR", "Indian Rupee", "₹"),
    ("USD", "US Dollar", "$"),
    ("EUR", "Euro", "€"),
    ("GBP", "Pound Sterling", "£"),
    ("AED", "UAE Dirham", "AED"),
    ("SAR", "Saudi Riyal", "SAR"),
    ("SGD", "Singapore Dollar", "S$"),
    ("AUD", "Australian Dollar", "A$"),
    ("CAD", "Canadian Dollar", "C$"),
    ("JPY", "Japanese Yen", "¥"),
    ("CNY", "Chinese Yuan", "CN¥"),
    ("CHF", "Swiss Franc", "CHF"),
    ("HKD", "Hong Kong Dollar", "HK$"),
    ("MYR", "Malaysian Ringgit", "RM"),
    ("THB", "Thai Baht", "฿"),
    ("BDT", "Bangladeshi Taka", "৳"),
    ("NPR", "Nepalese Rupee", "Rs"),
    ("LKR", "Sri Lankan Rupee", "Rs"),
    ("ZAR", "South African Rand", "R"),
    ("NZD", "New Zealand Dollar", "NZ$"),
]


def seed_currencies(Currency) -> None:
    for code, name, symbol in CURRENCIES:
        Currency.objects.get_or_create(code=code, defaults={"name": name, "symbol": symbol})
