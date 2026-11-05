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
4. **Google sign-in (once per project).** People sign in with their Google account; MyERP keeps no passwords. In the Cloud console for the project:
   1. *Google Auth Platform > Branding*: app name "MyERP", support email. *Audience*: **External**, then **Publish app** (Internal would admit only apurva.org.in accounts). MyERP asks only for name and email, so publishing needs no Google review.
   2. *Clients > Create client*: type **Web application**, name "MyERP staging". Under *Authorised JavaScript origins* add the app address (staging: `https://myerp-app-fzeilr5lpa-el.a.run.app`) and, for local development, `http://localhost:5173` and `http://localhost`. No redirect URIs are needed.
   3. Put the client id (ends in `.apps.googleusercontent.com`; not a secret) in `environments/staging.tfvars` as `google_client_id`, merge, and run `terraform apply` again.
5. **Users.** There is no sign-up page. An Owner adds people on the **Users** screen in MyERP. Only a new tenant's first Owner is added from Cloud Shell, reusing the migration job:

   ```sh
   gcloud run jobs execute myerp-migrate --project myerp-staging --region asia-south1 --wait \
     --args=manage.py,create_tenant_user,TENANT,PERSON@example.com,--name=FULL_NAME,--role=owner
   ```

   They can then sign in with that Google account. Add `--deactivate` to remove someone's access.

Not yet created, to keep staging cheap until they are needed: Memorystore (Redis) and the Celery worker (first background jobs arrive in Phase 2/3), and the load balancer with a wildcard certificate (needs the domain).
