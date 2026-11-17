---
id: spec-04-mcp-server-spec
title: FastMCP Server Specification
version: 1.0.0
depends_on: [spec-03-duckdb-spatial-engine]
---

# 1. Mounting & Transport
- **Library:** `fastmcp` mounted onto the FastAPI application at `/mcp` (`mcp.http_app(path="/")`).
- **Interoperability:** Consumed internally by the web app's AI orchestrator and externally accessible to any Streamable HTTP MCP client (e.g., Claude Desktop).

# 2. Standardized Tool Return Contract (UI Grounding)
Every `@mcp.tool()` must return a structured JSON dictionary adhering to this schema so both the LLM and the frontend map/timeline stay synchronized:

    {
      "summary_for_llm": "Factual narrative summary with values, units, distances, and freshness caveats.",
      "data_quality_notes": ["List of stale sensors or satellite latency warnings"],
      "evidence_refs": {
        "fire_ids": ["firms_..."],
        "station_ids": ["openaq_..."],
        "focus_timestamp": "2026-11-17T14:00:00Z",
        "bbox_focus": [-122.5, 37.0, -120.5, 38.5]
      }
    }

# 3. Tool Catalog (`@mcp.tool`)
1. **`analyze_downwind_impact(timestamp_iso: str, region_bbox: list[float] | None, radius_km: float = 150.0)`**
   - Executes the `analyze_downwind` spatial query from `spec-03`.
   - Identifies causal fire -> wind -> PM2.5 spike correlations.
2. **`get_station_timeseries(station_id: str, start_iso: str, end_iso: str)`**
   - Returns hourly PM2.5, local wind vectors, and nearby fire counts for a specific OpenAQ station.
3. **`find_worst_air_quality_events(start_iso: str, end_iso: str, limit: int = 5)`**
   - Ranks the highest PM2.5 peaks across the time window and returns their exact timestamps to guide timeline scrubbing.

# 4. Resource Catalog (`@mcp.resource`)
1. **`resource://data/freshness`**
   - Reads `ingestion_log.parquet` and returns exact data age per source plus known structural latency (e.g., NASA FIRMS ~3h lag).
2. **`resource://schema/capabilities`**
   - Documents measurement units (ug/m3, km/h, MW), EPA/WHO PM2.5 thresholds, and active geographic bounds.