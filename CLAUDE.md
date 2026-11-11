# MyERP: notes for Claude sessions

MyERP is Apurvam's own web ERP (books, stock, production, purchase, sales, GST, payroll), built to replace ERPNext and later sold as SaaS. Read `docs/specs/00-architecture-and-roadmap.md` (the plan, design rules 1-18, roadmap) and `docs/decisions/` before changing anything structural.

## Rules that code must keep

- Two ledgers (GL, stock ledger) are the source of truth; posted entries are immutable (cancel + amend, never edit).
- Money NUMERIC(18,2), qty/rates NUMERIC(18,6). Never floats.
- Tenant isolation: tenant data is reached only inside `tenancy.context.use_tenant(...)` (the middleware does this per request). Never pass `.using(...)` to reach another tenant. Transactions on tenant data use `tenancy.context.tenant_atomic()`, never bare `transaction.atomic` (that opens on the platform database). Platform-side apps are listed in `tenancy.router.PLATFORM_APPS`; everything else is tenant-side.
- No tenant-specific code: differences between tenants are data or plan feature flags.
- Tax rates, TDS sections, payroll rates are dated master data, never constants in code.
- AI only creates drafts or suggestions; a person submits.

## Working

- Backend: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`. Needs PostgreSQL 16 with a role that can CREATE DATABASE (tests create and drop `test_myerp_tenant_*`).
- Checks before pushing: `ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && pytest`; frontend `npm ci && npm run build`.
- Every posting rule gets a test. Every bug found with real data becomes a test before it is fixed.
- One small, testable slice per pull request.
- The user manual lives in `frontend/src/help/manual.tsx` (Help in the top menu; printable). Every pull request that adds or changes a screen updates its chapter in the same PR, in plain words with the on-screen labels in quotes. A new screen also gets a line in `helpTopicFor` (Help.tsx).
- Screen look (Sidharth, 2026-11-11): every form groups its fields in titled boxes using `Section` (Brand.tsx) or a fieldset with a legend, as on the GST and credit tab. Buttons follow the one family in app.css: solid green for Save and main actions, `link`/`secondary` (grey outline) for the rest, `link danger` (red outline) for Disable/Remove. Do not invent new button or box styles.
- Type scale (Sidharth, 2026-11-11): two sets only. Forms: box heading 15px bold deep green, labels 14px. Display (reading) screens: box heading 12px capitals slate, values 14px ink, fact labels 12px slate. Do not add other heading sizes or colours.
- Pickers (Sidharth, 2026-11-11): every dropdown is a type-to-search `Combobox` (Combobox.tsx), never a plain `<select>`, on all screens present and future.
- Import, export and print (Sidharth, 2026-11-11): every masters screen has the standard "Import", "Export", "Print" buttons from `useExchange` (Exchange.tsx), served by `core/exchange.py`. Each master registers once with `exchange.register(Master(...))`, naming the same serializer and save function its screen uses: columns come from the serializer, and imports run the form's own checks. A new master registers in the same PR; a new field that cannot sit in one cell (a relation, a list, rows inside rows) gets a `Codec` or an `exclude`, or registration fails.
- Masters in use (Sidharth, 2026-11-11): once any entry is against a master, its key fields cannot change (names, notes, contacts and Disable stay open). Key fields per master are in `core/locks.py` (`KEY_FIELDS`); every master's save calls `refuse_key_changes`, and each new voucher or stock entry registers its own "in use" test there with `locks.register`.
- No duplicate masters (Sidharth, 2026-11-11): a master never holds two records that mean the same thing. Names compare without capitals or extra spaces (tidied on save by `core/duplicates.py`), within the right scope: the tenant for shared masters (parties, items, units, credit terms, roles, item groups), the company for its own (ledgers and ledger groups share one name list, branches, courier accounts). Registration numbers are unique where they identify one thing (company GSTIN/PAN, party GSTIN, bank account number per company, barcode). Enforce both in the database (a `UniqueConstraint` on `Lower(...)`) and in the master's save function with `duplicates.check_name` / `duplicates.refuse`, which name the existing record and send `existing` so the screen's `ErrorNote` links to it; a new master also adds its kind to `existingHref` (ErrorNote.tsx) and opens a record from `?open=ID` (`useOpenParam`). Imports run the same save function. A migration adding such a constraint first checks existing data and stops with a readable list of clashes.
