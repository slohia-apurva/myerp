# MyERP — Architecture & Roadmap (v2)

Nov 3, 2026 · @Sidharth

> Exported from the planning doc on 4 Nov 2026 (https://claude.ai/artifact/8BXZHcpCW5rpFbRMqRqhFp). From here on this file is the source of truth: change it in a pull request. The v1 outline it builds on, including the full Module 1 masters table and acceptance tests, is in `01-v1-architecture-and-module1.md`.

## What changed from v1

v2 keeps every decision in the Nov 2 outline (Django + React, two ledgers, FIFO, rack/bin allocation, seven gated phases) and fills the gaps a full build would hit. Items marked **(new)** below were not in v1.

| Area | Change | Why it matters |
| --- | --- | --- |
| Scope | Named user roles and a per-module document list | Every module now has a defined set of documents and posting rules to spec against |
| Design rules | Rules 11 to 15 added: GRNI, batches/expiry, inter-company GST, approvals, tax master dates | These are the places ERP books usually go wrong |
| GST | Rate slabs made data-driven with effective dates; GSTR-2B ITC reconciliation added | v1 hard-coded 0/5/12/18/28; slabs changed in Sept 2025 and will change again |
| TDS | Sections held as master data, not code | Income-tax Act 2025 renumbers TDS sections from 1 Apr 2026 |
| Compliance | MCA audit-trail rule, document retention, invoice field rules | Apurva Organics Ltd must keep a non-disableable edit log |
| Non-functional | Security, backups with restore drills, performance targets | v1 had backups only |
| Migration | New section: what moves from ERPNext and how | Cutover was one line in v1 |
| Roadmap | Phase 0 (repo, CI, staging) and data migration made explicit | Each was hidden inside other phases |
| Risks | New section | Single-developer and compliance risks named with fallbacks |

The tax facts above (Sept 2025 slab change, Income-tax Act 2025) are from my own knowledge, not looked up here. Confirm them with your CA before they go into a spec.

## Goals, users and scope

MyERP is an independent, web-based ERP that runs Apurvam's books, stock, production, purchase and sales end to end, written with Claude and owned fully by Apurvam. It replaces ERPNext after 2 to 3 clean months of parallel running.

Target outcomes for v1:

- **Correct books first.** Every transaction posts balanced double-entry GL and stock ledger entries that a CA would accept.
- **Fix today's ERPNext pain points by design.** Sales Orders allocate from a rack/bin warehouse group, reordering uses real min/max and lead times, and work orders track every stage and consumption.
- **Multi-company from day one.** Apurvam Organics LLP and Apurva Organics Ltd as separate legal entities with separate GSTINs, books and numbering, on one install.
- **Indian compliance.** GST (CGST/SGST/IGST, RCM), HSN, e-invoice and e-way bill, TDS/TCS, GSTR-1/3B data, GSTR-2B reconciliation **(new)**.
- **Traceability (new).** Any finished batch traces back to the supplier lots and GRNs it was made from, and forward to the customers it shipped to.

### Users and roles (new)

| Role | Main screens | Can submit | Device |
| --- | --- | --- | --- |
| Owner / admin | MIS, approvals, all reports | Everything | Desktop, phone for approvals |
| Accountant | Journals, payments, bank recon, GST | Accounts vouchers, period close | Desktop |
| Purchase | PO, supplier, price list | PO, purchase invoice | Desktop |
| Stores | GRN, transfers, pick lists, stock count | GRN, stock entries, delivery notes | Desktop or tablet |
| Production | Work orders, job cards, consumption | Job cards, production entries | Tablet on the floor (open decision) |
| Sales | Quotation, SO, customer, receivables | SO, sales invoice | Desktop |
| CA (read-only) | Ledgers, GST reports, audit log | Nothing | Desktop |

### Scope

| In v1 | Later (v2+) | Not planned |
| --- | --- | --- |
| Masters, accounts, inventory, purchase, sales, production, GST, TDS, MIS, fixed assets, loans taken, payroll with staff expenses and staff loans | HR beyond payroll (recruitment, appraisals), CRM pipeline, e-commerce sync, mobile app, budgeting | Multi-currency trading beyond INR (unless exports are confirmed) |

## Best of Tally, ERPNext, Odoo and SAP (added 3 Nov)

MyERP takes the best idea from each of the four systems and leaves out the parts that cause pain today. Every borrowed idea below maps to a design rule or module in this doc. Anything not yet covered is marked **(adopt)** and becomes part of that module's spec.

| System | What we take | Where it lands | What we leave out |
| --- | --- | --- | --- |
| Tally | Group and sub-group ledger tree; keyboard-first voucher entry with shortcut keys; bill-wise tracking of receivables and payables; instant drill-down from any report figure to the voucher; simple day book and group summary | Module 1 chart of accounts, link field, report framework; **(adopt)** shortcut-key voucher screens in Module 2 | Editable past vouchers with no reversal trail; weak warehouse, batch and production control |
| ERPNext | Draft → submit → cancel → amend lifecycle; GL and stock ledger as the source of truth; naming series; link fields; per-document permissions; BOM → work order → job card flow | Rules 1–3 and 10, Module 1 platform, Module 5 | Group warehouses that can't hold reservations; slow full reposting; customisation that breaks on upgrade |
| Odoo | Modern screens: list, form, kanban and pivot views of the same records; a comment and activity feed on every document, with follow-ups and @mentions; every stock movement recorded as from-location → to-location, including virtual locations (supplier, customer, production, scrap); bank statement matching screen; barcode-driven picking | **(adopt)** document activity feed and kanban/pivot views as cross-cutting features; **(adopt)** from → to stock moves in the Module 3 stock ledger design; bank recon in Module 2 | Accounting entries that can be edited after posting; key features locked behind paid modules |
| SAP | GR/IR clearing account; three-way match of PO, GRN and invoice with price and quantity tolerances; a fixed code for every stock movement type; posting periods opened per account type; approval release strategies; segregation of duties | Rule 11 (GRNI), rule 7, rule 15; **(adopt)** three-way match with tolerances in Module 3; **(adopt)** movement-type codes on every stock entry; **(adopt)** a conflict check so one user can't both create and approve the same payment | Complexity, licence cost, and long implementation cycles |

The guiding test for any new feature is whether it makes the books more correct or a daily task faster. If it does neither, it waits for v2.

## Tech stack and architecture

The stack is unchanged from v1: Python/Django on PostgreSQL with a React front end, as a layered monolith where every module posts through one shared core. v2 adds the operational pieces a production system needs.

| Layer | Choice | Why |
| --- | --- | --- |
| Database | PostgreSQL 16 | Real transactions, row locks, NUMERIC for money, strong reporting SQL |
| Backend | Django 5 + Django REST Framework | ORM, migrations, auth, admin screens; huge ecosystem |
| Background jobs | Celery + Redis | Reposting, e-invoice calls, scheduled reorder runs, report exports |
| Front end | React + TypeScript (Vite), TanStack Query, a data-grid library | Fast forms and editable item grids |
| PDFs | WeasyPrint (HTML/CSS to PDF) | Modern CSS for invoice and voucher print formats |
| Reports / MIS | SQL views + Django endpoints; Metabase later if needed | MIS on the same database, no sync |
| Tests | pytest + factory\_boy | Every posting rule gets an automated test |
| File storage **(new)** | S3-compatible object storage | Attachments (supplier bills, COAs, certificates), exports, backups |
| Email / notifications **(new)** | Transactional email service; WhatsApp later | Send invoices and POs, approval alerts |
| Error monitoring **(new)** | Sentry (or self-hosted GlitchTip) | Know about a failed posting before a user reports it |
| Login security **(new)** | Sign in with Google (no MyERP passwords); Google 2-Step Verification enforced for staff; see decision 0007 | Books and GST data are high-value |
| Deploy | Google Cloud, Mumbai region: Cloud Run, Cloud SQL, Memorystore (see Hosting) | One-command deploy; data stays in India |
| Code | Private GitHub repo, GitHub Actions CI | Claude works from the repo each session; tests on every push |

Alternative if you prefer JavaScript end to end: NestJS + Prisma + PostgreSQL. Same architecture, less built-in admin.

### Repo layout

```
myerp/
  backend/
    tenancy/       # tenants, plans, tenant resolver, global masters and their sync
    core/          # company, users, permissions, naming, audit, posting service, approvals
    masters/       # items, parties, warehouses, UOM, price lists, tax masters
    accounts/      # GL, journals, payments, bank recon, period close
    stock/         # stock ledger, receipts, transfers, batches, reservations, reorder, quality
    buying/        # PO, GRN, landed cost, purchase invoice
    selling/       # quotation, SO, pick list, delivery, sales invoice, returns
    manufacturing/ # BOM, work orders, job cards, job work
    gst/           # tax calculation, e-invoice, e-way bill, returns data, 2B recon
    tds/           # TDS/TCS deduction, challans, returns data
    reports/       # MIS endpoints
    migration/     # ERPNext import scripts and reconciliation checks
  frontend/        # React + TypeScript
  docs/specs/      # one spec per module
  docs/decisions/  # short notes on each fixed choice
  deploy/          # Docker Compose, backup and restore scripts
```

## Hosting (added 4 Nov)

The recommendation is Google Cloud in the Mumbai region (asia-south1), with backups copied to Delhi (asia-south2), so all data stays in India. With the managed option you install no software on any server: Google runs the database, Redis and servers, and MyERP ships as Docker images. A VPS is cheaper, but you then own patching, backups and database care, which is a real load for a one-person team.

### What each option needs

| Need | Google Cloud (recommended) | Self-managed VPS (Ubuntu 24.04 LTS) |
| --- | --- | --- |
| Django API and React front end | Cloud Run (runs the app's Docker image, scales on its own) | Docker Engine + Docker Compose |
| PostgreSQL 16, one database per tenant | Cloud SQL for PostgreSQL, with automatic backups and point-in-time recovery | PostgreSQL 16 in Docker, plus PgBouncer |
| Redis for background jobs | Memorystore for Redis | Redis in Docker |
| Celery workers and scheduled jobs | A small Compute Engine VM running the worker image (or Cloud Run jobs + Cloud Scheduler) | Worker containers in the same Compose file |
| HTTPS and tenant subdomains (\*.myerp.in) | Cloud Load Balancer + Certificate Manager wildcard certificate, Cloud DNS | Caddy or Nginx with Let's Encrypt wildcard certificate |
| Files, exports and backups | Cloud Storage buckets in Mumbai, copy in Delhi | S3-compatible object storage in India, plus WAL-G or pgBackRest for database backups |
| Passwords and API keys | Secret Manager | Env file readable only by root |
| Logs, monitoring, alerts | Cloud Logging and Monitoring, plus Sentry for app errors | Uptime Kuma + Sentry; logs on disk |
| Security patches | Done by Google | You: unattended-upgrades, ufw firewall, fail2ban, SSH keys only |
| Deploys | GitHub Actions builds the image into Artifact Registry and deploys to Cloud Run | GitHub Actions builds the image and runs a deploy script over SSH |
| Email | A transactional email service (SendGrid, Amazon SES or similar) | Same |
| Rough monthly cost, production + staging | About ₹15,000–30,000 to start | About ₹4,000–8,000 |

The costs are rough guesses from memory. Check them with the Google Cloud pricing calculator before deciding. Cloud SQL is most of the Google bill, and staging can use a smaller instance that is switched off at night.

Python packages (Django, Celery, WeasyPrint and its fonts) and the React build all live inside the Docker image that CI builds, so nothing is hand-installed on either option.

### What you need to set up on Google Cloud

- [ ] A Google Cloud account with billing on a company card (Apurvam or the future SaaS entity)
- [ ] Two projects: myerp-staging and myerp-prod
- [ ] A domain for the app, for example myerp.in or a subdomain of apurvam's site
- [ ] Access for the build pipeline. I'll write the setup scripts (Terraform) so the services are created the same way in both projects

## SaaS-ready design (added 4 Nov)

MyERP is built as a multi-tenant product from Phase 0, even while Apurvam is its only user. Each customer (a group of companies) is a tenant with its own PostgreSQL database and its own users. Every tenant runs the same code, and global masters are maintained once and shared read-only. Building this in now adds about 2 weeks; adding it after go-live would mean touching every table and query.

_Diagram in the planning doc: one code base; a platform database and global masters; one database per tenant, each with a read-only copy of global masters._

A request reaches only its own tenant's database. Shared masters reach every tenant as a read-only copy.

### Three layers of data

| Layer | Lives in | Holds | Who can change it |
| --- | --- | --- | --- |
| Platform | One platform database | Tenants, plans, billing, each tenant's database connection, platform admins, support access log | Platform admins only |
| Global masters | Platform database, copied into every tenant database as read-only tables | HSN/SAC codes, GST rate table, TDS/TCS sections, states and state codes, countries and currencies, standard UOMs, bank IFSC list, Tally standard group template, PF/ESI rates, professional tax slabs, base print templates | Platform admins, published as a new version |
| Tenant | One database per tenant | Its companies, users and roles, all masters and transactions, both ledgers, custom fields, print formats, reports, approval rules, AI settings | That tenant's own admins |

### How it works

- **Tenant resolver.** Each tenant gets its own address, such as apurvam.myerp.in. Before login, the app looks up the tenant in the platform database and connects only to that tenant's database. Users and sessions live in the tenant database, so a user of one tenant cannot log in to another.
- **Global masters are synced, not shared live.** PostgreSQL can't link rows across databases, so a sync job copies each new version of the global masters into every tenant database. There the app can only read them, which keeps reports fast and makes each tenant's backup complete on its own. A tenant that needs a different value, such as a special GST rate on one item, records an override in its own database. The global value is never edited.
- **Customisation without code forks.** Everything a tenant can change is stored as data in its own database. That covers custom fields (a JSON column on every document plus field definitions), print formats, report definitions, dashboards, approval rules, naming series, roles and workflow states. No code is ever written for one tenant, so one upgrade serves everyone.
- **One version, rolled out in waves.** Each release runs its database migrations on every tenant database in turn, with Apurvam first as the pilot. Custom fields sit in the JSON column, so a migration never clashes with a tenant's customisations.
- **Everything carries the tenant.** Background jobs, file storage (a folder per tenant), logs, backups, AI calls and AI spending caps are all tagged with their tenant. Scheduled jobs loop over tenants.
- **Room to grow.** One PostgreSQL server holds many tenant databases behind a connection pooler (PgBouncer). A large tenant moves to its own server by changing one connection record. A separate database per tenant gives the strongest isolation, as you asked. If tenants number in the hundreds, revisit the cost of this at Phase 10.

### Design rules added

- **Rule 16: Tenant isolation.** Every request, job and file belongs to exactly one tenant and opens only that tenant's database. An automated test logs in to tenant A, tries to reach tenant B's data, and must fail.
- **Rule 17: Global masters are read-only to tenants.** Tenants override values locally and never edit shared data.
- **Rule 18: No tenant-specific code.** Every difference between tenants is configuration or data in their own database, or a feature flag in their plan.

### Needed before selling (Phase 10)

- Self-service onboarding: create the database, run migrations, seed the Tally groups and chart of accounts, sync global masters, create the first admin
- Plans and billing: users and companies per plan, feature flags (AI, payroll, production), subscription invoicing
- Platform admin console: each tenant's health, version, storage and usage
- Support access: platform staff enter a tenant only with its permission, and every visit shows in that tenant's audit log
- Tenant data export, and deletion when a customer leaves
- Legal: terms of service, a data processing agreement, and personal-data duties under India's DPDP Act (check with a lawyer)

## Core design rules

These rules are fixed before any module is written, and every later module must obey them. Rules 1 to 10 are v1's, shortened; 11 to 15 are new.

1. **Two ledgers are the source of truth.** GL entries and stock ledger entries. Every balance and valuation is derived from them and can be rebuilt.
2. **Posted entries are immutable.** Corrections are cancel (exact reversal) and amend (new version), each with user and timestamp.
3. **Document lifecycle:** Draft → (Pending approval) → Submitted → Cancelled. Only Submitted documents touch ledgers.
4. **Every GL posting balances** per voucher and per company, enforced by the shared posting service and a database check.
5. **Precision:** money NUMERIC(18,2), rates and quantities NUMERIC(18,6), exchange rates NUMERIC(18,9). Never floats. One rounding function, one round-off account.
6. **Multi-company on every row.** Every transaction and ledger row carries company\_id; all queries filter by it.
7. **Fiscal periods can be locked.** Nothing posts into a closed month without an authorised reopen, which is itself audited.
8. **FIFO per item-warehouse.** Lot queues per item-warehouse; transfers carry lot rates; backdated entries trigger a background repost for that item.
9. **Warehouses are a tree with real allocation.** Orders reserve against a parent (rack group); picking resolves to leaf bins.
10. **One posting service, many documents.** All documents call the same tested functions to write ledger rows.
11. **Received-not-billed is explicit (new).** A GRN debits stock and credits a Stock Received But Not Billed (GRNI) account; the purchase invoice clears it. Price differences between GRN and invoice post to a purchase price variance account, or revalue stock if it is still on hand. Landed costs (freight, loading) are added to lot rates through a landed cost voucher.
12. **Batches carry expiry and status (new).** Batch-tracked items record manufacturing date, expiry and QC status (quarantine, released, rejected). Only released batches can be picked; picking suggests first-expiry-first-out within FIFO valuation.
13. **Inter-company and inter-GSTIN movements are sales (new).** Stock moving between the LLP and the Ltd, or between two GSTINs of one company, posts a tax invoice and a matching purchase, with GST. Moves within one GSTIN are plain transfers.
14. **Tax rules are dated master data (new).** GST rates, HSN mappings, TDS sections and thresholds live in tables with valid-from dates. A rate change is a data entry, not a code change, and old documents keep the rate of their date.
15. **Approvals are rules, not code (new).** Approval rules per document type and company (e.g. PO above ₹1 lakh needs owner approval; sales below a margin floor needs approval; credit-limit breach blocks SO submit).

## Module map

Each module below lists the documents it owns and what they post. This is the checklist each module spec in docs/specs/ must cover.

| Module | Documents | Posts to GL | Posts to stock ledger | Key reports |
| --- | --- | --- | --- | --- |
| 1. Foundation and masters | Company, users, roles, naming series, all masters, import tool | No | No | Master lists, audit log |
| 2. Accounts | Journal entry, payment entry (receipt/payment/contra), bank reconciliation, debit/credit note (non-stock), period close, opening balance entry | Yes | No | Trial balance, P&L, balance sheet, GL, day book, cash/bank book, ageing |
| 3a. Stock | Stock entry (receipt, issue, transfer), stock reconciliation (physical count), batch, quality inspection, material request | Yes (stock value) | Yes | Stock balance, stock ledger, batch-wise stock, expiry report, stock ageing |
| 3b. Purchase | Material request, PO, GRN, landed cost voucher, purchase invoice, purchase return, debit note. GRN rules **(added 7–8 Nov)**: quantity above the PO is accepted, with an alert to the Purchase team and the Owner; an optional quality add-on on receipt checks cartons (CFC) and the batch code printed on packs | Yes | Yes (GRN, return) | Pending POs, GRNI, purchase register, supplier ageing |
| 3c. Reorder engine | Reorder run → draft material requests or POs | No | No | Shortage list, below-min items |
| 4. Sales | Quotation, SO (with reservation), pick list, delivery note, sales invoice, sales return, credit note | Yes | Yes (delivery, return) | Pending SOs, sales register, receivables ageing, customer statement |
| 3d/4b. Imports and exports **(added 5 Nov)** | Import file with several bills of entry (part clearance, into-bond and ex-bond), duties into landed cost; export file with export invoice (LUT or IGST paid), packing list, shipping bill, certificates, realisation (e-BRC), IGST refund and RoDTEP. Spec: [03-imports-and-exports.md](03-imports-and-exports.md) | Yes (duty, forex gain/loss, incentives) | Yes (via GRN, delivery) | Import and export registers, stock in bond, landed cost per batch, unrealised exports, refunds pending |
| 5. Production | BOM (multi-level, versioned), work order, job card per stage, material transfer to WIP, production entry, scrap/by-product entry, job work challan **(new)** | Yes (WIP, finished goods) | Yes | WIP, yield, BOM vs actual consumption, batch genealogy |
| 6a. GST | E-invoice (IRN), e-way bill, GSTR-1 data, GSTR-3B data, GSTR-2B reconciliation **(new)**, ITC-04 for job work **(new)** | RCM and ITC entries | No | GST registers, ITC mismatch report |
| 6b. TDS/TCS **(new)** | Deduction on purchase invoice/payment, challan entry, certificate tracking | Yes | No | TDS payable, 26Q/27EQ data |
| 6c. MIS | Dashboards | No | No | Sales, margin by item/customer, stock ageing, production yield, cash position |

### Fixed assets, loans and payroll (added 3 Nov)

These three modules sit on the accounts core and post through the same posting service. They are built after GST/TDS/MIS and before migration, so the parallel run covers a complete balance sheet and payroll.

| Module | Documents | Posts to GL | Key reports |
| --- | --- | --- | --- |
| 7a. Fixed assets | Asset category (useful life, depreciation method and rate), asset register, capitalisation from a purchase invoice or journal, capital work in progress, monthly depreciation run, transfer between locations, sale or scrap of an asset (with GST on sale), revaluation | Yes | Asset register, depreciation schedule, Schedule III fixed asset note, block-wise tax depreciation |
| 7b. Loans taken | Lender master (bank, NBFC, director, partner, other), loan account split into secured and unsecured, sanction details and security/charge, disbursement, repayment schedule (EMI or bullet), interest accrual, repayment entry, prepayment, TDS on interest paid to non-banks | Yes | Loan statement per lender, secured vs unsecured schedule, current vs non-current maturities, interest paid |
| 8a. Payroll | Employee master (PAN, UAN, ESI number, bank, department, company), salary structure, attendance and leave, monthly payroll run, statutory deductions (PF, ESI, professional tax, labour welfare fund, TDS on salary), payslips, bank transfer file, bonus and gratuity provisions, full and final settlement | Yes | Salary register, PF/ESI/PT returns data, Form 16 data, cost by department |
| 8b. Staff daily expenses | Expense claim with bill photos, petty cash/imprest per person or site, cash advance to staff and its settlement, approval by expense rule, GST credit on eligible bills | Yes | Expense register by head and person, open advances, petty cash book |
| 8c. Staff loans and advances | Loan or salary advance to an employee, instalment schedule, recovery through the payroll run, balance write-off on exit, interest if charged | Yes | Staff loan ledger, recovery schedule, balance due on exit |

Design rules for these modules:

- **Depreciation is kept twice.** Book depreciation (Companies Act Schedule II for the Ltd, the firm's policy for the LLP) and income-tax block-of-assets depreciation are separate schedules; only book depreciation posts to the GL.
- **Loan interest is accrued monthly** and every repayment splits into principal and interest from the schedule, so the balance sheet shows the correct current maturities.
- **Staff loans are recovered by payroll, not by hand.** A payroll run picks up each due instalment as a deduction, and a staff member's exit settlement nets off any loan or advance still open.
- **Payroll rules are dated master data**, like GST (rule 14): PF and ESI rates and ceilings, professional tax slabs per state, and the wage definition under the new labour codes. Confirm the labour code effects with your CA.

### Cross-cutting features (new)

- **Print formats:** GST-compliant tax invoice, delivery challan, PO, payment voucher, batch labels with barcodes, bin labels.
- **Attachments:** any document can hold files (supplier bill scan, certificate of analysis, organic certificate).
- **Email from the app:** send invoice/PO PDF to the party's email.
- **Generic import/export:** CSV/Excel import for every master and opening balance, with a dry-run that shows errors before saving.
- **Barcode scanning** on pick lists, GRNs and stock counts (USB or phone camera).
- **Warehouse mobile app (added 9 Nov):** one installable app with workspaces by role (Receive, Job work, Dispatch, Move, Count, Sales, Approvals) for GRN, customer material for job work, delivery, return of customer goods and moves within or between sites, built alongside Phases 3 to 5. Spec: [05-warehouse-mobile-app.md](05-warehouse-mobile-app.md)

## AI in MyERP (added 3 Nov)

Yes, MyERP should use AI, but only as an assistant that prepares drafts and flags problems. A person always submits. AI never posts to the ledgers, so design rules 1 to 3 stay exactly as they are.

### Where AI fits

| Feature | What it does | Module | When |
| --- | --- | --- | --- |
| Bill capture | Reads a supplier bill (PDF or phone photo) and creates a draft purchase invoice. It finds the supplier by GSTIN, matches lines to items, UOMs and HSN, and fills in taxes. It also suggests the matching PO and GRN. | 3b | After Phase 3 gate |
| Expense receipt capture | Reads a staff expense receipt into a draft claim and flags receipts already claimed | 8b | After Phase 8 gate |
| Bank matching | Suggests which invoice or payment each bank statement line belongs to, including part-payments and clubbed payments | 2 | After Phase 2 gate |
| GSTR-2B matching | Matches supplier invoices that differ only in invoice-number format or rounding | 6a | After Phase 6 gate |
| Ask your data | Answers plain-language questions such as "which distributors in Maharashtra are overdue over 60 days?" or "margin on 500 g packets last quarter vs the one before". It runs the existing reports and shows them with drill-down. | 6c | After Phase 6 gate |
| Anomaly alerts | Daily checks for duplicate bills, a rate far from an item's history, GST rate or state mismatches, unusual journals, or a bin's stock going negative. Each alert links to the document. | 2, 3, 6 | Rules first, AI ranking later |
| Demand and reorder suggestions | Suggests min/max and reorder quantities per item-warehouse from sales history, seasonality and lead times. The buyer approves. | 3c | After 12 months of data in MyERP |
| Month-end commentary | Drafts a one-page MIS note explaining what moved in sales, margin, stock and cash. Every figure comes from reports. | 6c | After first month-end close |
| Drafting help | Drafts payment reminders, PO emails and customer statements for a person to send | 4, 3b | Any time |
| Migration cleanup | Finds duplicate items and parties in the ERPNext export, and suggests missing HSN codes and UOMs | 9 | Phase 9 |

### Guardrails

1. **Drafts only.** AI can create a Draft document or a suggestion. Submitting, cancelling, approving and paying stay with a person who has that permission.
2. **Numbers come from the database, not the model.** An answer about balances or sales is built from the same report endpoints people use. The answer shows the report it came from, and every figure drills down to vouchers.
3. **Same permissions as the user.** The assistant sees only the companies, documents and reports the logged-in user can see. It uses read-only report tools, never free-form SQL or write access.
4. **Everything is logged.** The audit log records each AI suggestion with the source file, extracted values and confidence. It also records who accepted or changed the suggestion.
5. **Measured before it is switched on.** Each feature is tested on a set of real Apurvam bills or statements and must hit an agreed accuracy, for example 95% of bill lines correct, before being enabled. Low-confidence fields are highlighted for checking.
6. **Data sent out is minimal.** Only the document or question being handled is sent to the AI provider, with no training on our data. Bank and salary details are masked where they aren't needed.
7. **Can be switched off.** Each feature has an on/off switch per company and a monthly spending cap. MyERP works fully with AI off.

### How it is built

A small `ai/` app in the backend calls the Claude API (Anthropic). Slow jobs such as bill reading, anomaly runs and forecasting run on the existing Celery workers. "Ask your data" gives the model a fixed set of tools, one per report, that apply the user's permissions. Forecasting starts with standard statistical methods; the language model only explains the result. None of these features is on the cutover path, so a delay in AI never delays replacing ERPNext.

## Compliance requirements

Compliance is built into the design rules, not added at the end; each line below names the module that owns it. All of these are from memory and need your CA's confirmation before they are specced.

| Requirement | What the system must do | Module |
| --- | --- | --- |
| Audit trail (Companies Act, from Apr 2023) | Record every create, edit and delete on books with user, time, old and new value; the feature cannot be turned off. Applies to the Ltd; build it for the LLP too | 1 |
| Books kept and backed up in India | Daily backup to a server located in India; keep 8 years of records | 0, deploy |
| GST rate slabs | Rates are dated master data (rule 14). Slabs were rationalised in Sept 2025 to mainly 5% and 18%, with a 40% rate for a few goods, so v1's 0/5/12/18/28 template list must not be hard-coded | 1, 6a |
| Tax invoice fields | GSTIN of both sides, place of supply, HSN (4 or 6 digits by turnover), taxable value, tax split, reverse-charge flag, signature | 4 |
| E-invoice and e-way bill | IRN and QR on B2B invoices if turnover is over the e-invoice threshold; e-way bill for consignments over ₹50,000; time limit for IRN generation tracked | 6a |
| ITC conditions | Match purchase invoices to GSTR-2B; flag ITC to reverse when a supplier is unpaid after 180 days | 6a |
| MSME payments (43B(h)) | Mark suppliers registered as micro/small; warn on bills unpaid after 45 days, since late payment is disallowed as an expense | 3b, 2 |
| TDS/TCS | Sections, rates and thresholds as dated master data. The Income-tax Act 2025 renumbers sections from 1 Apr 2026, so no section number appears in code | 6b |
| Food / organic traceability | If products fall under FSSAI and organic certification: FSSAI licence on invoices and labels, lot traceability from supplier to customer, certificate attachments per supplier and batch | 3a, 5 |

## Non-functional requirements (new)

These targets apply to every module and are checked at each phase gate.

| Area | Target |
| --- | --- |
| Availability | Working hours 9am to 9pm IST; planned updates outside them |
| Backups | Nightly full PostgreSQL dump plus continuous WAL archiving to object storage in India; 30 daily and 12 monthly copies kept |
| Restore drill | Restore to a fresh server once a month; must complete in under 2 hours (RTO) with at most 15 minutes of lost data (RPO) |
| Security | HTTPS only; Sign in with Google, with 2-Step Verification enforced in Google Workspace; only people an admin added can sign in; secrets outside the repo; database not reachable from the internet |
| Permissions | Checked in the API on every request, never only in the UI |
| Performance | Voucher save under 1 second for 50 lines; link-field search under 300 ms on 5,000+ items; trial balance for a year under 3 seconds |
| Scale (sizing guess) | 15 concurrent users, 100k ledger rows a year per company; to be confirmed with real ERPNext volumes |
| Browser support | Latest Chrome and Edge on desktop; tablet screens only for the modules decided in open decisions |
| Observability | Error alerts to email; a daily health check that ledgers balance and stock value equals the stock GL account |

## Data migration from ERPNext (new)

Migration moves masters and balances, not full history: the new system starts from opening balances on a cutover date, and ERPNext stays read-only for anything older. Migration scripts live in backend/migration/ and are rerun for every parallel-run month.

| What | How it moves | Check after import |
| --- | --- | --- |
| Masters (items, parties, warehouses, accounts, BOMs, price lists) | ERPNext export → MyERP import with dry-run; ERPNext codes kept in a legacy-code field | Counts match; spot-check 20 records each |
| Opening GL balances | One opening entry per company per account, from ERPNext trial balance on cutover date | Trial balance identical |
| Open receivables and payables | Invoice-wise, so ageing and payment matching keep working | Party balances and ageing match |
| Opening stock | Per item, warehouse (leaf bin) and batch, with FIFO lots and rates from ERPNext's stock ledger | Quantity and value per item-warehouse match |
| Open documents | Open POs, SOs and work orders re-entered with pending quantities | Pending lists match |
| GST and TDS carry-over | Unclaimed ITC, TDS payable and unpaid challans as opening items | Balances agreed with CA |
| History | Not migrated. ERPNext kept read-only, with a database backup kept for 8 years | n/a |

The new modules also need opening data. Each fixed asset moves with its cost, accumulated book depreciation and tax written-down value. Each loan moves with its outstanding principal, its remaining schedule and any accrued interest. For payroll, each employee needs their master data, year-to-date salary and tax figures for the current financial year, and any open staff loan or advance balance.

Cutover is best on the first day of a quarter after a month-end close. The bin structure may not exist in ERPNext today, so the first physical count in MyERP assigns stock to bins.

## Roadmap

The build is now about 11 to 15 months of part-time work, then 2 to 3 months of parallel running. v2 adds Phase 0 for setup, folds TDS into Phase 6, adds fixed assets, loans and payroll as Phases 7 and 8, makes migration its own phase, and adds Phase 10 to prepare MyERP for sale as SaaS. The multi-tenant foundation itself is built in Phases 0 and 1, adding about 2 weeks.

_Roadmap diagram in the planning doc. Phases: 0 Setup (2–3 wks) · 1 Foundation and masters (4–6) · 2 Accounts core (6–8) · 3 Stock and purchase (8–10) · 4 Sales (6–8) · 5 Production (6–8) · 6 GST, TDS and MIS (5–7) · 7 Fixed assets and loans (3–4) · 8 Payroll and staff (6–8) · 9 Migration and cutover (2–3 months) · 10 SaaS launch (6–8). Each phase closes with a gate tested on real Apurvam data._

A phase starts only when the gate above it passes. Durations are estimates for one person working with Claude a few hours a day; dates get set once the target cutover date is known.

## Module 1 spec: changes to v1

The v1 Module 1 spec (platform pieces, link field, report framework, masters table, acceptance tests) stands as written. The changes below are added to it.

### Master changes

| Master | Change |
| --- | --- |
| Tax templates | Rates move to a dated GST rate table (rate, valid from, valid to); templates point at it. Seed current slabs, not 0/5/12/18/28 |
| HSN master **(new)** | HSN/SAC code, description, default GST rate with valid-from date; items link to it |
| TDS/TCS section **(new)** | Section, nature of payment, rate, threshold, valid from; parties link to their section |
| Item | Add: shelf life drives batch expiry; QC required flag; FSSAI category if relevant; reorder fields per item-warehouse instead of per item |
| Customer / Supplier | Add: MSME registration and type; GST registration type (regular, composition, unregistered, SEZ); legacy ERPNext code |
| Warehouse | Add: GSTIN address it belongs to (needed for rule 13); barcode for bins |
| Approval rule **(new)** | Document type, company, condition (amount, margin, credit), approver role |
| Print format **(new)** | Per document type and company, HTML template with letterhead |

### Item units of measure with dimensions and weight (added 3 Nov)

Every item can have several units of measure (UOMs), and each UOM records its own length × breadth × height and weight. Stock is always held in the item's stock UOM (design rule), but any document can buy, sell, pick or move in any of the item's UOMs.

Example for one product:

| UOM | Contains | = stock UOM | L × B × H (cm) | Net wt (kg) | Gross wt (kg) | Volume (m³) | Barcode | Whole numbers only | Default for |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Packet (500 g) | stock UOM | 1 | 18 × 12 × 5 | 0.500 | 0.520 | 0.00108 | Packet EAN | Yes | Stock, retail sale |
| Inner box | 6 packets | 6 | 26 × 19 × 16 | 3.000 | 3.250 | 0.00790 | Inner box code | Yes | Sales to shops |
| Carton | 4 inner boxes | 24 | 54 × 40 × 34 | 12.000 | 13.400 | 0.07344 | Carton code | Yes | Purchase, sales to distributors |
| Pallet | 40 cartons | 960 | 120 × 100 × 150 | 480.000 | 560.000 | 1.80000 | none | Yes | Dispatch planning |

The figures are illustrative only.

Rules:

- **Item UOM table.** Each item has one row per UOM. A row holds the UOM, what it contains (the next UOM down and how many), its conversion to the stock UOM, length, breadth and height in cm, net and gross weight in kg, a barcode, a whole-numbers-only flag, and default-for flags (purchase, sales, stock, production).
- **Conversions are exact and chained.** A carton's factor is computed from the chain (4 inner boxes × 6 packets). It is stored as NUMERIC, never a float, and the factors must agree up and down the chain.
- **Volume is derived.** Volume is computed from L × B × H and never typed. A missing dimension shows as a warning on the item, not an error, so items can be created before measurements are taken.
- **Transactions keep the UOM entered.** Each line stores the UOM, the quantity in that UOM, the conversion factor used, and the stock-UOM quantity. Changing the item master later never changes a posted document.
- **Whole-number UOMs are enforced.** A sales order for 2.5 cartons is rejected if cartons are whole-number only. Pick lists suggest full cartons first, then inner boxes, then loose packets.
- **Price per UOM.** Price lists can hold a separate rate per UOM (a carton rate need not be 24 × the packet rate).

Where dimensions and weight are used:

- Delivery note, invoice and e-way bill: total gross weight and number of packages, worked out from the UOMs on the lines
- Dispatch planning: total weight and volume per vehicle against its capacity
- Landed cost: freight split across GRN lines by weight or volume, not only by value
- Bins: **(adopt)** optional bin dimensions and maximum weight, so putaway warns when a bin is full
- Labels: carton and pallet labels print barcode, contents, weight and dimensions

### Chart of accounts: Tally-style groups and ledgers (added 3 Nov)

The chart of accounts works like Tally. Every ledger sits under a group, and groups can have sub-groups to any depth. A ledger takes its nature (asset, liability, income, expense) from the primary group at the top of its branch, so a new sub-group or ledger needs no accounting setup.

- **Groups vs ledgers.** Only ledgers take postings. A group only totals the ledgers and sub-groups under it.
- **Seeded groups.** Each company starts with Tally's 15 primary groups and 13 standard sub-groups (below). Users add their own sub-groups under any of them, such as Trade Creditors → Raw Material Suppliers → Organic Farm Suppliers.
- **Group settings, as in Tally.** Each group has a nature, inherited from the primary group. It also has a flag for whether it is gross profit (direct) or not, a flag to show net debit/credit balances in reports, and a flag for whether it behaves like a sub-ledger. Sub-groups inherit these settings unless overridden.
- **Parties are ledgers.** A new customer or supplier gets a ledger under Sundry Debtors or Sundry Creditors, or a sub-group the user chooses, such as Sundry Debtors → Distributors → Maharashtra. Banks, loans, assets and staff work the same way under their groups.
- **Moving is safe.** A ledger or sub-group can move to another group within the same nature without touching any posting. Only report grouping changes, because balances are always derived from the ledgers (rule 1). Moving it to a different nature is blocked once it has postings.
- **Reports follow the tree.** The trial balance, balance sheet and P&L show the group tree, with expand and collapse to any level. A group summary drills down from group to sub-group to ledger to voucher, as Tally does. A separate mapping table produces the Schedule III balance sheet for the Ltd.

| Primary group | Nature | Standard sub-groups |
| --- | --- | --- |
| Capital Account | Liability | Reserves & Surplus |
| Loans (Liability) | Liability | Secured Loans, Unsecured Loans, Bank OD A/c |
| Current Liabilities | Liability | Duties & Taxes, Provisions, Sundry Creditors |
| Suspense A/c | Liability | none |
| Branch / Divisions | Liability | none |
| Fixed Assets | Asset | none |
| Investments | Asset | none |
| Current Assets | Asset | Bank Accounts, Cash-in-hand, Deposits (Asset), Loans & Advances (Asset), Stock-in-hand, Sundry Debtors |
| Misc. Expenses (Asset) | Asset | none |
| Sales Accounts | Income (direct) | none |
| Direct Incomes | Income (direct) | none |
| Indirect Incomes | Income | none |
| Purchase Accounts | Expense (direct) | none |
| Direct Expenses | Expense (direct) | none |
| Indirect Expenses | Expense | none |

The Secured Loans and Unsecured Loans groups feed the loans module (7b). Staff loans go under Loans & Advances (Asset), and fixed asset categories become sub-groups of Fixed Assets.

### Added acceptance tests

- [ ] A GST rate changed with a future valid-from date applies only to documents dated on or after it
- [ ] An audit-log entry cannot be edited or deleted by any role, including admin
- [ ] Only people added by a tenant admin can sign in, and only at that tenant
- [ ] An approval rule (PO over ₹1 lakh) is saved and readable by Module 3
- [ ] A restore of last night's backup on a fresh server completes and the app logs in
- [ ] Item import dry-run on a bad CSV lists every row error without saving anything

* [ ] A sub-group three levels deep under Sundry Creditors is created, and its ledgers roll up correctly in the trial balance
* [ ] Posting to a group (not a ledger) is rejected
* [ ] Moving a ledger with postings between groups of the same nature changes the group totals with no change to any voucher
* [ ] Moving a ledger with postings from an expense group to an asset group is rejected
* [ ] Creating a customer creates its ledger under the group chosen on the customer form

- [ ] An item with packet → inner box → carton → pallet UOMs saves with the correct chained factors; a factor that breaks the chain is rejected
- [ ] Volume is computed from L × B × H and can't be typed in
- [ ] A sales order line for 2.5 cartons is rejected when cartons are whole-number only
- [ ] A delivery note with mixed UOM lines shows the correct total gross weight and package count
- [ ] Changing an item's conversion factor doesn't change the stock quantity on an already-submitted document
- [ ] Scanning a carton barcode adds one carton (24 stock units) to a pick list

## How we work

The v1 working method stands: the repo is the project's memory, spec before code, small testable slices, real Apurvam cases become tests, staging before production, and a parallel run before switch-off. Two additions:

- **Decision log.** Every fixed choice (FIFO, stack, hosting) gets a short note in docs/decisions/ so it is never re-argued.
- **CA review per posting module.** Modules 2, 3, 4, 5 and 6 each end with a CA walk-through of the posting rules and sample vouchers, before their gate.

## Risks (new)

| Risk | Effect | Mitigation |
| --- | --- | --- |
| One builder, part-time | Timeline slips; knowledge sits with one person | Specs, decision log and tests in the repo; small slices so any pause is safe |
| Wrong posting rule found after go-live | Books need correction across months | CA sign-off per module; daily ledger-balance health check; parallel run |
| Tax rules change mid-build | Rework in GST/TDS | Rule 14: rates and sections as dated data |
| Migration mismatch | Opening balances don't tie out | Repeatable scripts, rerun monthly in the parallel run |
| Server loss | Downtime, data loss | WAL backups, monthly restore drill |
| Scope creep (CRM, payroll) | v1 never ends | Out-of-scope list; new asks go to a v2 backlog |

## Open decisions

- [x] Stack: Django + React (decided 4 Nov)
- [x] Default stock valuation: FIFO for all items (decided)
- [ ] Hosting: VPS you manage, or a managed platform (Render / Railway / AWS) at higher cost
- [ ] Mobile/tablet screens in v1 for production, stores or sales? (Stores: yes, a warehouse mobile app, see `05-warehouse-mobile-app.md`; devices, network and labels still to answer)
- [ ] E-invoice and e-way bill: direct NIC API or via a GSP
- [ ] Who validates posting rules: you alone, or with your CA per module
- [ ] Budget for running costs (server, backups, GSP fees)
- [ ] **(new)** Do you do job work (send material out for processing, or process for others)? Decides ITC-04 and job work challans (Processing customers' material: yes, 9 Nov, see `05-warehouse-mobile-app.md`; sending out still to confirm)
- [ ] **(new)** Any exports or foreign-currency purchases? Decides multi-currency in v1
- [ ] **(new)** Are products FSSAI-licensed and organic-certified? Decides batch traceability depth and label formats
- [ ] **(new)** How many users per role, and real yearly volumes (invoices, GRNs, items)?
- [ ] **(new)** Does either company have more than one GSTIN (another state)?
- [ ] **(new)** Target cutover date, so the roadmap can be dated

* [ ] **(new)** How many employees in each company, and are any paid daily or through a labour contractor?
* [ ] **(new)** Which states do staff work in? This decides professional tax and labour welfare fund rules
* [ ] **(new)** Do you need attendance from a biometric device, or entered by hand? (Biometric: yes, see `04-biometric-attendance.md`)
* [ ] **(new)** List of current lenders and loans (secured and unsecured), including loans from directors and partners
* [ ] **(new)** Fixed asset register today: in ERPNext, in Excel, or with your CA only?

- [ ] **(new)** Monthly budget for AI usage, and which features to switch on first (bill capture is the suggested first one)
- [ ] **(new)** Are you comfortable sending supplier bills and expense receipts to an AI provider outside India, with no training on the data? Check with your CA and legal adviser for any data-residency concerns
- [ ] **(new)** 50 to 100 real supplier bills and bank statements to build the accuracy test set

* [ ] **(new)** Which entity will own and sell MyERP as SaaS: one of the two companies, or a new one?
* [ ] **(new)** Product name and web domain for the SaaS version (apurvam.myerp.in is a placeholder)
* [ ] **(new)** Which customisations should tenants be able to make themselves, and which only your team on request?
