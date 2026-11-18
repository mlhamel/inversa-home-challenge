---
id: spec-10-backfill-refinement
title: OpenAQ Backfill Refinement — Station Selection, Execution, and Quality-Flag Semantics
version: 1.0.0
depends_on: [spec-01-data-contracts, spec-02-ingestion-pipelines]
status: draft
---

# 1. Purpose

This spec refines `spec-02` §4 (historical backfill) for the OpenAQ feed. It is
normative where it says MUST and overrides `spec-02` §4 on the points below;
everywhere else `spec-02` still applies.

A naive backfill — every station in `BBOX` × 7 days — fails three ways:

1. **Too many API calls.** Hundreds of stations × hourly history, plus
   pagination, risks rate-limiting and a backfill that never finishes inside
   the Phase 2 session.
2. **No narrative relevance.** Stations far from any fire add nothing to the
   demo question (fire → wind → downwind air quality) while costing calls,
   Parquet size, and query time.
3. **Wrong quality flags.** `spec-01` §3.1 marks a reading `stale` when
   `ingested_at - observed_at > 2h`. Applied literally to backfilled rows
   (ingested today, observed days ago), the entire 7-day history would be
   flagged `stale` and the timeline would render every station grey.

# 2. Prerequisites

- `OPENAQ_API_KEY` is set (obtained from the OpenAQ Explorer dashboard after
  email verification). Before running anything, verify it with a single call:
  `GET /v3/locations?bbox=${BBOX}&limit=1`. If this fails, stop — do not
  attempt the backfill.
- `BBOX` is chosen (active fires present in the window, OpenAQ stations
  downwind). Fetch the FIRMS detections for the window first: station ranking
  (§3) depends on them.
- Python 3.12, `uv` workspace, `services/ingestion` (see `spec-02` §2).

# 3. Station Selection (Manifest)

Select the backfill station set **before** fetching any history. The selection
is deterministic and reviewable: write it to
`${DATA_DIR}/meta/station_manifest.json`.

## 3.1 Candidate fetch

1. `GET /v3/locations?bbox=${BBOX}&parameters_id=2` (`2` = PM2.5).
   Paginate (`limit=100`, follow `page`) until all locations are retrieved.
2. For each location, resolve its PM2.5 sensor(s) and keep the location only
   if at least one PM2.5 sensor has a reading within the last 24h at
   selection time (check via `GET /v3/locations/{id}/latest`).

## 3.2 Ranking and cap

Rank candidates in this order and take the top N:

1. **Downwind of an active fire.** Station within `150 km` of a fire observed
   in the last 24h AND within `±25°` of the plume bearing computed from the
   nearest wind vector (reuse the cone math of `spec-03` §3.1; if no wind data
   is available yet, use the distance test only and record that in the
   manifest).
2. **Geographic spread.** At most 2 stations per `0.5° × 0.5°` cell, to avoid
   clusters that add no information.
3. **Coverage.** Prefer stations with the most complete recent history.

Cap: `BACKFILL_MAX_STATIONS`, default `40` (acceptable range 30–50).

## 3.3 Manifest format

One entry per selected station:

```json
{
  "station_id": "openaq:<id>",
  "location_id": 1234,
  "sensor_id": 5678,
  "lat": 37.77,
  "lon": -122.42,
  "selection_reason": "downwind | coverage",
  "last_seen": "2026-11-17T14:00:00Z"
}
```

# 4. Backfill Execution

## 4.1 Window order

Backfill in two phases: **(A)** `T-3d` → `T0` first, verify (§6), then
**(B)** extend to `T-7d` → `T-3d`. A 3-day timeline is enough for a first
working demo; the extension runs in the background.

## 4.2 Per-sensor fetch

- `GET /v3/sensors/{sensor_id}/hours?datetime_from={from}&datetime_to={to}&limit=1000`.
  168 hourly values fit in one page; paginate if the response indicates more.
