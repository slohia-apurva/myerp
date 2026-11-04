# 0004 Hosting: Google Cloud, Mumbai region (leaning, not final)

- Status: proposed, 4 Nov 2026
- Proposal: Cloud Run (app), Cloud SQL for PostgreSQL (one database per tenant), Memorystore (Redis), a small VM for Celery workers, Cloud Storage (Mumbai, copy in Delhi), Secret Manager, load balancer with a wildcard certificate for tenant subdomains. All data stays in India.
- Fallback: Docker Compose on a Mumbai VPS (cheaper, but we own patching and backups).
- Open: Google Cloud account and billing, domain name.
