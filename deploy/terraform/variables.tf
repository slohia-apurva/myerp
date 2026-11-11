variable "project_id" {
  description = "Google Cloud project, e.g. myerp-staging"
  type        = string
}

variable "environment" {
  description = "staging or prod"
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be staging or prod."
  }
}

variable "region" {
  description = "Mumbai keeps all data in India"
  type        = string
  default     = "asia-south1"
}

variable "db_tier" {
  description = "Cloud SQL machine type"
  type        = string
  default     = "db-custom-1-3840"
}

variable "db_high_availability" {
  description = "Standby in a second zone (prod only; doubles the database cost)"
  type        = bool
  default     = false
}

variable "allowed_hosts" {
  description = "Host names Django accepts, comma separated (the Cloud Run URL until a domain is set)"
  type        = string
  default     = ".run.app"
}

variable "base_domain" {
  description = "Tenants are reached at <tenant>.<base_domain>; a placeholder until the domain is registered"
  type        = string
  default     = "myerp.invalid"
}

variable "runtime_service_account" {
  description = "Created by deploy/gcp/bootstrap.sh"
  type        = string
}

variable "fallback_tenant" {
  description = "Tenant served on hosts with no tenant subdomain. Staging only, until a domain is set; leave empty in prod."
  type        = string
  default     = ""
}

variable "google_client_id" {
  description = "OAuth client id for Sign in with Google (APIs & Services > Credentials). Not a secret. Empty until created; sign-in then says it is not set up."
  type        = string
  default     = ""
}

variable "allow_data_reset" {
  description = "Let an Owner use Admin > Reset data. For staging and trial runs; keep false for live books."
  type        = bool
  default     = false
}
