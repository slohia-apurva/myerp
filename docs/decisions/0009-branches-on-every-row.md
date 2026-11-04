# 0009 Branch on every voucher and ledger row; POS as a later module

- Status: decided as design, 4 Nov 2026
- Context: Sidharth wants branch-wise accounts and POS billing later. Adding a branch column to ledger rows after go-live would mean rewriting posted history.
- Decision:
  - Branch master per company from Phase 1, with a default "Head office" branch so single-branch use is unchanged.
  - branch_id on every voucher header, GL row, stock ledger row and warehouse (design rule 19). Vouchers balance per branch; cross-branch vouchers post through a Branch/Divisions control account.
  - Per-branch naming series, price lists and user restrictions. Cost centre is a separate second dimension on GL rows.
  - POS billing is Phase 11: offline-capable counter screen, terminals with their own series, shifts with cash count, split payments, each bill a B2C sales invoice.
- Details: `docs/specs/00-architecture-and-roadmap.md`, "Branch accounts and POS billing" and rule 19.
