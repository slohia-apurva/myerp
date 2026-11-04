# Google Cloud setup

1. `bootstrap.sh <project-id>`: one-time, run in Cloud Shell by a project Owner. Turns on services, creates the Terraform state bucket, the deployer and runtime service accounts, and keyless GitHub Actions access (main branch of this repo only). Creates nothing that costs money.
2. Terraform (next): Cloud SQL, Cloud Run, Memorystore, Artifact Registry, Storage, Secret Manager, run by an Owner.
3. GitHub Actions (next): build and deploy to staging on every merge to main.

Start with `myerp-staging`; run the same steps for `myerp-prod` once staging passes the Phase 0 gate.
