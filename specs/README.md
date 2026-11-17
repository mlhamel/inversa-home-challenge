---
id: spec-index
title: Master Specification Index & Antigravity Execution Plan
version: 1.0.0
---

# 1. Specification Map
- `00-context-and-vision.md` — Product narrative, monorepo structure, and stack.
- `01-data-contracts.md` — Canonical `.proto` definitions (`buf`) and GCS Parquet schemas.
- `02-ingestion-pipelines.md` — Polars collectors (FIRMS, OpenAQ, Open-Meteo) + 7-day backfill.
- `03-duckdb-spatial-engine.md` — In-memory DuckDB + `spatial` views and downwind cone SQL.
- `04-mcp-server-spec.md` — `FastMCP` tools, resources, and `McpToolEnvelope` UI grounding contract.
- `05-fastapi-agent-gateway.md` — FastAPI REST snapshot/timeline endpoints + SSE `/api/chat`.
- `06-frontend-timeline-map.md` — Next.js + MapLibre/Deck.gl map, timeline scrubber, and evidence drawer.
- `07-infra-gcp-terraform.md` — Terraform (GCS, Cloud Run Service/Job, Scheduler) + GitHub Actions.
- `08-agent-behavior-and-evals.md` — Agent system prompt guardrails and golden demo queries.
- `09-qa-and-load-testing.md` — Load testing, QA checklist, and final demo readiness.

# 2. Phased Build Order for Code Generation
Execute and verify one phase at a time:
1. **Phase 1 (Contracts):** Create `packages/proto/` and `packages/shared-schemas/`, run `buf generate`, and verify Python + TypeScript imports (`spec-01`).
2. **Phase 2 (Ingestion & Local Datalake):** Implement `services/ingestion` and run `make backfill` against a real `BBOX` to populate `.local_datalake/` with 7 days of real Parquet files (`spec-02`).
3. **Phase 3 (DuckDB + FastMCP):** Implement `services/api` DuckDB engine and `FastMCP` server; verify `/mcp` tools return valid `McpToolEnvelope` JSON against `.local_datalake/` (`spec-03`, `spec-04`).
4. **Phase 4 (FastAPI + Agent):** Wire `PydanticAI` agent and `/api/timeline/summary`, `/api/snapshot`, and `/api/chat` SSE endpoints; test against the 5 golden prompts (`spec-05`, `spec-08`).
5. **Phase 5 (Frontend):** Build `apps/web` MapLibre/Deck.gl canvas, 60fps timeline scrubber, and chat drawer with automatic evidence highlighting (`spec-06`).
6. **Phase 6 (Cloud Deployment):** Provision GCP via `infra/` Terraform and deploy via GitHub Actions to produce the public demo URL (`spec-07`).

# 3. Architectural Tradeoffs Log (For Final Interview Discussion)
- **Protobuf IDL + Parquet at Rest + Proto-JSON on Wire:** Enforces strict cross-language contracts without sacrificing DuckDB columnar pruning or browser/LLM JSON ergonomics.
- **DuckDB + GCS FUSE vs. Managed Warehouse (BigQuery/TimescaleDB):** Zero idle cost, sub-50ms analytical queries on 7-day windows, and native `spatial` + `ASOF JOIN` support inside a single Cloud Run container.
- **Mounted FastMCP vs. Separate Microservice:** Eliminates inter-service network latency for the web agent while still exposing a standards-compliant `/mcp` HTTP endpoint for external MCP clients (e.g., Claude Desktop).
- **Pre-Aggregated Hourly Timeline Summary:** Decouples timeline scrubbing (instant client-side state) from heavy spatial snapshot queries.
