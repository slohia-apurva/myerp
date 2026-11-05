# 0012 Roles and permissions per tenant

- Status: decided, 5 Nov 2026
- Decision:
  - **Permission codes are code.** Each module declares its permissions in `accounts/permissions.py`, for example `sales.submit`. **Which role gets which permission is data** in the tenant database, so tenants change it on the Roles screen with no code (rule 18).
  - Eight standard roles come with every tenant: Owner, Accountant, Sales, Purchase, Storekeeper, Production supervisor, Quality and Viewer. Tenants can edit any of them except Owner, and can add their own roles.
  - **Owner** can always do everything. It is not stored as a list, so new modules' permissions apply automatically. Only an Owner can grant or remove Owner, change an Owner's access, or edit roles. A tenant must always keep at least one active Owner.
  - `users.manage` lets someone add people, change their roles and companies, and deactivate them.
  - A user can be limited to some companies; with none ticked they see all companies. Branch limits come with branches (rule 19).
  - People who existed before roles were added (on Apurvam, Sidharth) became Owners in the migration.
- API: `/api/v1/users/`, `/api/v1/roles/` (with the permission catalogue) and `/api/v1/companies/`. These are the first `/api/v1/` endpoints (decision 0011).
- Later: an audit log of user and role changes (Companies Act audit trail, Module 1), branch limits, and segregation-of-duties checks.
