# 0005 Chart of accounts: Tally-style groups

- Status: decided, 3 Nov 2026 (Sidharth)
- Decision: every ledger sits under a group; groups nest to any depth; nature (asset, liability, income, expense) comes from the primary group. Seed Tally's 15 primary groups and 13 standard sub-groups. Customers and suppliers are ledgers under Sundry Debtors / Sundry Creditors (or a sub-group).

## How it is built (5 Nov 2026)

- Every new company gets the 28 standard groups and a Head office branch (`core.companies.create_company`).
- Standard groups carry a fixed code (e.g. `sundry_debtors`) that posting rules use, so names never matter to code. They cannot be renamed, moved or deleted.
- As in Tally, Capital Account is a liability-nature group; there is no separate equity nature.
- Groups people add must sit under another group and take its nature. Moving a group carries everything under it to the new nature. Once ledgers have postings, such moves will be refused.
- Sales, Purchase, Direct Incomes and Direct Expenses (and groups under them) are marked as trading-account groups, above gross profit.
