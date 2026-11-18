output "web_api_url" {
  description = "URL of the FastAPI + FastMCP + DuckDB service (IAM-only: callers need roles/run.invoker and a web_sa identity token)."
  value       = google_cloud_run_v2_service.web_api.uri
}

output "web_ui_url" {
  description = "Shareable demo URL (basic-auth gated; password is the WEB_UI_HTPASSWD demo credential)."
  value       = google_cloud_run_v2_service.web_ui.uri
}

output "datalake_bucket" {
  description = "GCS bucket backing /mnt/data on web-api and the ingestion job."
  value       = google_storage_bucket.datalake.name
}

output "ingestion_job_name" {
  description = "Cloud Run job refreshed by the `0 */2 * * *` scheduler and deploy runs."
  value       = google_cloud_run_v2_job.ingestion.name
}
