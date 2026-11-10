# 0019. Credit terms are a master, split into parts

Date: 9 Nov 2026. Asked by Sidharth: "credit terms should be a master as sometimes we have terms like 50% advance and 50% on delivery".

## Decision

Each company keeps a list of credit terms (superseded by 0020: one list for the group) (`core.CreditTerm`). A term is split into parts (`core.CreditTermPart`), each a share of the bill (percent) falling due at an event plus some days:

| Event | Meaning |
|---|---|
| order | With the order (advance) |
| dispatch | Before dispatch |
| delivery | On delivery |
| bill | After the bill date |

The shares add up to 100%. "30 days" is one part, 100% bill + 30 days; "50% advance, 50% on delivery" is two parts.

- A party (decision 0018) picks one term from its own company's list; this replaces the earlier credit days field. Migration 0013 turns any credit days already entered into the matching "N days" term.
- Every company starts with standard terms (full advance, 50/50 advance and delivery, 50/50 advance and dispatch, on delivery, 15/30/45/60 days); new ones can be added.
- Terms are never deleted, only made inactive; inactive terms are not offered to new parties but stay on those that have them.
- Terms are per company, like ledgers, so each company's list and Activity stay its own.
- Changes are in the audit log as "Credit terms" records, parts included.

## Later

- Sales and purchase orders and invoices copy the party's term (changeable per document) and split the bill into due dates; advances due "with the order" feed the advance request and the receivables ageing.
- Overdue checks and credit limit holds (rule 15) use these due dates.
