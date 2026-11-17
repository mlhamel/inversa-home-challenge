---
id: spec-05-fastapi-agent-gateway
title: FastAPI Gateway, SSE Streaming, and Agent Orchestration
version: 1.0.0
depends_on: [spec-03-duckdb-spatial-engine, spec-04-mcp-server-spec]
---

# 1. REST Endpoints (Map & Timeline Data)
- **`GET /api/timeline/summary?start={iso}&end={iso}`**
  - Returns a lightweight JSON array of hourly aggregates (`hour_bucket`, `active_fires_count`, `avg_pm25`, `max_pm25`, `active_stations`, `stale_stations`) in < 50ms for smooth 60fps client-side timeline scrubbing.
- **`GET /api/snapshot?timestamp={iso}`**
  - Returns the exact map state at `timestamp`: active FIRMS fires over the trailing 4 hours, all OpenAQ stations with `quality_flag`, and wind vector grid points from Open-Meteo.

# 2. Conversational Endpoint (`POST /api/chat`)
- **Protocol:** Server-Sent Events (`text/event-stream`).
- **Orchestrator:** `PydanticAI` wired to the `FastMCP` server tools and resources.
- **System Prompt Rules:**
  - Always check `resource://data/freshness` when answering questions about current/"live" conditions.
  - Cite exact station names, PM2.5 values, distances, wind bearings, and explicitly note stale or missing sensors.
- **SSE Events Emitted to Frontend:**
  - `event: tool_call` -> `{"tool": "analyze_downwind_impact", "status": "running"}` (UI thinking indicator).
  - `event: evidence` -> `evidence_refs` payload extracted from MCP tool output (triggers automatic timeline scrubbing and map zoom/highlight).
  - `event: token` -> Streamed Markdown text chunks of the final response.