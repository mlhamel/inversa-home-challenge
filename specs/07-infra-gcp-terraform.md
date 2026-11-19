---
id: spec-07-infra-gcp-terraform
title: GCP Infrastructure (Terraform) and CI/CD (GitHub Actions)
version: 1.0.0
depends_on: [spec-02-ingestion-pipelines, spec-05-fastapi-agent-gateway]
---

# 1. Terraform Resources (`infra/`)
- **`google_storage_bucket.datalake`:** Regional GCS bucket with a lifecycle rule deleting objects older than 30 days.
- **`google_service_account.api_sa` / `ingestion_sa` / `web_sa`:** Dedicated per-workload service accounts — `ingestion_sa` on the job (bucket `roles/storage.objectAdmin`), `web_sa` on the UI (and the only non-IAM `web_api` invoker), each holding `roles/secretmanager.secretAccessor` on the secrets its workload consumes (`locals.secret_consumers`).
- **`google_cloud_run_v2_service.web_api`:**
  - Runs the unified FastAPI + FastMCP + DuckDB container (`2 vCPU`, `2 GiB RAM`).
  - **GCS FUSE Volume Mount:** Mounts `google_storage_bucket.datalake` at `/mnt/data` (`read_only = true`).
  - **IAM-only invoker:** the public `allUsers` binding is gone; only `web_sa` holds `roles/run.invoker`, so direct callers must present a `web_sa` identity token (`gcloud auth print-identity-token` or the web-ui middleware).
- **`google_cloud_run_v2_service.web_ui`:** a two-container (sidecar) Cloud Run service providing the shareable demo URL:
  - **`nginx` entry container** (`mirror.gcr.io/library/nginx:stable`, port `8080`): basic-auth gate (`auth_basic_user_file /etc/nginx/secrets/.htpasswd`) in front of `proxy_pass http://127.0.0.1:3000`, with `proxy_buffering off` and 3600s read/send timeouts so the SSE stream stays live; `/healthz` is auth-exempt for probes.
  - **`nextjs` container** (port `3000` via `PORT`): the React map/timeline/chat UI, whose same-origin `/api/*` proxy now reaches the IAM-only `web_api`; `src/middleware.ts` attaches a `web_sa` ID token (audience = runtime env `API_AUDIENCE`, deliberately not the build-inlined `NEXT_PUBLIC_API_URL`) fetched from the instance metadata server, failing open when no metadata server exists (local `make serve`).
  - Both secrets ride Secret Manager volume mounts (`web-ui-htpasswd` apr1 hash, `web-ui-nginx-conf` server block), read by `web_sa`.
- **`google_cloud_run_v2_job.ingestion_job`:**
  - Executes `python -m inversa.ingestion.backfill` with `FIRMS_MAP_KEY`, `OPENAQ_API_KEY`, and the study-area variables (`REGION_*`, falling back to `BBOX`) as defined in spec-02 section 1.
- **`google_cloud_scheduler_job.trigger_ingestion`:**
  - Triggers `ingestion_job` every 2 hours (`0 */2 * * *`).

# 2. CI/CD Pipeline (`.github/workflows/deploy.yml`)
- Triggered on push to `main`.
- Keyless GCP authentication via Workload Identity Federation (OIDC).
- Builds and pushes `backend`, `ingestion`, and `frontend` Docker images to Google Artifact Registry.
- Updates Cloud Run Service and Cloud Run Job definitions automatically.
- Passes the optional `WEB_UI_HTPASSWD` GitHub secret into `TF_VAR_web_ui_htpasswd`; when unset, the throwaway demo default in `variables.tf` applies.
