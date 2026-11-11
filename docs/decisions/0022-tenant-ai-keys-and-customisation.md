# 0022. Each tenant brings its own AI key; AI customises only tenant data

Date: 11 Nov 2026. Asked by Sidharth: "Each tenant to have their own api key from which ever AI they choose to give them suggestions they ask for. The main system cannot be touched. They can make print reports, or screen reports etc or add fields so on in their own database."

## Decision

- MyERP holds no shared AI key. Each tenant chooses its AI provider and enters its own API key on an Owner-only "AI settings" screen. The key is stored encrypted in the tenant's database (master key in Secret Manager), shown only as its last 4 characters, and used only by the backend for that tenant. No key means AI is off.
- MyERP talks to providers through one adapter per provider. Tools, permissions, the read-only rule, limits and logging are the same for every provider.
- AI may draft only a tenant's own customisations, stored as data in the tenant's database: screen reports, print formats, custom fields, and later dashboards and rules. Each kind needs its own permission (`reports.build`, `printformats.manage`, `customfields.manage`; Owner by default, given to other roles by the Owner), and a person holding it previews and activates each one; every customisation is versioned and can be turned off.
- AI never changes MyERP's code, standard screens, reports or print formats, posting rules, ledgers, tax rates, other tenants or the platform. Decision 0006 (AI drafts, never posts) stands; customisation drafts are one more kind of draft.
- Standard reports, print formats and screens are changed only by the MyERP super admin (the owner of MyERP, platform side) and ship in a release. Tenants, including a tenant's Owner, can only "Save as copy" and change the copy (Sidharth, 11 Nov).

Spec: [05-ai-assistant.md](../specs/05-ai-assistant.md).
