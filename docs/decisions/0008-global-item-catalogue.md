# 0008 Global item catalogue, searched live and copied on pick

- Status: decided as design, 4 Nov 2026 (scope questions open in the roadmap spec)
- Context: Sidharth wants a master database of items with a barcode-like code and fixed descriptions that any tenant can pull into its own item master.
- Decision:
  - The catalogue lives only in the platform database and is maintained by platform admins. Codes are GTINs where they exist, otherwise MyERP-issued codes with a check digit; codes are never reused.
  - Unlike small global masters, it is not synced in full into tenant databases. Tenants search it through a read-only API, and a picked item is copied into the tenant database with its catalogue code and version.
  - The catalogue fields of a linked item are read-only to the tenant (rule 17). Corrections are published as new versions and offered to tenants, who accept them. Posted documents never change.
  - Tenant items reach the catalogue only through an explicit suggestion that platform admins review.
- Details: `docs/specs/00-architecture-and-roadmap.md`, "Global item catalogue".
