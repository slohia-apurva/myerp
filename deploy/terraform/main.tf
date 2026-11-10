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
  }

  # Secrets, read by Cloud Run from Secret Manager at start-up.
  secret_env = {
    DJANGO_SECRET_KEY     = google_secret_manager_secret.django_secret_key.secret_id
    PLATFORM_DATABASE_URL = google_secret_manager_secret.platform_database_url.secret_id
    GSTINAPI_KEY          = data.google_secret_manager_secret.gstinapi_key.secret_id
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

# The gstinapi.in key is created by hand in the console (never in code or
# state); Terraform only points Cloud Run at it and must not read its value.
data "google_secret_manager_secret" "gstinapi_key" {
  secret_id = "gstinapi-key"
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
  ]
}
