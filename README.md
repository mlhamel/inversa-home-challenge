# Inversa — Wildfire & Air Quality Explorer

An interactive, natural-language-driven web application to explore in real time — and over a rolling 7-day window — how active wildfires and shifting wind patterns degrade air quality in downwind communities.

> **Core question:** "How do smoke plumes from active wildfires and shifting wind patterns degrade air quality in downwind communities, and how does this evolve over time?"

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
- **Infrastructure.** Terraform-provisioned GCS + Cloud Run (Service + Job) + Cloud Scheduler, deployed by GitHub Actions.

## Repository map

| Piece | Path | What it is |
| --- | --- | --- |
| Specs (source of truth) | [`specs/`](specs/README.md) | OKF Markdown specifications 00–09 — all implementation decisions flow from these |
| Proto contracts | [`packages/proto`](packages/proto/README.md) | Canonical `inversa.v1` `.proto` definitions, buf-managed |
| Shared schemas | [`packages/shared-schemas`](packages/shared-schemas/README.md) | Generated Python bindings (namespace `inversa.v1`) |
| Ingestion | [`services/ingestion`](services/ingestion/README.md) | Cloud Run Job: FIRMS / OpenAQ / Open-Meteo collectors → Parquet datalake |
| API | `services/api` (Phase 3+) | FastAPI + FastMCP + in-memory DuckDB + PydanticAI agent |
| Web | [`apps/web`](apps/web/README.md) | Next.js + MapLibre/Deck.gl frontend — *planned, Phase 5* |
| Infra | `infra/` | Terraform GCP infrastructure — *planned, Phase 6* |

## Build status

Phased build per [`specs/README.md` §2](specs/README.md) — one phase per PR:

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Contracts | `packages/proto` + `packages/shared-schemas`, buf codegen | ✅ Done |
| 2. Ingestion & local datalake | `services/ingestion` collector code (FIRMS, OpenAQ, Open-Meteo) | ✅ Done |
| 2b. Data scrape (backfill) | `make backfill` real-API run into `${DATA_DIR}` (spec-02 §4 + spec-10) | ✅ Done: nasa_firms 290 + openaq 11629 + open_meteo 21991 rows ingested |
| 3. DuckDB + FastMCP | `services/api` engine + `/mcp` | ✅ Done |
| 4. FastAPI + agent | REST + SSE chat, golden prompts | ✅ Done |
| 5. Frontend | Map, timeline, chat drawer | ⏳ Next |
| 6. Cloud deployment | Terraform + CI/CD → public demo URL | ⬜ Planned |

## Getting started

```bash
git clone git@github.com:mlhamel/inversa-home-challenge.git && cd inversa-home-challenge
cp .env.example .env          # BBOX, DATA_DIR, FIRMS_MAP_KEY, OPENAQ_API_KEY
make proto                    # lint .protos + regenerate Python/TS bindings
make verify                   # protolint + prek/ruff + mypy --strict + pytest
make backfill                 # 7 days of real Parquet into ./.local_datalake
```

## Documentation

- [`specs/`](specs/README.md) — the authoritative specifications (00: vision · 01: contracts · 02: ingestion · 03: DuckDB engine · 04: MCP · 05: API/agent · 06: frontend · 07: infra · 08: agent behavior · 09: QA/load)
- [`AGENTS.md`](AGENTS.md) — repository constitution: hard architectural boundaries and verification loop
- [`docs/inversa-take-home-challenge.pdf`](docs/inversa-take-home-challenge.pdf) — the original challenge brief
