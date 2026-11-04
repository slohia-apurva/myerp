# MyERP: notes for Claude sessions

MyERP is Apurvam's own web ERP (books, stock, production, purchase, sales, GST, payroll), built to replace ERPNext and later sold as SaaS. Read `docs/specs/00-architecture-and-roadmap.md` (the plan, design rules 1-18, roadmap) and `docs/decisions/` before changing anything structural.

## Rules that code must keep

- Two ledgers (GL, stock ledger) are the source of truth; posted entries are immutable (cancel + amend, never edit).
- Money NUMERIC(18,2), qty/rates NUMERIC(18,6). Never floats.
- Tenant isolation: tenant data is reached only inside `tenancy.context.use_tenant(...)` (the middleware does this per request). Never pass `.using(...)` to reach another tenant. Platform-side apps are listed in `tenancy.router.PLATFORM_APPS`; everything else is tenant-side.
- No tenant-specific code: differences between tenants are data or plan feature flags.
- Tax rates, TDS sections, payroll rates are dated master data, never constants in code.
- AI only creates drafts or suggestions; a person submits.

## Working

- Backend: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`. Needs PostgreSQL 16 with a role that can CREATE DATABASE (tests create and drop `test_myerp_tenant_*`).
- Checks before pushing: `ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && pytest`; frontend `npm ci && npm run build`.
- Every posting rule gets a test. Every bug found with real data becomes a test before it is fixed.
- One small, testable slice per pull request.
