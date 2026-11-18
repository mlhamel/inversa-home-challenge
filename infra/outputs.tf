output "web_api_url" {
  description = "Public URL of the FastAPI + FastMCP + DuckDB service."
  value       = google_cloud_run_v2_service.web_api.uri
}

output "web_ui_url" {
  description = "Public URL of the map / timeline / chat demo (shareable demo URL)."
  value       = google_cloud_run_v2_service.web_ui.uri
}

output "datalake_bucket" {
  description = "GCS bucket backing /mnt/data on web-api and the ingestion job."
  value       = google_storage_bucket.datalake.name
}

output "ingestion_job_name" {
  description = "Cloud Run job refreshed by the `0 */2 * * *` Cloud Scheduler job."
  value       = google_cloud_run_v2_job.ingestion.name
}
