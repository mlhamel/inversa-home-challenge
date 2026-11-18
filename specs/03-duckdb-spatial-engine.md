---
id: spec-03-duckdb-spatial-engine
title: DuckDB Analytical Engine and Spatial Queries
version: 1.0.0
depends_on: [spec-01-data-contracts]
---

# 1. Lifecycle & Configuration (`services/api/src/db/engine.py`)
- **Instance:** In-memory DuckDB singleton (`duckdb.connect(":memory:")`) initialized during FastAPI `lifespan`.
- **Extensions:** Pre-install `spatial` during Docker image build (`INSTALL spatial;`) and load at runtime (`LOAD spatial;`).
- **Data Access:** Query Parquet files located in `${DATA_DIR}` (`/mnt/data` in Cloud Run via GCS FUSE, `./.local_datalake` locally) using `read_parquet(..., union_by_name=true)`.
- **Concurrency:** Every HTTP request or MCP tool call acquires an isolated cursor via `con.cursor()` for non-blocking concurrent reads.
- **Empty-Datalake Resilience:** Guard startup view creation so the service boots cleanly even before the first ingestion batch runs.

# 2. Logical Views Initialized at Startup
Create SQL views at startup to abstract file paths and handle deduplication across overlapping ingestion batches:
- `v_fires`: Deduplicates `fire_id` (`QUALIFY ROW_NUMBER() OVER (PARTITION BY fire_id ORDER BY ingested_at DESC) = 1`).
- `v_air_quality`: Deduplicates `measurement_id` (`QUALIFY ROW_NUMBER() OVER (PARTITION BY measurement_id ORDER BY ingested_at DESC) = 1`).
- `v_weather`: Deduplicates `(grid_id, observed_at)` (`QUALIFY ROW_NUMBER() OVER (PARTITION BY grid_id, observed_at ORDER BY ingested_at DESC) = 1`).

# 3. Canonical Queries (`services/api/src/db/queries/`)

## 3.1 Downwind Smoke Plume Analysis (`analyze_downwind.sql`)
- **Parameters:** `$target_ts` (TIMESTAMP), `$radius_km` (DOUBLE, default `150.0`), `$cone_half_angle` (DOUBLE, default `25.0`).
- **Algorithm:**
  1. Filter `v_fires` within `[target_ts - 4h, target_ts]` where `confidence != 'low'`.
  2. Associate each fire with the nearest wind observation using temporal `ASOF JOIN` (`f.observed_at >= w.observed_at`) and spatial proximity (`ST_DWithin`).
  3. Compute downwind plume direction: `plume_bearing = (w.wind_direction_10m + 180) % 360` (since meteorological wind direction indicates where wind blows FROM).
  4. Join `v_air_quality` within `[target_ts - 1h, target_ts]` and within `$radius_km` (`ST_Distance_Spheroid`).
  5. Calculate exact fire-to-station azimuth via `DEGREES(ST_Azimuth(...))`.
  6. Filter stations where the minimum circular angular delta `ABS(((bearing_to_station - plume_bearing + 540) % 360) - 180) <= $cone_half_angle`.
  7. Retain `'stale'` or `null` PM2.5 stations in the result set (`ORDER BY pm25 DESC NULLS LAST`) so the AI agent can explicitly report monitoring blind spots.

