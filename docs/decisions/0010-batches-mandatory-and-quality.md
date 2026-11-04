# 0010 Every stock item is batch-tracked; quality checklists are a module

- Status: decided, 4 Nov 2026 (Sidharth)
- Decision:
  - Batch tracking is mandatory for all stock items, not optional per item. Every stock ledger row carries a batch (rule 12). Items with no natural lot get one batch per receipt automatically.
  - Production records exact input batch to output batch links, so forward and backward traceability and mock recalls come straight from the stock ledger.
  - Quality and food safety (ISO 9001, FSSC 22000 / ISO 22000, HACCP, GMP) is a module, 5b. Checklist templates are global masters that tenants copy and adapt. Checklist runs are tied to GRNs, work orders, CCPs and dispatch, and block batch release when missing or failed. Out-of-limit readings raise non-conformances with CAPA. Submitted runs are immutable.
- Consequence: checklist runs and batch release need tablet and phone screens in v1.
