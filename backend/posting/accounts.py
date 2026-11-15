"""Which ledgers postings go to.

System ledgers are the fixed clearing and adjustment accounts the posting
rules need (decision 0017, rule 11). Each company gets them the first time a
posting needs one, under its standard group, and they are found again by
`Ledger.system_code`, so people may rename them. They cannot be disabled.
"""

from rest_framework.exceptions import ValidationError

from core.models import Company, Item, ItemGroupAccount, Ledger, LedgerGroup

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
}


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