- **Canonical SQL:**

      WITH active_fires AS (
          SELECT
              f.fire_id,
              f.lat AS fire_lat,
              f.lon AS fire_lon,
              f.frp,
              f.confidence,
              f.observed_at AS fire_time,
              (w.wind_direction_10m + 180) % 360 AS plume_bearing_deg,
              w.wind_speed_10m
          FROM v_fires f
          ASOF JOIN v_weather w
              ON f.observed_at >= w.observed_at
          WHERE f.observed_at BETWEEN CAST($target_ts AS TIMESTAMP) - INTERVAL '4 hours'
                                  AND CAST($target_ts AS TIMESTAMP)
            AND f.confidence != 'low'
            AND ST_DWithin(ST_Point(f.lon, f.lat), ST_Point(w.lon, w.lat), 0.5)
      ),
      downwind_stations AS (
          SELECT
              af.fire_id,
              af.frp AS fire_frp,
              af.wind_speed_10m,
              af.plume_bearing_deg,
              aq.station_id,
              aq.station_name,
              aq.pm25,
              aq.quality_flag,
              aq.observed_at AS station_time,
              ROUND(ST_Distance_Spheroid(
                  ST_Point(af.fire_lat, af.fire_lon),
                  ST_Point(aq.lat, aq.lon)
              ) / 1000.0, 1) AS distance_km,
              DEGREES(ST_Azimuth(
                  ST_Point(af.fire_lon, af.fire_lat),
                  ST_Point(aq.lon, aq.lat)
              )) AS bearing_to_station
          FROM active_fires af
          JOIN v_air_quality aq
              ON aq.observed_at BETWEEN CAST($target_ts AS TIMESTAMP) - INTERVAL '1 hour'
                                    AND CAST($target_ts AS TIMESTAMP)
          WHERE ST_Distance_Spheroid(
              ST_Point(af.fire_lat, af.fire_lon),
              ST_Point(aq.lat, aq.lon)
          ) <= $radius_km * 1000.0
      )
      SELECT
          fire_id,
          fire_frp,
          station_id,
          station_name,
          pm25,
          quality_flag,
          distance_km,
          plume_bearing_deg,
          wind_speed_10m,
          ROUND(ABS(((bearing_to_station - plume_bearing_deg + 540) % 360) - 180), 1) AS angle_diff_deg
      FROM downwind_stations
      WHERE ABS(((bearing_to_station - plume_bearing_deg + 540) % 360) - 180) <= $cone_half_angle
      ORDER BY pm25 DESC NULLS LAST;

## 3.2 Pre-Aggregated Timeline Summary (`timeline_summary.sql`)
- **Parameters:** `$start_ts` (TIMESTAMP), `$end_ts` (TIMESTAMP).
- **Purpose:** Feeds `GET /api/timeline/summary` in < 50ms for 60fps client-side scrubbing.

      WITH aq_hourly AS (
          SELECT
              date_trunc('hour', observed_at) AS hour_bucket,
              COUNT(DISTINCT station_id) FILTER (WHERE quality_flag = 'valid') AS active_stations,
              COUNT(DISTINCT station_id) FILTER (WHERE quality_flag = 'stale') AS stale_stations,
              ROUND(AVG(pm25) FILTER (WHERE quality_flag = 'valid'), 1) AS avg_pm25,
              ROUND(MAX(pm25) FILTER (WHERE quality_flag = 'valid'), 1) AS max_pm25
          FROM v_air_quality
          WHERE observed_at BETWEEN CAST($start_ts AS TIMESTAMP) AND CAST($end_ts AS TIMESTAMP)
          GROUP BY 1
      ),
      fires_hourly AS (
          SELECT
              date_trunc('hour', observed_at) AS hour_bucket,
              COUNT(DISTINCT fire_id) AS active_fires_count
          FROM v_fires
          WHERE observed_at BETWEEN CAST($start_ts AS TIMESTAMP) AND CAST($end_ts AS TIMESTAMP)
            AND confidence != 'low'
          GROUP BY 1
      )
      SELECT
          COALESCE(aq.hour_bucket, f.hour_bucket) AS hour_bucket,
          COALESCE(f.active_fires_count, 0) AS active_fires_count,
          aq.avg_pm25,
          aq.max_pm25,
          COALESCE(aq.active_stations, 0) AS active_stations,
          COALESCE(aq.stale_stations, 0) AS stale_stations
      FROM aq_hourly aq
      FULL OUTER JOIN fires_hourly f ON aq.hour_bucket = f.hour_bucket
      ORDER BY 1 ASC;
