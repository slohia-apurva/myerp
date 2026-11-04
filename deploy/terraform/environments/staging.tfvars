# No domain yet: fallback_tenant serves the Apurvam tenant on the Cloud Run URL.
project_id              = "myerp-staging"
environment             = "staging"
db_tier                 = "db-custom-1-3840"
db_high_availability    = false
runtime_service_account = "myerp-runtime@myerp-staging.iam.gserviceaccount.com"
fallback_tenant         = "apurvam"
