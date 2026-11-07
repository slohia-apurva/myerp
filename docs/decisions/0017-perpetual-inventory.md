# 0017. Perpetual inventory: cost of goods sold posted with each movement

Date: 7 Nov 2026. Confirmed by Sidharth ("perpetual is what we want"). To be walked through with the CA before Phase 2 (Accounts) posting rules are built.

## Decision

Stock is accounted for perpetually. Every stock movement posts to the GL as it happens, at FIFO cost (rule 8), so stock in the books and gross profit are right on any day, and no closing stock journal is passed.

| Movement | GL entry |
|---|---|
| Goods receipt (GRN) | Dr Stock (inventory ledger of the warehouse/item group), Cr Stock Received But Not Billed (rule 11) |
| Purchase invoice | Dr Stock Received But Not Billed, Dr input GST, Cr supplier. Difference from GRN value → purchase price variance, or revalues stock still on hand |
| Landed cost voucher | Dr Stock (added to lot rates), Cr freight / clearing / duty ledgers |
| Delivery note / sales issue | Dr Cost of goods sold, Cr Stock, at FIFO cost of the lots issued |
| Sales invoice | Dr customer, Cr sales, Cr output GST (revenue only; cost already posted by the delivery) |
| Sales return | Dr Stock, Cr Cost of goods sold, at the cost the goods left at |
| Issue to production / job work | Dr Work in progress (or Cost of materials consumed), Cr Stock (raw and packing materials) |
| Production receipt | Dr Stock (finished goods), Cr Work in progress, at the rolled-up cost |
| Stock count difference, scrap, expiry write-off | Dr Stock adjustment / loss ledger, Cr Stock (or the reverse for a surplus) |
| Transfer between warehouses of one GSTIN | No GL change unless the warehouses use different stock ledgers (rule 13 covers inter-GSTIN moves) |

## Reporting

The profit and loss is still shown in the Schedule III form (decision 0015): Revenue; Cost of materials consumed; Purchases of stock-in-trade; Changes in inventories of finished goods, work in progress and stock-in-trade. Those lines are derived from the stock ledger and the GL (opening stock, receipts, closing stock by category), not from separate periodic entries.

## Why not periodic

Periodic (purchases to a Purchase account, closing stock entered at period end) is simpler, but stock and margin in the books are only right on closing days, and it cannot give batch-wise or item-wise margin without a separate costing run.

## Consequences

- Backdated stock entries re-cost the later issues of that item and re-post their COGS (rule 8's background repost); periods that are locked (rule 7) block this until reopened.
- Each item group (or warehouse) maps to a stock ledger, a COGS ledger and, for production, a WIP ledger; these defaults are part of the Phase 3 masters.
- Opening stock at go-live is entered as stock with lots and rates, and its total must equal the opening balances of the stock ledgers.
