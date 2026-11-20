# Inversa — Wildfire & Air Quality Explorer

An interactive, natural-language-driven web application to explore in real time — and over a rolling 7-day window — how active wildfires and shifting wind patterns degrade air quality in downwind communities.

> **Core question:** "How do smoke plumes from active wildfires and shifting wind patterns degrade air quality in downwind communities, and how does this evolve over time?"

> **Live demo:** <https://web-ui-yvllqhsf5a-nn.a.run.app/> — map, timeline, and natural-language chat, gated by a throwaway basic-auth prompt (user `demo`, password `inversa-demo-2026`; how to rotate it in the [deployment section](#one-time-cloud-deployment-phase-6)).

## The problem

Answering that question means joining three live external feeds, each with gaps that must be surfaced rather than hidden:

| Feed | Provides | Imperfections made explicit |
| --- | --- | --- |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | Active fire detections | ~3-hour satellite latency |
| [Open-Meteo](https://open-meteo.com/) | Wind vectors & boundary layer | forecast- vs. observed-time skew |
| [OpenAQ](https://openaq.org/) | Ground PM2.5 / PM10 stations | offline stations, stale (> 2h) & outlier readings |

Because smoke transport is wind-driven, the system relates fire hotspots to downwind cones (azimuth + distance) around them and tracks how measured air quality responds as the wind shifts — live, and replayable over the past 7 days.

## The goal

A map + timeline interface driven by a natural-language agent:

- **Evidence grounding, not hallucination.** Every factual claim references exact record IDs (`evidence_refs`: `fire_ids`, `station_ids`, `focus_timestamp`), so the UI can highlight the fires and sensors on the map and scrub the timeline to the exact timestamp.
- **Transparent data quality.** Missing, stale, and outlier measurements are never dropped silently: the `QualityFlag` flows through Parquet, DuckDB queries, and frontend rendering so blind spots stay visible.
- **Scope exclusions.** No authentication, user accounts, or RBAC — outside the challenge.

## Architecture at a glance

- **Protobuf is the single source of truth.** `buf`-managed `.proto` definitions (`packages/proto`) generate the Python and TypeScript bindings. Hand-written duplicates of telemetry or grounding types do not exist anywhere.
- **Parquet at rest, DuckDB for analytics, proto-JSON on the wire.** Ingestion lands ZSTD-compressed Parquet under `${DATA_DIR}` (`/mnt/data` via GCS FUSE on Cloud Run; `./.local_datalake` locally). The API queries it through in-memory DuckDB with the `spatial` extension and isolated cursors — `ST_Azimuth`, `ST_Distance_Spheroid`, and `ASOF JOIN` power the downwind reasoning.
- **Mounted FastMCP server.** Analytical tools and data-freshness resources are exposed via FastMCP at `/mcp` inside the FastAPI app; every tool returns an `McpToolEnvelope` carrying `evidence_refs` for UI grounding.
- **API & agent.** FastAPI serves snapshot/timeline REST endpoints plus an SSE `/api/chat` gateway backed by PydanticAI.
- **Frontend.** Next.js (App Router) with MapLibre GL JS / Deck.gl for the 60fps map and timeline canvas, consuming the generated TypeScript types.
- **Infrastructure.** Terraform-provisioned GCS + Cloud Run (Service + Job) + Cloud Scheduler, deployed by GitHub Actions. Deploys push new service images and run Terraform; they do not trigger an ingestion run — the lake refreshes at the next scheduled tick (within 2 h).

## Repository map

| Piece | Path | What it is |
| --- | --- | --- |
| Specs (source of truth) | [`specs/`](specs/README.md) | OKF Markdown specifications 00–09 — all implementation decisions flow from these |
| Proto contracts | [`packages/proto`](packages/proto/README.md) | Canonical `inversa.v1` `.proto` definitions, buf-managed |
| Shared schemas | [`packages/shared-schemas`](packages/shared-schemas/README.md) | Generated Python bindings (namespace `inversa.v1`) |
| Ingestion | [`services/ingestion`](services/ingestion/README.md) | Cloud Run Job: FIRMS / OpenAQ / Open-Meteo collectors → Parquet datalake |
| API | `services/api` | FastAPI + FastMCP + in-memory DuckDB + PydanticAI agent |
| Web | [`apps/web`](apps/web/README.md) | Next.js + MapLibre/Deck.gl frontend |
| Infra | `infra/` | Terraform GCP infrastructure |

## Build status

Phased build per [`specs/README.md` §2](specs/README.md) — one step per PR, each gated by `make verify`. The build-status column links the phase-delivery PRs; the journal below records what was learned.

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Contracts | `packages/proto` + `packages/shared-schemas`, buf codegen | ✅ Done — #3 |
| 2. Ingestion & local datalake | `services/ingestion` collector code (FIRMS, OpenAQ, Open-Meteo) | ✅ Done — #4, #9, #16 |
| 2b. Data scrape (backfill) | `make backfill` real-API run into `${DATA_DIR}` (spec-02 §4 + spec-10) | ✅ Done: nasa_firms 290 + openaq 11629 + open_meteo 21991 rows ingested — #18, #19 |
| 3. DuckDB + FastMCP | `services/api` engine + `/mcp` | ✅ Done — #13 |
| 4. FastAPI + agent | REST + SSE chat, golden prompts | ✅ Done — #20, #22 |
| 5. Frontend | Map, timeline, chat drawer | ✅ Done — #24 |
| 6. Cloud deployment | Terraform + CI/CD → public demo URL | ✅ Done — #27, #32, #38 |

## Build journal

What was actually learned during the build, with the PRs that carried each decision:

- **Repo & CI.** The `make verify` gate landed first (PR #1), per-package READMEs followed (PR #10), and a CI review bot auto-responds to review comments with opencode (PR #17).
- **Phases 1–2 · Contracts & collectors.** Buf-managed `inversa.v1` protos with offline buf codegen (PR #3), then the FIRMS / OpenAQ / Open-Meteo collectors writing contract-validated Parquet (PRs #4, #9, #16).
- **Phase 2b · Real-data scrape.** The first backfill "succeeded" against a stale FIRMS product — switching `VIIRS_SNPP_NRT` → `VIIRS_NOAA20_NRT` (PR #18) fixed it. Fire-active bounding boxes then returned 0 hotspots; verification showed the query was fine and the corrected NOAA-20 feed really did carry 290 active detections. The completed scrape: 290 fire + 11,629 OpenAQ + 21,991 Open-Meteo rows (PR #19), following the OpenAQ refinement spec (PR #12).
- **Phase 3 · DuckDB + FastMCP (PR #13).** Two hard-won SQL details: every DuckDB cursor gets `SET TimeZone='UTC'` and `geometry_always_xy=false`, and the spatial extension's XY mode takes coordinates lon-first — the axis order that bit hardest in this phase.
- **Phase 4 · FastAPI + agent.** Timeline/snapshot REST + SSE chat gateway (PR #20), station-timeseries hour clamping (PR #21), `GET /health` (PR #22), `make serve`/`make ask` ergonomics (PR #23). Agent answers were tuned bottom-line-first and concise (PR #26).
- **Phase 5 · Frontend.** Timeline dock, 3-layer map, and chat drawer (PR #24), API URL baked into the rewrite manifest (PR #33), a map legend (PR #36). Deck.gl icon layers crashed on asynchronously-drawn atlases — fixed with explicit `getPosition`, a canvas `iconAtlas`, and gating wind vectors on atlas presence (PRs #42–#44). Recent snapshots pre-cache into IndexedDB (PR #45) and the map surfaces loading/empty-hour state (PR #46).
- **Phase 6 · Cloud.** First deploy: Terraform + Docker images + GitHub Actions (PR #27), made green by bootstrap and Artifact Registry fixes (PRs #28–#31). The ingestion scheduler slowed to every 2 h to end overlapping runs (PR #35), and the deploy-time datalake refresh was dropped — deploys push images only, the lake refreshes at the next tick (PR #37). The web-api agent was pinned to the same ollama `glm-5.3-flash` model already used locally (PR #32).
- **Post-deploy hardening.** The demo is gated by an nginx basic-auth sidecar with `web-api` locked to IAM invokers (PR #38) — infrastructure access control on the public demo URL, not the excluded app-level auth: no user accounts or RBAC were added. A perf pass added gzip + ETag + snapshot prefetch (PR #39) and a TTL cache that skips gcsfuse rescans (PR #40). The app went multi-region via `REGION_*` env vars with subtle study-area map tints (PR #47), a `nw_india` Punjab–Haryana–Delhi NCR study area (PR #50), and `REGION_CALIFORNIA` wired onto `web_api` (PR #49). Agent thinking events stream to the chat drawer (PR #51) over an unbuffered SSE passthrough (PR #53).

## Getting started

```bash
git clone git@github.com:mlhamel/inversa-home-challenge.git && cd inversa-home-challenge
cp .env.example .env          # REGION_CALIFORNIA, DATA_DIR, FIRMS_MAP_KEY, OPENAQ_API_KEY
make bootstrap                # one-time setup: uv sync (.venv) + npm ci (apps/web) + prek
make proto                    # lint .protos + regenerate Python/TS bindings
make verify                   # protolint + prek/ruff + mypy --strict + pytest
make backfill                 # 7 days of real Parquet into ./.local_datalake
make serve                    # API on :8000 + web UI on :3000 — Ctrl-C stops both
```

## One-time cloud deployment (Phase 6)

The deploy workflow (`.github/workflows/deploy.yml`) runs on every merge to `main`:
it re-runs the verify gate, builds/pushes the `backend`, `ingestion`, and `frontend`
images to Artifact Registry, applies `infra/` with Terraform via keyless Workload
Identity Federation. Deploys do not trigger an ingestion run — the lake refreshes
at the next scheduled tick. Cloud Scheduler refreshes the datalake every 2 hours
(`0 */2 * * *`).

The only manual step is a one-time bootstrap — run from the repo root with an
Owner-level account (creates the tfstate bucket, Artifact Registry repo, WIF
pool/provider, and the deployer service account):

```bash
PROJECT_ID=inversa-home-challenge ./infra/bootstrap.sh
```

Then set the two variables and three secrets it prints:

```bash
gh variable set GCP_WIF_PROVIDER --body '<printed provider name>'
gh variable set GCP_DEPLOY_SA    --body '<printed deployer email>'
gh secret set FIRMS_MAP_KEY      --body '<NASA FIRMS MAP_KEY>'
gh secret set OPENAQ_API_KEY     --body '<OpenAQ API key>'
gh secret set AGENT_API_KEY      --body '<LLM API key>'
gh variable set AGENT_MODEL      --body 'openai:gpt-4o-mini'   # optional override
gh secret set WEB_UI_HTPASSWD    --body 'demo:<apr1 hash>'     # optional demo password
```

`WEB_UI_HTPASSWD` is optional: without it the demo uses the built-in throwaway
credential (user `demo`, password `inversa-demo-2026`). To rotate it, generate
a new line with `openssl passwd -apr1 '<new-password>'` and prefix it with
`demo:`.

`infra/` provisions: `web-api` (FastAPI + FastMCP + DuckDB, 2 vCPU/2 GiB, GCS FUSE
`/mnt/data` read-only, **IAM-only** — invoker restricted to `web_sa`), `web-ui`
(nginx basic-auth sidecar on port 8080 in front of Next.js on port 3000;
it proxies same-origin `/api/*` → `web-api`, and its middleware attaches a
`web_sa` identity token so the UI keeps working behind the IAM wall,
preserving the zero-CORS design directly to `web-api`), `ingestion-job` (GCS FUSE
read-write, writes ZSTD Parquet), the `${PROJECT_ID}-datalake` bucket with a 30-day
lifecycle rule, the `0 */2 * * *` scheduler, and Secret Manager entries for the optional
API keys (created only when the matching GitHub secret is non-empty; Cloud Run
reads them via `value_source`, never plain env vars; the nginx `.htpasswd` /
conf ride Secret Manager volume mounts). Idle cost is ≈ $0 —
`min-instances` 0 and no static IP. Local Terraform equivalent: `make infra-init`
/ `infra-plan` / `infra-apply` (pass secrets with
`TF_ARGS="-var firms_map_key=..."`).

Accessing the deployed demo:

- **Map / timeline / chat UI:** <https://web-ui-yvllqhsf5a-nn.a.run.app/> (printed
  as the `web_ui_url` Terraform output) plus the `demo` password — the URL is
  public, the basic-auth prompt is the gate.
- **Direct `web-api` calls** (scripts, graders, load tests): fetch a
  `web_sa`-flavored identity token and send it as a Bearer header:

  ```bash
  curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
       "$(terraform -chdir=infra output web_api_url)/health"
  ```

  (Your account needs `roles/run.invoker` on `web-api`; the agent's in-process
  MCP client needs nothing external.)
- Local `make serve` is unchanged — no auth, and the middleware fails open
  without a metadata server.

## Documentation

- [`specs/`](specs/README.md) — the authoritative specifications (00: vision · 01: contracts · 02: ingestion · 03: DuckDB engine · 04: MCP · 05: API/agent · 06: frontend · 07: infra · 08: agent behavior · 09: QA/load)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the specs turned into layers: component-interaction diagram, a layer-by-layer tour anchored in real paths, and spotlights on two new-to-me technologies (DuckDB over partitioned Parquet · Pydantic AI over Ollama/GLM 5.3)
- [`playbooks/`](playbooks/) — operational how-tos ([run a historical data backfill](playbooks/backfill.md))
- [`AGENTS.md`](AGENTS.md) — repository constitution: hard architectural boundaries and verification loop
