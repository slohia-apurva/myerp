# MyERP infrastructure for one environment (staging or prod).
#
# Run by a project Owner from Cloud Shell:
#   cd deploy/terraform
#   terraform init -backend-config="bucket=myerp-staging-tfstate"
#   terraform apply -var-file=environments/staging.tfvars
#
# GitHub Actions only swaps the container image on the service and the
# migration job; everything else changes here, through a pull request.

locals {
  name = "myerp-${var.environment}"

  # Non-secret settings for the app (see backend/config/settings.py).
  plain_env = {
    DJANGO_DEBUG           = "0"
    DJANGO_ALLOWED_HOSTS   = var.allowed_hosts
    MYERP_BASE_DOMAIN      = var.base_domain
    MYERP_FALLBACK_TENANT  = var.fallback_tenant
    MYERP_FILES_BUCKET     = google_storage_bucket.files.name
    MYERP_GOOGLE_CLIENT_ID = var.google_client_id
    # The Owner's "Reset data" tool: off unless an environment turns it on.
    MYERP_ALLOW_DATA_RESET = var.allow_data_reset ? "1" : "0"
    # Each deploy grants this login SELECT on every database (tenancy/reader.py).
    MYERP_READER_DB_USER = local.reader_db_user
  }

  # Cloud SQL names a service account's database login by its email without
  # ".gserviceaccount.com". Empty when there is no reader.
  reader_db_user = var.claude_reader ? trimsuffix(google_service_account.claude_reader[0].email, ".gserviceaccount.com") : ""

  # Secrets, read by Cloud Run from Secret Manager at start-up.
  secret_env = {
    DJANGO_SECRET_KEY     = google_secret_manager_secret.django_secret_key.secret_id
    PLATFORM_DATABASE_URL = google_secret_manager_secret.platform_database_url.secret_id
    GSTINAPI_KEY          = data.google_secret_manager_secret.gstinapi_key.secret_id
    MYERP_SECRETS_KEY     = google_secret_manager_secret.secrets_key.secret_id
    # Sign-in emails of MyERP platform admins, who alone see the Central menu.
    MYERP_PLATFORM_ADMINS = data.google_secret_manager_secret.platform_admins.secret_id
  }

  # Cloud Run needs an image to create the service; CI replaces it on deploy.
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"
}

# ---------------------------------------------------------------- network

