# 0020. Customers, suppliers and credit terms are shared by the group

Date: 9 Nov 2026. Chosen by Sidharth ("Shared masters, ledgers per company") when he asked for ledgers, credit terms, items, suppliers and customers to be shared between all companies of a group.

## Decision

- **Credit terms** are one list per tenant (group of companies), not per company. Migration 0014 merges the per-company copies by name.
- **Customers and suppliers** (`core.Party`) are one record per group, holding GST details, addresses, contacts and credit terms. Party names are unique in the group.
- Each company that deals with a party has its **own ledger** for it under Sundry Debtors or Sundry Creditors (`Ledger.party`, at most one per company). The ledger holds what belongs to that company's books: balance, opening bills, the **credit limit** and the **salesman** (customers) or **purchaser** (suppliers), each company having its own (`Ledger.credit_limit`, `Ledger.salesman`; Sidharth, same day: "each company can have different salespeople or purchaser").
- On the ledger form, a new party ledger can pick an existing party ("Existing customer or supplier", API `party_id`), and ticks under "Companies that deal with this party" add the party's ledger to more companies on Save (API `also_in`), under the same standard group.
- Migration 0014 gives every party ledger a group party: parties with the same GSTIN, or else the same name, become one, keeping the first one's details (including credit terms) and adding the others' addresses and contacts; each company keeps its own credit limit and salesman. 0015 drops the old columns (split because Postgres cannot alter a table in the same transaction as moving its rows).
- **Items** will be one shared catalogue when built (already the plan).
- **Other ledgers** (expenses, income, bank, capital) stay per company: their balances are each company's books and bank accounts differ. An "Also add to" tick to create the same ledger in other companies is to follow.

## Audit

Party changes are logged on the ledger that was saved (its company's Activity). Credit terms are logged without a company and shown on the Credit terms page.

## Later

- A group-wide "Customers and suppliers" list under Masters.
- "Also add to" for non-party ledgers.
- Party changes shown in every linked company's ledger Activity.
