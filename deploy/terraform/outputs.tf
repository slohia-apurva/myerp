output "app_url" {
  description = "Cloud Run URL of the app"
  value       = google_cloud_run_v2_service.app.uri
}

output "image_repository" {
  description = "Where CI pushes images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "database_instance" {
  value = google_sql_database_instance.main.connection_name
}

output "migrate_job" {
  value = google_cloud_run_v2_job.migrate.name
}

output "claude_reader" {
  description = "Service account whose key goes into the Claude environment settings"
  value       = var.claude_reader ? google_service_account.claude_reader[0].email : ""
}
