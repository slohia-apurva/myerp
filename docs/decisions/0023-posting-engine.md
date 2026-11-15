# 0023. The posting engine: one service writes the GL and the stock ledger

Date: 15 Nov 2026. Built before the goods receipt, which is its first user (Sidharth approved the order: batches, posting engine, goods receipt, attachments).

## Decision

All postings go through `backend/posting/service.py` (design rule 10). A document calls `post(voucher, stock=[...], gl=...)` on Submit and `cancel(voucher_type, id)` on Cancel. Nothing else writes ledger rows.

| Table | What a row is |
|---|---|
| GL entry | One debit or credit, in rupees, to one ledger, with company, branch, date and the voucher (type, id, number) |
| Stock move | One item in (+qty) or out (-qty) of a bin or area, with batch, rate and signed value |
| Stock lot | A FIFO lot: what a valued receipt brought into a branch and how much is left (working state, not a ledger) |

## Rules it enforces

- **Open month**: the date must be in a fiscal year and its month not locked (rule 7).
- **Balance**: debits equal credits per voucher. The service checks it, and the database checks it again when the transaction commits (a deferred trigger), so no voucher can be saved out of balance by any route.
- **Immutable**: the database refuses any update or delete of GL entries and stock moves. A cancel writes the exact reverse rows on the original date. Only the Owner's data reset (test data) may delete, and only inside its own transaction.
- **Stock**: quantity never goes below zero at a place and batch. A batch-tracked item must name a batch of that item. Stock sits in a bin or an area, never on a rack.
- **FIFO per item and branch** (decision 0002): an issue uses the oldest lots dated on or before it; the last of a lot takes its exact remaining value, so no paisa is lost to rounding. Moving stock between bins of one branch does not change its cost.
- **Backdating**: until the background repost (rule 8) is built, a valued entry dated before a later issue of the same item and branch is refused, because it would change that issue's cost. Receipts dated after the last issue are fine.
- **Customer-owned goods**: posted with `valued=False`; quantity only, no lot, no GL.
- **Cancel**: refused if stock it brought in has since been issued or moved.

## Ledgers

- Stock and COGS/Expense ledgers come from the item's main item group, per company (Masters › Item groups). A posting that needs one that is not set is refused with a message naming the group.
- System ledgers are made for a company the first time a posting needs them, and are found by a fixed code, so they may be renamed but not disabled:

| Ledger | Group |
|---|---|
| Goods Received but Bills not Received | Other Current Liabilities |
| Bills Received but Goods not Received | Other Current Assets |
| Goods Delivered but Bills not Made | Other Current Assets |
| Bills Made but Goods not Delivered | Other Current Liabilities |
| Work in Progress | Stock-in-Hand |
| Stock with Job Workers | Stock-in-Hand |
| Purchase Price Difference | Direct Expenses |
| Stock Adjustment | Direct Expenses |
| Round Off | Other Expenses |

## Locks

A ledger with GL entries, and an item, batch, branch or warehouse place with stock moves, counts as in use (key fields lock). Once an item group's stock has been valued in a company, that company's Stock and COGS ledgers on the group stop changing.

## For the CA review

The ledger groups of the system ledgers above, and the refusal of backdated entries before a later issue, are the points to confirm.
