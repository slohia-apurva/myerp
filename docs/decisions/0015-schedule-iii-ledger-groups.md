# 0015. Standard ledger groups follow Schedule III

Date: 5 Nov 2026. Asked for by Sidharth; supersedes the group list in 0005 (the Tally-style tree, nesting and codes stay).

## Decision

The standard groups every company gets are laid out as the balance sheet and profit and loss heads of Schedule III (Division I) of the Companies Act, 2013, instead of Tally's 15 primary and 13 sub-groups. Each standard group stores its Schedule III head (`LedgerGroup.schedule_iii`), shown on the Ledger groups screen and used by the statements.

- Equity: Capital Account, Reserves & Surplus.
- Non-current liabilities: long-term borrowings (secured, unsecured), deferred tax liability, other long-term liabilities, long-term provisions.
- Current liabilities: short-term borrowings (Bank OD / Cash Credit), Sundry Creditors (trade payables), Duties & Taxes, other current liabilities, short-term provisions.
- Non-current assets: Fixed Assets (PPE), capital WIP, intangible assets, investments, deferred tax asset, long-term loans and advances (deposits), other non-current assets.
- Current assets: current investments, Stock-in-Hand (inventories), Sundry Debtors (trade receivables), cash, bank accounts, other bank balances, short-term loans and advances, other current assets.
- Profit and loss: Sales Accounts and Other Operating Revenue (revenue from operations), Other Income, Purchase Accounts (materials; stock-in-trade), Direct Expenses, Indirect Expenses (employee benefits, finance costs, depreciation, other expenses), Tax Expense.
- Branch / Divisions and Suspense stay as control groups; they are not shown in the statements.

Familiar names are kept for groups people post to (Sundry Debtors, Bank Accounts, Duties & Taxes), with the Schedule III wording beside them.

## Details

- Trade payables are split MSME / others in the statements from the supplier's Udyam registration, not by separate groups.
- Current maturities of long-term debt and the change in inventories are worked out by the statements, not posted to separate groups.
- Existing companies were converted by migration 0011 (`seed_standard_groups` re-lays groups by code). "Loans (Liability)" became Long-term Borrowings and "Misc. Expenses (ASSET)" became Other Non-current Assets; their sub-groups and ledgers moved with them.
- LLPs have no prescribed format; they use the same tree (Capital Account holds partners' contribution).
