terraform {
  required_version = ">= 1.9"

  required_providers {
    # 7.25 or later: the database's data_api_access setting (main.tf).
    google = {
      source  = "hashicorp/google"
      version = "~> 7.25"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Bucket is set per environment at init:
  #   terraform init -backend-config="bucket=myerp-staging-tfstate"
  backend "gcs" {
    prefix = "myerp"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
