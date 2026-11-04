# Google Cloud setup

Start with `myerp-staging`; repeat for `myerp-prod` once staging passes the Phase 0 gate.

1. **Bootstrap (once per project).** In Cloud Shell, as an Owner: `bash deploy/gcp/bootstrap.sh myerp-staging`. Turns on services, creates the Terraform state bucket, the `myerp-deployer` and `myerp-runtime` service accounts, and keyless GitHub Actions access (main branch of this repo only). Costs nothing.
2. **Infrastructure (Terraform, run by an Owner).** In Cloud Shell:

   ```sh
   cd deploy/terraform
   terraform init -backend-config="bucket=myerp-staging-tfstate"
   terraform plan  -var-file=environments/staging.tfvars
   terraform apply -var-file=environments/staging.tfvars
   ```

   Creates: VPC with private service access, Cloud SQL PostgreSQL 16 (private IP only, nightly backups kept 14 days, 7 days point-in-time recovery), Secret Manager secrets, Artifact Registry, a files bucket, the Cloud Run service `myerp-app` and the migration job `myerp-migrate` (both on a placeholder image until CI deploys).
3. **Deploys (GitHub Actions, next PR).** On every merge to main: build the image, push it, run `myerp-migrate`, roll out `myerp-app`.

Not yet created, to keep staging cheap until they are needed: Memorystore (Redis) and the Celery worker (first background jobs arrive in Phase 2/3), and the load balancer with a wildcard certificate (needs the domain).
