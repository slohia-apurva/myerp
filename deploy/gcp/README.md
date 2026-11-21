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

6. **Read-only access for Claude (staging only, once).** Lets Claude sessions check entries and reports themselves. Terraform (with `claude_reader = true`, set in `staging.tfvars`) makes a service account `claude-reader` that may read the database and the logs and nothing else: its database login gets SELECT only, never sign-in sessions (`backend/tenancy/reader.py`), and it reaches the database through Google's Cloud SQL Data API, so the database keeps its private address. Its key never goes into this repository, which is public. In Cloud Shell, as an Owner:

   1. Bring the code up to date and apply. `-upgrade` is needed once, because this change moves the Google provider to version 7. The plan should *add* the `claude-reader` account, its three roles and its database login, and *change* the database instance in place (Data API on, IAM sign-in flag on); it must destroy nothing. If it wants to destroy or replace anything, stop and ask.

      ```sh
      cd ~/myerp && git pull && cd deploy/terraform
      terraform init -upgrade -backend-config="bucket=myerp-staging-tfstate"
      terraform plan  -var-file=environments/staging.tfvars
      terraform apply -var-file=environments/staging.tfvars
      ```

   2. Grant the new login read access to every database (each deploy repeats this from now on):

      ```sh
      gcloud run jobs execute myerp-migrate --project myerp-staging --region asia-south1 --wait
      ```

   3. Make the key, print it as one line, then delete the file:

      ```sh
      gcloud iam service-accounts keys create ~/claude-reader.json --project myerp-staging \
        --iam-account=claude-reader@myerp-staging.iam.gserviceaccount.com
      base64 -w0 ~/claude-reader.json; echo
      rm ~/claude-reader.json
      ```

      If Google refuses with "Key creation is not allowed on this service account" (an organisation policy, on by default for new organisations), an organisation admin turns it off for this project only and you run step 3 again: `gcloud resource-manager org-policies disable-enforce iam.disableServiceAccountKeyCreation --project=myerp-staging`.

   4. Copy the long line and add it in claude.ai: the MyERP project's settings, **Cloud environment**, the gear beside the environment, **Environment variables**, as `MYERP_STAGING_READER_KEY=<the line>`. New Claude sessions pick it up. Never paste it into a chat, a file in this repository, or an issue.

   To take the access away at any time: *IAM & Admin > Service accounts > claude-reader > Keys*, delete the key (or disable the account). To remove it completely, set `claude_reader = false` and apply.

7. **Scheduled work (once per project, then nothing).** Terraform makes a Cloud Run job `myerp-scheduled` (`manage.py run_scheduled`) and a Cloud Scheduler job `myerp-hourly` that starts it every hour (India time), signed in as the `myerp-scheduler` service account, which may only start that job. Each piece of scheduled work checks for itself whether it is due; the first is the daily Stock Check (on per company, on the Stock Check screen). Deploys swap the job's image like the migration job's, and skip it until the first `terraform apply` has made it. If the apply says the Cloud Scheduler API is off, wait a minute and apply again.

Not yet created, to keep staging cheap until they are needed: Memorystore (Redis) and the Celery worker (first background jobs arrive in Phase 2/3), and the load balancer with a wildcard certificate (needs the domain).
