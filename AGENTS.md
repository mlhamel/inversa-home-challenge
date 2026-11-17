# AGENTS.md — Repository Constitution & Agent Directives

## 1. Mission & Architectural North Star
This repository implements the Inversa Engineering Challenge: a real-time and historical (7-day) natural-language geospatial explorer analyzing how active wildfires (`NASA FIRMS`) and wind vectors (`Open-Meteo`) degrade downwind air quality (`OpenAQ`)[cite: 1].

All implementation decisions MUST strictly follow the OKF specifications in `specs/README.md` (`specs/00` through `specs/09`). Never invent alternative schemas, storage formats, or endpoints.

## 2. Hard Architectural Boundaries (Do Not Violate)
1. **Protobuf is the Single Source of Truth:**
   - Never hand-write duplicate Python dataclasses or TypeScript interfaces for telemetry or grounding payloads.
   - Edit `.proto` files in `packages/proto/inversa/v1/` and run `make proto` (`buf generate`) to update `packages/shared-schemas` and `apps/web/src/generated`.
2. **Parquet at Rest, DuckDB for Analytics, Proto-JSON on the Wire:**
   - Ingestion (`services/ingestion`) writes ZSTD-compressed Parquet files to `${DATA_DIR}` (`/mnt/data` in prod, `./.local_datalake` locally).
   - The API (`services/api`) reads Parquet strictly via in-memory `DuckDB` (`spatial` extension) using isolated cursors (`con.cursor()`). Never introduce Postgres, BigQuery, or Redis.
3. **Mounted FastMCP Server:**
   - Analytical tools and data-freshness resources MUST be exposed via `FastMCP` mounted at `/mcp` inside the FastAPI app—not as hardcoded LLM functions.
   - Every `@mcp.tool()` MUST return a valid `McpToolEnvelope` containing `evidence_refs` (`fire_ids`, `station_ids`, `focus_timestamp`) so the UI can highlight evidence on the map and timeline[cite: 1].
4. **Explicit Imperfect-Data Transparency:**
   - Never drop `stale` (>2h old) or `outlier` sensor records silently. Preserve `quality_flag` through Parquet, DuckDB queries, and frontend rendering so the agent and UI explicitly surface blind spots and NASA FIRMS's ~3-hour satellite latency[cite: 1].
5. **Scope Exclusions:**
   - Do NOT implement authentication, user accounts, RBAC, or billing[cite: 1].

## 3. Monorepo Commands & Verification Loop
Before considering any task or phase complete, you MUST run and pass:
- `make proto` — Lints `.proto` files (`buf lint`, `protolint`) and regenerates Python & TypeScript bindings.
- `make verify` — Runs `protolint`, `prek` / `ruff`, `mypy --strict`, and `pytest`.

## 4. Coding Standards
- **Python (`3.12+`):** Managed with `uv` workspaces. Full type annotations required (`mypy --strict` must pass). Use `pydantic` `BaseModel`s (with `model_config = ConfigDict(frozen=True)` when immutability is needed) for all Python value objects — never `dataclasses`. Use `Polars` (never `Pandas`) for ingestion transformations and `httpx.AsyncClient` for external API calls. All Python code lives under the `inversa` PEP 420 namespace: packages are `inversa.<service>.*` (e.g. `inversa.ingestion`), never a bare top-level `<service>` package, and `src/inversa/` must not contain an `__init__.py` (so `inversa.v1` from generated proto bindings merges into the same namespace).
- **SQL (`DuckDB`):** Parameterize all dynamic inputs (`$target_ts`, `$radius_km`). Keep spatial calculations (`ST_Azimuth`, `ST_Distance_Spheroid`, `ASOF JOIN`) inside `services/api/src/db/queries/`.
- **TypeScript (`Next.js` App Router):** Strict TypeScript (`noImplicitAny`). Consume generated types from `apps/web/src/generated/inversa/v1/`.

## 5. Phased Execution Workflow
Follow `specs/README.md` Section 2 sequentially (`Phase 1` -> `Phase 6`). After completing each phase:
1. Run `make verify` and fix all lint, type, or test failures.
2. Summarize what was built and any tradeoffs made before moving to the next phase.

## 6. Git & PR Workflow
All changes land on `main` through squash-merged PRs created with `gh`. The agent opens PRs but **never merges** — the user owns the merge button (see step 5). Work strictly **one step at a time**: one phase or sub-step per session — never batch multiple phases into a single branch, PR, or session — and stop for review after each completed step.

1. Branch from a fresh `main` per step: `feat/01-proto-contracts`, `fix/ingestion-retry`, ...
2. Write **Conventional Commits** — `type(scope): precise imperative message` (<= 100 chars), types `feat|fix|perf|refactor|test|build|ci|chore|docs|revert`, scopes from `proto|ingestion|api|web|infra|repo`. `scripts/check_conventional_commits.sh` enforces this via the prek commit-msg hook and in CI; PR titles must pass the same check because the squash-merge title becomes the commit subject.
3. Before pushing, `make verify` must pass (see §3).
4. Push, then create the PR with `gh pr create` (title + body following `.github/pull_request_template.md`).
5. Stop once CI is green — **the agent never merges**. Report the PR URL, the CI status, and hand off: merging (squash by default) and branch deletion are the user's responsibility.
