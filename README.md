# MyERP

Apurvam's own web ERP: accounts, stock, purchase, sales, production, GST/TDS, fixed assets, loans and payroll. Built multi-tenant from day one so it can later be offered as SaaS: each customer (a group of companies) gets its own database and users.

- Plan and design rules: [docs/specs/00-architecture-and-roadmap.md](docs/specs/00-architecture-and-roadmap.md)
- Decisions: [docs/decisions/](docs/decisions/)
- Current phase: [Phase 0](docs/specs/02-phase0-setup.md)

## Run it locally

With Docker:

```sh
docker compose up -d db redis
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py create_tenant apurvam "Apurvam group"
docker compose up
```

Then open http://apurvam.localhost:5173 (browsers resolve `*.localhost` to your machine).

Without Docker (PostgreSQL 16 and Redis installed locally):

```sh
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py migrate                      # platform database
.venv/bin/python manage.py create_tenant apurvam "Apurvam group"
.venv/bin/python manage.py runserver
curl -H 'Host: apurvam.localhost' localhost:8000/api/whoami/

cd ../frontend && npm ci && npm run dev                  # http://apurvam.localhost:5173
```

## Tests

```sh
cd backend && .venv/bin/pytest
```

The tests create two real tenant databases and check that neither can see the other's data.
