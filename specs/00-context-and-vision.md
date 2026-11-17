---
id: spec-00-context
title: Context, Product Vision, and System Architecture
version: 1.1.0
status: approved
---

# 1. System Objective
Build an interactive, natural-language-driven web application to explore in real time and over a recent historical window (7 days) how active wildfires and wind dynamics impact urban and regional air quality.

## Core Narrative Question
> "How do smoke plumes from active wildfires and shifting wind patterns degrade air quality in downwind communities, and how does this evolve over time?"

# 2. Challenge Requirements & Constraints
- **Three Coherent Real-Time Data Feeds:** NASA FIRMS (active fires), OpenAQ (PM2.5/PM10 ground sensors), and Open-Meteo (wind vectors & boundary layer)[cite: 1].
- **Meaningful New Technology:** Expose the analytical query engine via a Model Context Protocol (`FastMCP`) server backed by `DuckDB` querying partitioned Parquet files[cite: 1].
- **Evidence Grounding & Traceability:** The AI agent must never hallucinate; every factual claim must reference exact record IDs (`evidence_refs`) so the UI can highlight sensors/fires on the map and scrub the timeline to the exact timestamp[cite: 1].
- **Transparent Data Quality Handling:** Explicitly surface missing, stale, or outlier measurements (e.g., ~3-hour satellite latency on NASA FIRMS, offline OpenAQ stations)[cite: 1].
- **Explicit Exclusions:** No user authentication, user accounts, or RBAC required[cite: 1].

# 3. Monorepo Directory Structure

    inversa-wildfire-airquality/
    ├── .github/workflows/deploy.yml   # Path-filtered CI/CD pipelines
    ├── specs/                         # OKF Markdown specifications (source of truth)
    ├── packages/
    │   └── shared-schemas/            # Shared Python Polars/Pydantic data contracts
    ├── services/
    │   ├── ingestion/                 # Cloud Run Job (Python 3.12 + Polars)
    │   └── api/                       # Cloud Run Service (FastAPI + FastMCP + DuckDB)
    ├── apps/
    │   └── web/                       # Next.js + MapLibre/Deck.gl frontend
    ├── infra/                         # Terraform GCP infrastructure
    ├── docker-compose.yml             # Local dev environment (mounts ./.local_datalake to /mnt/data)
    ├── Makefile                       # Unified developer commands
    └── .env.example

# 4. Technology Stack
- **Ingestion:** Python 3.12+, `uv`, `Polars`, `httpx`, `Apache Parquet` (ZSTD compression).
- **Storage:** Google Cloud Storage (GCS) mounted via GCS FUSE at `/mnt/data` on Cloud Run (`./.local_datalake` locally).
- **Analytical Engine & MCP:** `DuckDB` (with `spatial` extension) + `FastMCP` (Streamable HTTP transport at `/mcp`).
- **API & Agent Orchestration:** `FastAPI` + `PydanticAI` with Server-Sent Events (SSE) streaming.
- **Frontend:** `Next.js` (App Router), `Tailwind CSS`, `MapLibre GL JS` / `Deck.gl`.
- **Infrastructure & CI/CD:** `Terraform`, `Google Cloud Run` (Service + Job), `Cloud Scheduler`, `GitHub Actions`.