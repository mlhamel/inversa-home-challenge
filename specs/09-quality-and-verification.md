---
id: spec-09-quality-and-verification
title: Automated Verification, Linting, Typechecking, and Testing
version: 1.0.0
depends_on: [spec-01-data-contracts, spec-03-duckdb-spatial-engine, spec-04-mcp-server-spec]
---

# 1. Toolchain & Root Configuration (`pyproject.toml` & `.pre-commit-config.yaml`)
All Python packages (`packages/shared-schemas`, `services/ingestion`, `services/api`) share centralized strict quality gates:
- **Lint & Format (`ruff`):** Enforces PEP8, import sorting (`I`), bugbear (`B`), and async rules (`ASYNC`) with line-length `100`.
- **Static Typechecking (`mypy`):** Configured in `strict = true` mode across `services/` and `packages/`, ensuring generated Protobuf types and PydanticAI tool signatures align cleanly.
- **Protobuf Linting (`protolint` + `buf lint`):** Validates `packages/proto/inversa/v1/*.proto` naming conventions, field numbering, and package structure.
- **Git Hooks (`prek`):** Configured via `.pre-commit-config.yaml` to run `ruff check`, `ruff format --check`, `mypy`, and `protolint` locally before commits.

# 2. High-Leverage `pytest` Suite (Targeted, Fast, Zero-Flake)
Focus test coverage strictly on high-risk domain logic rather than boilerplate CRUD:

## 2.1 Data Contract & Quality Flag Tests (`services/ingestion/tests/test_quality_rules.py`)
- Verify OpenAQ outlier detection (`pm25 < 0` or `pm25 > 1500` -> `QUALITY_FLAG_OUTLIER` and `pm25 = None`).
- Verify staleness threshold (`ingested_at - observed_at > 2h` -> `QUALITY_FLAG_STALE`).
- Verify deterministic `fire_id` hashing prevents duplicates across overlapping NASA FIRMS ingestion windows.

## 2.2 DuckDB Spatial & Downwind Cone Math Tests (`services/api/tests/test_downwind_sql.py`)
- Spin up an in-memory DuckDB instance (`:memory:`) with synthetic Parquet fixtures in `tmp_path`.
- **Positive downwind case:** Fire at `(lat, lon)` with wind blowing `FROM 270°` (West -> East, `plume_bearing = 90°`) matches a station due East within `±25°` and `150 km`.
- **360° wrap-around edge case:** Wind blowing `FROM 175°` (`plume_bearing = 355°`) accurately matches a station at bearing `5°` (`angle_diff_deg = 10°`, testing the modulo wrap-around formula).
- **Upwind rejection case:** Station located upwind (`angle_diff_deg = 180°`) is excluded.
- **Stale visibility preservation:** Downwind stations with `quality_flag = 'stale'` remain in query results with `pm25 = None`.

## 2.3 MCP & API Grounding Contract Tests (`services/api/tests/test_mcp_contracts.py`)
- Invoke `FastMCP` tools directly against synthetic Parquet fixtures and validate that every response deserializes cleanly into the `McpToolEnvelope` Protobuf schema with non-empty `evidence_refs`.

# 3. Unified Verification Command (`Makefile`)
- `make verify` runs: `protolint lint packages/proto && ruff check . && mypy services packages && pytest`
- Antigravity MUST run `make verify` and achieve exit code `0` at the end of every implementation phase in `specs/README.md`.
