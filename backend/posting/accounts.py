"""Which ledgers postings go to.

System ledgers are the fixed clearing and adjustment accounts the posting
rules need (decision 0017, rule 11). They are found by `Ledger.system_code`
and cannot be disabled. Most are made the first time a posting needs one,
under their standard group, and people may rename them.

The six FIXED ones (goods and bills not yet matched, work in progress, stock
with job workers) are made with every company (Sidharth, 2026-11-17), keep
their names, and may be moved to another group at any time, even once in use,
so the CA can place them (the entries move with the ledger).
"""

from rest_framework.exceptions import APIException, ValidationError

from core.models import Company, Item, ItemAccount, ItemGroupAccount, Ledger, LedgerGroup

GRNI = "grni"
BILLS_NOT_RECEIVED_GOODS = "bills_received_goods_not_received"
GOODS_DELIVERED_NOT_BILLED = "goods_delivered_not_billed"
BILLED_NOT_DELIVERED = "billed_not_delivered"
WIP = "work_in_progress"
STOCK_WITH_JOB_WORKERS = "stock_with_job_workers"
PRICE_DIFFERENCE = "purchase_price_difference"
STOCK_ADJUSTMENT = "stock_adjustment"
ROUND_OFF = "round_off"
INPUT_CGST = "input_cgst"
INPUT_SGST = "input_sgst"
INPUT_IGST = "input_igst"
OUTPUT_CGST = "output_cgst"
OUTPUT_SGST = "output_sgst"
OUTPUT_IGST = "output_igst"

# code: (name, standard group code)
SYSTEM_LEDGERS = {
    GRNI: ("Goods Received but Bills not Received", "other_current_liabilities"),
    BILLS_NOT_RECEIVED_GOODS: ("Bills Received but Goods not Received", "other_current_assets"),
    GOODS_DELIVERED_NOT_BILLED: ("Goods Delivered but Bills not Made", "other_current_assets"),
    BILLED_NOT_DELIVERED: ("Bills Made but Goods not Delivered", "other_current_liabilities"),
    WIP: ("Work in Progress", "stock_in_hand"),
    STOCK_WITH_JOB_WORKERS: ("Stock with Job Workers", "stock_in_hand"),
    PRICE_DIFFERENCE: ("Purchase Price Difference", "direct_expenses"),
    STOCK_ADJUSTMENT: ("Stock Adjustment", "direct_expenses"),
    ROUND_OFF: ("Round Off", "other_expenses"),
    INPUT_CGST: ("Input CGST", "duties_taxes"),
    INPUT_SGST: ("Input SGST", "duties_taxes"),
    INPUT_IGST: ("Input IGST", "duties_taxes"),
    OUTPUT_CGST: ("Output CGST", "duties_taxes"),
    OUTPUT_SGST: ("Output SGST", "duties_taxes"),
    OUTPUT_IGST: ("Output IGST", "duties_taxes"),
}

# Made with every company; their names cannot change, their group can.
FIXED = (
    GRNI,
    BILLS_NOT_RECEIVED_GOODS,
    GOODS_DELIVERED_NOT_BILLED,
    BILLED_NOT_DELIVERED,
    WIP,
    STOCK_WITH_JOB_WORKERS,
)


def is_fixed(ledger: Ledger) -> bool:
    return ledger.system_code in FIXED


def ensure_fixed_ledgers(company: Company) -> None:
    """Give the company its six fixed system ledgers (those it lacks)."""
    for code in FIXED:
        system_ledger(company, code)


def system_ledger(company: Company, code: str) -> Ledger:
    """The company's ledger for this posting role, made if it is missing. A
    ledger someone already made with the same name is taken over."""
    ledger = Ledger.objects.filter(company=company, system_code=code).first()
    if ledger is not None:
        return ledger
    name, group_code = SYSTEM_LEDGERS[code]
    ledger = Ledger.objects.filter(company=company, name__iexact=name).first()
    if ledger is None:
        group = LedgerGroup.objects.get(company=company, code=group_code)
        ledger = Ledger(company=company, group=group, name=name)
    ledger.system_code = code
    ledger.is_active = True
    ledger.save()
    return ledger


def main_group(item: Item):
    group = item.item_group
    while group is not None and group.parent_id is not None:
        group = group.parent
    return group


def _accounts(company: Company, item: Item) -> ItemGroupAccount | None:
    group = main_group(item)
    if group is None:
        return None
    return ItemGroupAccount.objects.filter(group=group, company=company).first()


