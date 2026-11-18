# No domain yet: fallback_tenant serves the Apurvam tenant on the Cloud Run URL.
project_id              = "myerp-staging"
environment             = "staging"
db_tier                 = "db-custom-1-3840"
db_high_availability    = false
runtime_service_account = "myerp-runtime@myerp-staging.iam.gserviceaccount.com"
fallback_tenant         = "apurvam"
# Sign in with Google (OAuth client "MyERP staging"; not a secret).
google_client_id = "255819525378-jv4ptq7n0cdr95rpvqtroauk1m57f4rk.apps.googleusercontent.com"
# Read-only service account for Claude sessions to check entries (main.tf).
claude_reader = true
