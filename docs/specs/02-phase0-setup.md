# Phase 0 spec: setup and multi-tenant foundation

Goal: a repo, CI and a running skeleton that every later module builds on, with tenant isolation (rule 16) proven by tests from day one.

## In this first pull request

- [x] Django 5.2 backend with a platform database (`default`) and one database per tenant
- [x] `tenancy` app: `Tenant` model, subdomain resolver middleware, database router, `use_tenant` context, `tenant_task` helper for Celery jobs
- [x] Commands: `create_tenant <slug> <name>` (creates the database and runs tenant migrations) and `migrate_tenants` (oldest tenant first, so Apurvam is the pilot)
- [x] `core.Company` as the first tenant-side model; `GET /api/whoami/` shows the tenant and its companies; `GET /api/health/` needs no tenant
- [x] Isolation tests against real PostgreSQL: tenant A never sees tenant B, no tenant = error, platform and tenant tables never mix, unknown or suspended tenant = 404
- [x] React + TypeScript (Vite) shell that calls `/api/whoami/`
- [x] Docker Compose for local development; GitHub Actions CI (lint, migration check, tests, frontend build)

## Still to do in Phase 0 (next pull requests)

- [ ] Staging on Google Cloud (Terraform for Cloud Run, Cloud SQL, Memorystore, Storage, Secret Manager, wildcard certificate), deploy on every merge to main
- [ ] Nightly backups plus point-in-time recovery, and a scripted restore drill
- [ ] Error alerts (Sentry)
- [ ] Login with TOTP two-factor for admin and submit roles (tenant-side users)
- [ ] PgBouncer / connection limits per tenant

## Gate

Every merge deploys to staging; a restore drill passes; an automated test proves tenant B cannot see tenant A.