def stock_ledger(company: Company, item: Item) -> Ledger:
    """The inventory ledger an item's stock value sits in, set per company on
    its main item group (Masters > Item groups)."""
    accounts = _accounts(company, item)
    if accounts is None or accounts.stock_ledger_id is None:
        group = main_group(item)
        raise ValidationError(
            {
                "detail": [
                    f'Set the "Stock Ledger" of item group {group} for {company} '
                    f"(Masters > Item groups) before {item.name} can be posted."
                ]
            }
        )
    return accounts.stock_ledger


def expense_ledger(company: Company, item: Item) -> Ledger:
    """Where a purchase bill without goods receipt books the item: its own
    "Expense Account" for the company (Masters > Items), else its main group's
    COGS/Expense ledger."""
    own = ItemAccount.objects.filter(item=item, company=company).select_related("expense_ledger")
    if row := own.first():
        return row.expense_ledger
    accounts = _accounts(company, item)
    if accounts is None or accounts.cogs_ledger_id is None:
        raise ValidationError(
            {
                "detail": [
                    f'Set the "Expense Account" of {item.name} for {company} (Masters > '
                    "Items), or the COGS/Expense Ledger of its item group."
                ]
            }
        )
    return accounts.cogs_ledger


def cogs_ledger(company: Company, item: Item) -> Ledger:
    """The cost of goods sold / expense ledger of the item's main group."""
    accounts = _accounts(company, item)
    if accounts is None or accounts.cogs_ledger_id is None:
        group = main_group(item)
        raise ValidationError(
            {
                "detail": [
                    f'Set the "COGS/Expense Ledger" of item group {group} for '
                    f"{company} (Masters > Item groups) before {item.name} can be posted."
                ]
            }
        )
    return accounts.cogs_ledger


def sales_ledger(company: Company, item: Item) -> Ledger:
    """Where a sales invoice books the item: its main group's Sales Ledger."""
    accounts = _accounts(company, item)
    if accounts is None or accounts.sales_ledger_id is None:
        group = main_group(item)
        raise ValidationError(
            {
                "detail": [
                    f'Set the "Sales Ledger" of item group {group} for {company} '
                    f"(Masters > Item groups) before {item.name} can be billed."
                ]
            }
        )
    return accounts.sales_ledger


# The ledgers an item group sets per company (Masters > Item groups), as the
# screens name them.
STOCK, COGS, SALES = "stock", "cogs", "sales"
ACCOUNT_LABELS = {STOCK: "Stock Ledger", COGS: "COGS/Expense Ledger", SALES: "Sales Ledger"}


def missing_accounts(company: Company, lines, needs=(STOCK, COGS)) -> list[dict]:
    """Each main item group whose ledgers for this company are not all set, with
    the lines that need them. `lines` is (line number, item) pairs."""
    rows: dict[int, dict] = {}
    for n, item in lines:
        group = main_group(item)
        if group is None:
            continue
        accounts = _accounts(company, item)
        missing = [
            ACCOUNT_LABELS[k]
            for k in needs
            if accounts is None or getattr(accounts, f"{k}_ledger_id") is None
        ]
        if not missing:
            continue
        row = rows.setdefault(
            group.pk, {"group": group.pk, "group_name": group.name, "missing": missing, "lines": []}
        )
        row["lines"].append(f"Line {n} {item.name}")
    return list(rows.values())


def accounts_refusal(company: Company, user, lines, needs=(STOCK, COGS)) -> dict | None:
    """The refusal of a Submit whose items lack their group's ledgers: every one at
    once, so the screen can list them in a popup (Sidharth, 2026-11-17), and
    whether this person may set them (else the screen offers "Ask to set")."""
    rows = missing_accounts(company, lines, needs)
    if not rows:
        return None
    names = ", ".join(r["group_name"] for r in rows)
    return {
        "detail": f"Set the ledgers of item group {names} for {company} "
        "(Masters > Item groups) before Submit.",
        "missing_accounts": rows,
        "may_set": user.can("masters.edit"),
        "company": company.pk,
    }


class AccountsMissing(APIException):
    """Submit refused for missing item group ledgers; the body is the refusal as is."""

    status_code = 400
    default_code = "accounts_missing"

    def __init__(self, refusal: dict):
        super().__init__(refusal["detail"])
        self.detail = refusal


def require_accounts(company: Company, user, lines, needs=(STOCK, COGS)) -> None:
    if refusal := accounts_refusal(company, user, lines, needs):
        raise AccountsMissing(refusal)
