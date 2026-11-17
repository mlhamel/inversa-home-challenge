---
id: spec-07-infra-gcp-terraform
title: GCP Infrastructure (Terraform) and CI/CD (GitHub Actions)
version: 1.0.0
depends_on: [spec-02-ingestion-pipelines, spec-05-fastapi-agent-gateway]
---

# 1. Terraform Resources (`infra/`)
- **`google_storage_bucket.datalake`:** Regional GCS bucket with a lifecycle rule deleting objects older than 30 days.
- **`google_service_account.app_sa`:** Dedicated service account granted `roles/storage.objectAdmin` on the bucket and `roles/run.invoker`.
- **`google_cloud_run_v2_service.web_api`:**
  - Runs the unified FastAPI + FastMCP + DuckDB container (`2 vCPU`, `2 GiB RAM`).
  - **GCS FUSE Volume Mount:** Mounts `google_storage_bucket.datalake` at `/mnt/data` (`read_only = true`).
  - Public IAM binding (`allUsers` -> `roles/run.invoker`) to provide the required shareable demo URL[cite: 1].
- **`google_cloud_run_v2_job.ingestion_job`:**
  - Executes `python -m ingestion.run_all` with `FIRMS_MAP_KEY`, `OPENAQ_API_KEY`, and `BBOX` environment variables.
- **`google_cloud_scheduler_job.trigger_ingestion`:**
  - Triggers `ingestion_job` every 30 minutes (`*/30 * * * *`).

# 2. CI/CD Pipeline (`.github/workflows/deploy.yml`)
- Triggered on push to `main`.
- Keyless GCP authentication via Workload Identity Federation (OIDC).
- Builds and pushes `backend` and `ingestion` Docker images to Google Artifact Registry.
- Updates Cloud Run Service and Cloud Run Job definitions automatically.
