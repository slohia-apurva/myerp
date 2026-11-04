# Google Cloud setup

Start with `myerp-staging`; repeat for `myerp-prod` once staging passes the Phase 0 gate.

1. **Bootstrap (once per project).** In Cloud Shell, as an Owner: `bash deploy/gcp/bootstrap.sh myerp-staging`. Turns on services, creates the Terraform state bucket, the `myerp-deployer` and `myerp-runtime` service accounts, and keyless GitHub Actions access (main branch of this repo only). Costs nothing.
2. **Infrastructure (Terraform, run by an Owner).** Cloud Shell no longer ships Terraform; install 1.12.2 once into `~/bin` (it survives Cloud Shell restarts):

   ```sh
   mkdir -p ~/bin && cd /tmp && curl -sSLO https://releases.hashicorp.com/terraform/1.12.2/terraform_1.12.2_linux_amd64.zip \
     && unzip -o terraform_1.12.2_linux_amd64.zip -d ~/bin && export PATH="$HOME/bin:$PATH" && terraform version
   ```

   Then, from the repo:

   ```sh
   cd deploy/terraform
   terraform init -backend-config="bucket=myerp-staging-tfstate"
   terraform plan  -var-file=environments/staging.tfvars
   terraform apply -var-file=environments/staging.tfvars
   ```

   Creates: VPC with private service access, Cloud SQL PostgreSQL 16 (private IP only, nightly backups kept 14 days, 7 days point-in-time recovery), Secret Manager secrets, Artifact Registry, a files bucket, the Cloud Run service `myerp-app` and the migration job `myerp-migrate` (both on a placeholder image until CI deploys).
3. **Deploys (GitHub Actions).** On every merge to main: build the image, push it, run `myerp-migrate` (`manage.py deploy_migrate`), roll out `myerp-app`.
4. **Users.** There is no sign-up page. An Owner creates each user from Cloud Shell by running the migration job with other arguments, then reads the one-time password link from its log:

   ```sh
   gcloud run jobs execute myerp-migrate --project myerp-staging --region asia-south1 --wait \
     --args=manage.py,create_tenant_user,apurvam,USERNAME,--first-name=FIRST,--email=EMAIL
   gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="myerp-migrate" AND textPayload:"Password link"' \
     --project myerp-staging --limit 1 --format='value(textPayload)'
   ```

   Put the app address in front of the printed `/#set-password/...` path and open it within 24 hours. The link works once. The user chooses a password, logs in, and sets up an authenticator app (required for everyone). For a forgotten password or a lost phone, run the same command with `--reset` added.

Not yet created, to keep staging cheap until they are needed: Memorystore (Redis) and the Celery worker (first background jobs arrive in Phase 2/3), and the load balancer with a wildcard certificate (needs the domain).
