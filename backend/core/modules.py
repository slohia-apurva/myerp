"""The modules a company can switch on (decision 0014).

A trading company has no use for Production; a service company may not
keep stock. The tenant's Owner ticks the modules each company uses; menus
and documents of the others stay hidden for that company. Later the
tenant's plan (SaaS) caps which modules can be ticked at all.
"""

# (code, label, what it covers, modules it needs)
MODULES = [
    ("accounts", "Accounts", "Ledgers, vouchers, bank, reports. Always on.", ()),
    ("gst", "GST", "E-invoice, e-way bill, GST returns data", ()),
    ("tds", "TDS / TCS", "Deduction, challans, returns data", ()),
    ("stock", "Stock", "Items, batches, warehouses, stock entries", ()),
    ("purchase", "Purchase", "POs, goods receipts, purchase invoices", ()),
    ("sales", "Sales", "Quotations, orders, deliveries, sales invoices", ()),
    ("production", "Production", "BOMs, work orders, job work", ("stock",)),
    ("quality", "Quality and food safety", "Checklists, batch release, CAPA", ("stock",)),
    ("imports_exports", "Imports and exports", "Import and export files, BOEs, shipping bills", ()),
    ("fixed_assets", "Fixed assets", "Asset register and depreciation", ()),
    ("loans", "Loans taken", "Lenders, repayment schedules, interest", ()),
    ("payroll", "Payroll", "Employees, salary, PF / ESI / PT", ()),
    ("expenses", "Staff expenses and advances", "Expense claims, petty cash, staff loans", ()),
    ("pos", "Point of sale", "Counter billing at shops", ("sales", "stock")),
]
CODES = [code for code, *_ in MODULES]
ALWAYS_ON = ("accounts",)
_LABELS = {code: label for code, label, *_ in MODULES}
_NEEDS = {code: needs for code, _label, _what, needs in MODULES}


def all_modules() -> list[str]:
    return list(CODES)


def check(codes: list[str]) -> list[str]:
    """Known codes in the standard order, with Accounts added. Raises
    ValueError naming what is wrong."""
    unknown = sorted(set(codes) - set(CODES))
    if unknown:
        raise ValueError(f"Unknown module: {', '.join(unknown)}.")
    chosen = set(codes) | set(ALWAYS_ON)
    for code in chosen:
        missing = [n for n in _NEEDS[code] if n not in chosen]
        if missing:
            needed = " and ".join(_LABELS[n] for n in missing)
            raise ValueError(f"{_LABELS[code]} needs {needed}.")
    return [code for code in CODES if code in chosen]
