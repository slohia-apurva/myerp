# 0003 SaaS-ready: one database per tenant

- Status: decided, 4 Nov 2026 (Sidharth asked for each group of companies to have its own database and users)
- Decision: a tenant is a group of companies. Each tenant has its own PostgreSQL database holding its users, companies, masters, ledgers and customisations. A platform database holds the tenant list and (later) plans and billing. Global masters are maintained once and copied read-only into every tenant database.
- How: `tenancy.middleware.TenantMiddleware` picks the tenant from the subdomain; `tenancy.router.TenantRouter` sends tenant models to that tenant's database and raises `NoTenantSelected` if none is selected. Jobs and commands use `tenancy.context.use_tenant`.
- Rules: 16 tenant isolation (tested in `backend/tests/test_tenancy.py`), 17 global masters read-only to tenants, 18 no tenant-specific code.
- Trade-off: strongest isolation and simple per-tenant backup/restore, at the cost of one connection pool per tenant (PgBouncer later). Revisit if tenants number in the hundreds.
- Note: the platform-side app is called `tenancy`, not `platform`, because `platform` is a Python standard-library module.
