# 0002 Stock valuation: FIFO per item-warehouse

- Status: decided, Nov 2026
- Decision: FIFO for all items. Each item-warehouse keeps a queue of incoming lots (qty, rate, date); issues consume the oldest lots; transfers carry lot rates; backdated entries trigger a background repost for that item.
