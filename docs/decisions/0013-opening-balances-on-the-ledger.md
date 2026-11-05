# 0013 Opening balances are entered on the ledger

- Status: decided, 5 Nov 2026 (Sidharth)
- Decision: as in Tally, a ledger's opening balance (amount and Dr/Cr) is entered on the ledger screen, as at the company's "books beginning from" date. A ledger can keep balances bill by bill (on by default under Sundry Debtors and Sundry Creditors); its opening balance is then the total of a grid of open bills (reference, bill date, due date, amount, Dr/Cr), each dated before the books begin.
- Why: this is how the team migrates from Tally/ERPNext today, and it keeps the outstanding bills that receipts and payments must be set against.
- How it fits rule 1 (ledgers are the source of truth): the opening balance is the ledger's first row. When the GL arrives, balances and reports start from these opening figures; the opening bills become the first entries of the bill-wise outstanding register. Once a period is locked, opening balances can no longer be changed.
- The company page shows total opening debits, credits and the difference, which must be cleared before go-live (Tally shows the same difference).
- Later: branch on opening balances (rule 19), opening stock from the inventory side.