- Concurrency: `asyncio.Semaphore(5)` (as in `spec-02` §4).
- Retries: up to 3 attempts per request, exponential backoff (1s, 2s, 4s);
  honor `Retry-After` on HTTP 429; per-request timeout 30s.
- A sensor that fails after retries is recorded as `failed` in the ingestion
  log (§4.3) and skipped — it MUST NOT fail the whole run.

## 4.3 Writes and resume

- Write one ZSTD-compressed Parquet file per sensor per day under
  `air_quality/date=YYYY-MM-DD/` (layout per `spec-01` §3).
- Append one row per sensor per run to `meta/ingestion_log.parquet`
  (`source='openaq_backfill'`, `status` in `'success' | 'partial' | 'failed'`,
  `records_written`, `latest_data_ts`).
- **Resume:** skip sensors that already have a `success` row for the window.
  Re-running is safe: `measurement_id` is deterministic
  (`f"{station_id}_{observed_at_iso}"`, `spec-01` §3.1) and the
  `v_air_quality` view deduplicates on it (`spec-03` §2).
- **Do not synthesize rows for missing hours.** A station that was offline
  simply has no rows for those hours; the gap stays visible through the
  `active_stations` counts in `timeline_summary.sql` (`spec-03` §3.2).

# 5. Quality-Flag Semantics for Backfilled Rows (Normative)

This section corrects how `spec-01` §3.1 applies to backfill. It does NOT
change the rules for live ingestion.

- **Outlier rule — unchanged.** `pm25 < 0.0` or `pm25 > 1500.0` →
  `QUALITY_FLAG_OUTLIER` and `pm25 = null`.
- **Stale rule — replay semantics.** For backfilled rows, set
  `ingested_at = observed_at`, documented in code as "backfill replays
  ingestion at observation time". The `spec-01` stale rule
  (`ingested_at - observed_at > 2h`) then evaluates as if each reading had
  been ingested when observed, which is the correct semantics for historical
  data. Live ingestion keeps `ingested_at` = wall-clock ingestion time.
- **Rationale (for the debrief):** without this, every backfilled row is
  `stale` by construction and the demo's core transparency feature — showing
  real blind spots — becomes noise, because everything looks blind.

# 6. Verification / Acceptance Criteria

All MUST pass before Phase 2 is considered complete:

1. `make verify` passes (per `AGENTS.md` §3).
2. The station manifest exists, holds 30–50 stations, and every entry has a
   `selection_reason`.
3. Coverage report (print or log it): per station, % of the 168 expected
   hourly values present; flag any station below 50%.
4. **Zero backfilled rows flagged `stale` by ingestion lag.** Check with:
   `SELECT COUNT(*) FROM v_air_quality WHERE quality_flag = 'stale' AND
   ingested_at - observed_at > INTERVAL '2 hours'` — expect `0` for
   backfilled rows (rows flagged `stale` by a genuine late sensor feed are
   acceptable if the log explains them).
5. `GET /api/timeline/summary` (or the equivalent DuckDB query) returns 168
   hourly buckets for the 7-day window.
6. Spot check (manual): pick one fire and one downwind station from the
   manifest and confirm the PM2.5 elevation aligns with the fire's time in
   the data — not just in the UI.
7. `ingestion_log.parquet` has one row per sensor per run with an accurate
   `status`.

# 7. Integration With Existing Specs

- Add this file to the index in `specs/README.md` §1 and mention it in the
  Phase 2 description (§2, step 2).
- `spec-02` §4 defers to this spec for station selection, execution detail,
  and quality-flag semantics. No changes to `.proto` contracts are needed.
- No change to the phased order: this refinement is executed inside Phase 2,
  before Phase 3.

# 8. Out of Scope

- **Live collector optimization.** Replacing per-station `/latest` calls with
  a single `/v3/measurements?bbox=...` query per 15-minute cycle is a
  recommended follow-up for the live collector, not required for Phase 2.
- **Changing quality-flag rules for live ingestion.** Out of scope here.
