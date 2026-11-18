locals {
  web_api_name    = "web-api"
  web_ui_name     = "web-ui"
  ingestion_job   = "ingestion-job"
  datalake_bucket = "${var.project_id}-datalake"
  artifact_url    = "${var.region}-docker.pkg.dev/${var.project_id}/inversa"
  backend_image   = var.backend_image != "" ? var.backend_image : "${local.artifact_url}/backend:latest"
  frontend_image  = var.frontend_image != "" ? var.frontend_image : "${local.artifact_url}/frontend:latest"
  ingestion_image = var.ingestion_image != "" ? var.ingestion_image : "${local.artifact_url}/ingestion:latest"
  apis = toset([
    "run.googleapis.com",
    "storage.googleapis.com",
    "storage-component.googleapis.com",
    "cloudscheduler.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  secret_meta = {
    "firms-map-key" = {
      env_key     = "FIRMS_MAP_KEY"
      consumed_by = "ingestion"
      enabled     = nonsensitive(var.firms_map_key != "")
    }
    "openaq-api-key" = {
      env_key     = "OPENAQ_API_KEY"
      consumed_by = "ingestion"
      enabled     = nonsensitive(var.openaq_api_key != "")
    }
    "agent-api-key" = {
      env_key     = "AGENT_API_KEY"
      consumed_by = "web_api"
      enabled     = nonsensitive(var.agent_api_key != "")
    }
  }
  secret_meta_enabled = { for name, m in local.secret_meta : name => m if m.enabled }
  secret_values = {
    "firms-map-key"  = var.firms_map_key
    "openaq-api-key" = var.openaq_api_key
    "agent-api-key"  = var.agent_api_key
  }
}
