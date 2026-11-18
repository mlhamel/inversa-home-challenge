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
    "web-ui-htpasswd" = {
      env_key     = "WEB_UI_HTPASSWD"
      consumed_by = "web_ui"
      enabled     = true
    }
    "web-ui-nginx-conf" = {
      env_key     = "WEB_UI_NGINX_CONF"
      consumed_by = "web_ui"
      enabled     = true
    }
  }
  secret_meta_enabled = { for name, m in local.secret_meta : name => m if m.enabled }

  secret_consumers = {
    web_api   = google_service_account.api_sa.email
    web_ui    = google_service_account.web_sa.email
    ingestion = google_service_account.ingestion_sa.email
  }

  secret_values = {
    "firms-map-key"     = var.firms_map_key
    "openaq-api-key"    = var.openaq_api_key
    "agent-api-key"     = var.agent_api_key
    "web-ui-htpasswd"   = var.web_ui_htpasswd
    "web-ui-nginx-conf" = local.web_ui_nginx_conf
  }

  web_ui_nginx_conf = <<-EOT
    server {
      listen 8080;

      location = /healthz {
        access_log off;
        return 200 "ok";
      }

      location / {
        auth_basic "Inversa demo";
        auth_basic_user_file /etc/nginx/secrets/.htpasswd;

        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;

        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
      }
    }
  EOT
}
