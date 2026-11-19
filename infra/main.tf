resource "google_project_service" "enabled" {
  for_each = local.apis

  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "datalake" {
  name          = local.datalake_bucket
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled["storage.googleapis.com"]]
}

resource "google_service_account" "api_sa" {
  account_id   = "inversa-api"
  display_name = "Inversa web-api runtime"
}

resource "google_service_account" "ingestion_sa" {
  account_id   = "inversa-ingestion"
  display_name = "Inversa ingestion-job runtime (scheduler-invoked)"
}

resource "google_service_account" "web_sa" {
  account_id   = "inversa-web"
  display_name = "Inversa web-ui runtime"
}

resource "google_storage_bucket_iam_member" "web_api_object_viewer" {
  bucket = google_storage_bucket.datalake.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.api_sa.email}"
}

resource "google_storage_bucket_iam_member" "ingestion_object_admin" {
  bucket = google_storage_bucket.datalake.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ingestion_sa.email}"
}

resource "google_secret_manager_secret" "app_secrets" {
  for_each = local.secret_meta_enabled

  secret_id = each.key

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled["secretmanager.googleapis.com"]]
}

resource "google_secret_manager_secret_version" "app_secret_versions" {
  for_each = local.secret_meta_enabled

  secret      = google_secret_manager_secret.app_secrets[each.key].id
  secret_data = local.secret_values[each.key]
}

resource "google_secret_manager_secret_iam_member" "consumers" {
  for_each = local.secret_meta_enabled

  secret_id = google_secret_manager_secret.app_secrets[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.secret_consumers[each.value.consumed_by]}"
}

resource "google_cloud_run_v2_service" "web_api" {
  name     = local.web_api_name
  location = var.region

  deletion_protection = false

  template {
    service_account = google_service_account.api_sa.email

    volumes {
      name = "datalake"
      gcs {
        bucket    = google_storage_bucket.datalake.name
        read_only = true
      }
    }

    containers {
      image = local.backend_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "DATA_DIR"
        value = "/mnt/data"
      }

      env {
        name  = "REGION_CALIFORNIA"
        value = var.bbox
      }

      env {
        name  = "REGION_NW_INDIA"
        value = var.nw_india_bbox
      }

      env {
        name  = "REGION_NW_INDIA_LABEL"
        value = "Punjab–Haryana–Delhi NCR"
      }

      env {
        name  = "AGENT_MODEL"
        value = var.agent_model
      }

      env {
        name  = "AGENT_BASE_URL"
        value = var.agent_base_url
      }

      dynamic "env" {
        for_each = {
          for name, m in local.secret_meta_enabled : m.env_key => name
          if m.consumed_by == "web_api"
        }
        content {
          name = env.key

          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app_secrets[env.value].id
              version = "latest"
            }
          }
        }
      }

      volume_mounts {
        name       = "datalake"
        mount_path = "/mnt/data"
      }
    }
  }

  depends_on = [
    google_project_service.enabled["run.googleapis.com"],
    google_project_service.enabled["storage-component.googleapis.com"],
    google_secret_manager_secret_iam_member.consumers,
    google_secret_manager_secret_version.app_secret_versions,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "web_api_ui_invoker" {
  name     = google_cloud_run_v2_service.web_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.web_sa.email}"
}

resource "google_cloud_run_v2_service" "web_ui" {
  name     = local.web_ui_name
  location = var.region

  deletion_protection = false

  template {
    service_account = google_service_account.web_sa.email

    volumes {
      name = "nginx-conf"
      secret {
        secret = google_secret_manager_secret.app_secrets["web-ui-nginx-conf"].secret_id

        items {
          path    = "default.conf"
          version = "latest"
        }
      }
    }

    volumes {
      name = "htpasswd"
      secret {
        secret = google_secret_manager_secret.app_secrets["web-ui-htpasswd"].secret_id

        items {
          path    = ".htpasswd"
          version = "latest"
        }
      }
    }

    containers {
      name  = "nginx"
      image = "mirror.gcr.io/library/nginx:stable"

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }

      ports {
        name           = "http1"
        container_port = 8080
      }

      volume_mounts {
        name       = "nginx-conf"
        mount_path = "/etc/nginx/conf.d"
      }

      volume_mounts {
        name       = "htpasswd"
        mount_path = "/etc/nginx/secrets"
      }
    }

    containers {
      name  = "nextjs"
      image = local.frontend_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "PORT"
        value = "3000"
      }

      env {
        name  = "NEXT_PUBLIC_API_URL"
        value = google_cloud_run_v2_service.web_api.uri
      }

      env {
        name  = "API_AUDIENCE"
        value = google_cloud_run_v2_service.web_api.uri
      }
    }
  }

  depends_on = [
    google_project_service.enabled["run.googleapis.com"],
    google_secret_manager_secret_iam_member.consumers,
    google_secret_manager_secret_version.app_secret_versions,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "web_ui_public" {
  name     = google_cloud_run_v2_service.web_ui.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_job" "ingestion" {
  name     = local.ingestion_job
  location = var.region

  deletion_protection = false

  template {
    task_count = 1

    template {
      service_account = google_service_account.ingestion_sa.email
      max_retries     = 2
      timeout         = "1200s"

      volumes {
        name = "datalake"
        gcs {
          bucket = google_storage_bucket.datalake.name
        }
      }

      containers {
        image   = local.ingestion_image
        command = ["python", "-m", "inversa.ingestion.backfill"]

        env {
          name  = "DATA_DIR"
          value = "/mnt/data"
        }

        env {
          name  = "REGION_CALIFORNIA"
          value = var.bbox
        }

        env {
          name  = "REGION_NW_INDIA"
          value = var.nw_india_bbox
        }

        dynamic "env" {
          for_each = {
            for name, m in local.secret_meta_enabled : m.env_key => name
            if m.consumed_by == "ingestion"
          }
          content {
            name = env.key

            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.app_secrets[env.value].id
                version = "latest"
              }
            }
          }
        }

        volume_mounts {
          name       = "datalake"
          mount_path = "/mnt/data"
        }
      }
    }
  }

  depends_on = [
    google_project_service.enabled["run.googleapis.com"],
    google_project_service.enabled["storage-component.googleapis.com"],
    google_secret_manager_secret_iam_member.consumers,
    google_secret_manager_secret_version.app_secret_versions,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "ingestion_scheduler_invoker" {
  name     = google_cloud_run_v2_job.ingestion.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.ingestion_sa.email}"
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_iam_member" "scheduler_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

resource "google_cloud_scheduler_job" "trigger_ingestion" {
  name             = "trigger-ingestion"
  region           = var.region
  schedule         = "0 */2 * * *"
  time_zone        = "UTC"
  attempt_deadline = "1200s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.ingestion.name}:run"

    oauth_token {
      service_account_email = google_service_account.ingestion_sa.email
    }
  }

  depends_on = [
    google_project_service.enabled["cloudscheduler.googleapis.com"],
    google_project_service.enabled["run.googleapis.com"],
  ]
}