resource "google_compute_network" "vpc" {
  name                    = "myerp-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "app" {
  name                     = "myerp-app"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

# Private range for Google-managed services (Cloud SQL, later Memorystore).
resource "google_compute_global_address" "private_services" {
  name          = "myerp-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

# ---------------------------------------------------------------- database

resource "google_sql_database_instance" "main" {
  name                = local.name
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = true

  depends_on = [google_service_networking_connection.private_services]

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = var.db_high_availability ? "REGIONAL" : "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = true

    # Private IP only: the database is not reachable from the internet.
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    # Nightly backup at 02:00 IST, 14 kept, plus 7 days of point-in-time recovery.
    backup_configuration {
      enabled                        = true
      start_time                     = "20:30"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      location                       = var.region

      backup_retention_settings {
        retained_backups = 14
      }
    }

    # Sunday 21:00 UTC = Monday 02:30 IST.
    maintenance_window {
      day  = 7
      hour = 21
    }

    insights_config {
      query_insights_enabled = true
    }

    # Read-only checks by the claude-reader service account (below) go through
    # Google's Cloud SQL Data API over HTTPS, as that account's own login: the
    # database stays on its private address, with no public IP.
    data_api_access = var.claude_reader ? "ALLOW_DATA_API" : "DISALLOW_DATA_API"

    dynamic "database_flags" {
      for_each = var.claude_reader ? [1] : []
      content {
        name  = "cloudsql.iam_authentication"
        value = "on"
      }
    }
  }
}

resource "random_password" "db" {
  length  = 32
  special = false
}

# Cloud SQL users created this way may CREATE DATABASE, which tenant
# provisioning needs (one database per tenant).
resource "google_sql_user" "app" {
  name     = "myerp"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

# ---------------------------------------------------------------- read-only access
# The claude-reader service account lets Claude sessions check entries and
# reports. Its key is made once by an Owner and kept in the Claude environment
# settings, never in this public repository (deploy/gcp/README.md). It can:
#   - run SQL through the Data API as its own database login, which each deploy
#     grants SELECT only, and no sign-in sessions (tenancy/reader.py);
#   - see the database instance's settings and read the logs.
# It cannot change data, read secrets or files, or deploy.

resource "google_service_account" "claude_reader" {
  count        = var.claude_reader ? 1 : 0
  account_id   = "claude-reader"
  display_name = "Claude read-only (checks entries; never changes data)"
}

resource "google_project_iam_member" "claude_reader" {
  for_each = var.claude_reader ? toset([
    "roles/cloudsql.instanceUser", # sign in to the database and run SQL by the Data API
    "roles/cloudsql.viewer",       # see the instance and its databases
    "roles/logging.viewer",        # read the app's logs, to look into errors
  ]) : toset([])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.claude_reader[0].email}"
}

resource "google_sql_user" "claude_reader" {
  count    = var.claude_reader ? 1 : 0
  name     = local.reader_db_user
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_sql_database" "platform" {
  name     = "myerp_platform"
  instance = google_sql_database_instance.main.name
}

# ---------------------------------------------------------------- secrets
# Values also sit in the Terraform state bucket, which only Owners can read.

resource "random_password" "django_secret_key" {
  length  = 50
  special = false
}

resource "google_secret_manager_secret" "django_secret_key" {
  secret_id = "django-secret-key"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "django_secret_key" {
  secret      = google_secret_manager_secret.django_secret_key.id
  secret_data = random_password.django_secret_key.result
}

# The key that locks customers' API secrets (core/secrets.py): a Fernet key,
# which is 32 random bytes as URL-safe base64 with its "=" padding. It must
# never change once secrets are saved with it: a new key cannot read them.
resource "random_id" "secrets_key" {
  byte_length = 32
}

resource "google_secret_manager_secret" "secrets_key" {
  secret_id = "secrets-key"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "secrets_key" {
  secret      = google_secret_manager_secret.secrets_key.id
  secret_data = "${random_id.secrets_key.b64_url}="
}

# The gstinapi.in key is created by hand in the console (never in code or
# state); Terraform only points Cloud Run at it and must not read its value.
data "google_secret_manager_secret" "gstinapi_key" {
  secret_id = "gstinapi-key"
}

# The platform admins' sign-in emails (comma separated), also kept by hand in
# Secret Manager: the repository is public, so the emails cannot sit in a
# tfvars file, and a Terraform variable left empty on an apply wiped the
# Central menu (16 Nov 2026). Create it once per project, before applying:
#   printf '%s' 'you@example.com' | gcloud secrets create platform-admins \
#     --replication-policy=user-managed --locations=asia-south1 --data-file=-
# and change it later with `gcloud secrets versions add platform-admins`
# followed by a new Cloud Run revision.
data "google_secret_manager_secret" "platform_admins" {
  secret_id = "platform-admins"
}

resource "google_secret_manager_secret" "platform_database_url" {
  secret_id = "platform-database-url"
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "platform_database_url" {
  secret = google_secret_manager_secret.platform_database_url.id
  secret_data = format(
    "postgres://%s:%s@%s:5432/%s",
    google_sql_user.app.name,
    random_password.db.result,
    google_sql_database_instance.main.private_ip_address,
    google_sql_database.platform.name,
  )
}

# ---------------------------------------------------------------- storage

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "myerp"
  format        = "DOCKER"
  description   = "MyERP container images"
}

resource "google_storage_bucket" "files" {
  name                        = "${var.project_id}-files"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket_iam_member" "runtime_files" {
  bucket = google_storage_bucket.files.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.runtime_service_account}"
}

# ---------------------------------------------------------------- app

resource "google_cloud_run_v2_service" "app" {
  name     = "myerp-app"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  # The app does its own login; no Google sign-in in front of it. This also
  # avoids granting allUsers, which the organisation's policy may forbid.
  invoker_iam_disabled = true

  template {
    service_account = var.runtime_service_account

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.app.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = local.placeholder_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }

        cpu_idle = true

        # Full CPU while the instance starts, so Django is imported quickly: a
        # person who wakes a sleeping instance waited 6.5 seconds on the median
        # (198 instance starts in the week to 2026-11-25). Charged only for the
        # startup, not while the instance runs.
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.plain_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_secret_manager_secret_version.django_secret_key,
    google_secret_manager_secret_version.platform_database_url,
    google_secret_manager_secret_version.secrets_key,
  ]
}

# Runs platform and tenant migrations; CI executes it before each rollout.
resource "google_cloud_run_v2_job" "migrate" {
  name     = "myerp-migrate"
  location = var.region

  template {
    task_count = 1

    template {
      service_account = var.runtime_service_account
      max_retries     = 0
      timeout         = "900s"

      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.app.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = local.placeholder_image

        # Admin commands reuse this job by overriding the arguments, e.g.
        #   gcloud run jobs execute myerp-migrate --args=manage.py,create_tenant_user,apurvam,NAME
        command = ["python"]
        args    = ["manage.py", "deploy_migrate"]

        dynamic "env" {
          for_each = local.plain_env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = local.secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_secret_manager_secret_version.django_secret_key,
    google_secret_manager_secret_version.platform_database_url,
    google_secret_manager_secret_version.secrets_key,
  ]
}

# ---------------------------------------------------------------- scheduled work

# Scheduled work (manage.py run_scheduled), started every hour by Cloud
# Scheduler below; each piece decides for itself whether it is due. Now: the
# daily Stock Check. CI swaps its image on each deploy, as for the migrations.
resource "google_cloud_run_v2_job" "scheduled" {
  name     = "myerp-scheduled"
  location = var.region

  template {
    task_count = 1

    template {
      service_account = var.runtime_service_account
      max_retries     = 0
      timeout         = "600s"

      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.app.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = local.placeholder_image

        command = ["python"]
        args    = ["manage.py", "run_scheduled"]

        dynamic "env" {
          for_each = local.plain_env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = local.secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_secret_manager_secret_version.django_secret_key,
    google_secret_manager_secret_version.platform_database_url,
    google_secret_manager_secret_version.secrets_key,
  ]
}

resource "google_project_service" "scheduler" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

# Cloud Scheduler signs in as this account, which may only start the job above.
resource "google_service_account" "scheduler" {
  account_id   = "myerp-scheduler"
  display_name = "MyERP hourly scheduler"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_runs_job" {
  name     = google_cloud_run_v2_job.scheduled.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "hourly" {
  name      = "myerp-hourly"
  region    = var.region
  schedule  = "0 * * * *"
  time_zone = "Asia/Kolkata"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/${google_cloud_run_v2_job.scheduled.id}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.scheduler,
    google_cloud_run_v2_job_iam_member.scheduler_runs_job,
  ]
}
