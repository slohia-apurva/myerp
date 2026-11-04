terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.30"
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
