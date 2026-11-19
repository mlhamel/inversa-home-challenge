---
id: spec-02-ingestion-pipelines
title: Polars Ingestion Pipelines and Backfill Script
version: 2.1.0
depends_on: [spec-01-data-contracts]
---

# 1. Configurable Geographic Bounding Box
Ingestion collectors are bounded by environment variables that keep data volume low and query performance fast. One or more study areas are declared as `REGION_<NAME>` variables formatted as `min_lon,min_lat,max_lon,max_lat`; the lowercased `<NAME>` becomes the region id and an optional `REGION_<NAME>_LABEL` overrides its display label (>label defaults to the id). Every FIRMS and OpenAQ collection runs once per region; rows carry their `region` id, and Parquet batches are named `<source>/date=YYYY-MM-DD/<source>_<region>_<HHMM>.parquet`. `ingestion_log` rows gain the same `region` column, and run statuses are keyed `"<source>:<region_id>"`. The legacy `BBOX` variable remains supported as a single region with id `default`; any `REGION_*` variable takes precedence.

# 2. Validation & Serialization Flow
Each collector follows a strict three-step boundary pipeline:
1. **Fetch & Normalize:** Query external REST/CSV API via `httpx` and normalize fields in `Polars`.
2. **Contract Validation:** Validate records against the generated Python Protobuf classes from `inversa_schemas.v1` (`FireDetection`, `AirQualityReading`, `WindVector`) to enforce types and enum bounds (`QualityFlag`, `FireConfidence`).
3. **Persist:** Write ZSTD-compressed Parquet files to `${DATA_DIR}/<source>/date=YYYY-MM-DD/` and append a status row to `${DATA_DIR}/meta/ingestion_log.parquet`.

# 3. Collector Specifications (`services/ingestion/src/ingestion/`)

## 3.1 `fetch_firms.py` (NASA FIRMS)
- **Endpoint:** `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${FIRMS_MAP_KEY}/VIIRS_NOAA20_NRT/${BBOX}/1`
- **Schedule:** Every 2 hours via Cloud Scheduler (`0 */2 * * *`).
- **Polars Logic:**
  1. Parse CSV response via `pl.read_csv()`.
  2. Combine `acq_date` and zero-padded 4-digit `acq_time` (`HHMM`) into UTC `observed_at`.
  3. Map `confidence` (`'h'` -> `FIRE_CONFIDENCE_HIGH` / `'high'`, `'n'` -> `'nominal'`, `'l'` -> `'low'`).
  4. Generate deterministic `fire_id` and write Parquet to `fires/date=YYYY-MM-DD/`.

## 3.2 `fetch_openaq.py` (OpenAQ v3)
- **Endpoint:** `https://api.openaq.org/v3/locations?bbox=${BBOX}&parameters_id=2` (ID 2 = PM2.5).
- **Schedule:** Every 15 minutes.
- **Polars Logic:**
  1. Fetch active monitoring locations within `BBOX` and their latest sensor readings.
  2. Compute `quality_flag` (`'valid'`, `'outlier'`, `'stale'`) per `spec-01-data-contracts`.
  3. Write Parquet batch to `air_quality/date=YYYY-MM-DD/`.

## 3.3 `fetch_meteo.py` (Open-Meteo)
- **Endpoint:** `https://api.open-meteo.com/v1/forecast` (supports batch coordinate arrays `latitude=...&longitude=...`).
- **Schedule:** Hourly.
- **Spatial Sampling Logic:**
  1. Extract unique coordinates from OpenAQ stations and active fire cluster centroids (rounded to `0.25` degrees).
  2. Query `wind_speed_10m`, `wind_direction_10m`, and `boundary_layer_height` in UTC.
  3. Write Parquet batch to `weather/date=YYYY-MM-DD/`. To stay rate-limit friendly the forecast is queried once over the union grid across all regions; each grid row is attributed to the nearest region bbox and tagged with its `region`.

# 4. Historical Backfill Script (`services/ingestion/src/ingestion/backfill.py`)
- **Purpose:** Populate the trailing 7 days (`T-7d` to `T0`) immediately upon initial deployment so the interactive timeline has rich history on first load.
- **Historical Endpoints:**
  - **NASA FIRMS:** Use `day_range=7` on the Area CSV API.
  - **Open-Meteo:** Use `past_days=7` on `/v1/forecast`.
  - **OpenAQ:** Iterate over `/v3/sensors/{id}/hours` for the trailing 7 days across primary stations in `BBOX` (throttled via `asyncio.Semaphore(5)`).
