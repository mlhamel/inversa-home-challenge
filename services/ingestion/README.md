# services/ingestion

Cloud Run Job that collects the three live feeds and lands them as ZSTD-compressed Apache Parquet under `${DATA_DIR}` (`/mnt/data` via GCS FUSE in production, `./.local_datalake` locally).

- **Collectors** (`fetch_firms`, `fetch_openaq`, `fetch_open_meteo`): async `httpx` with shared retry policy (`http_retry`), every record validated against the `inversa.v1` proto contracts (`contract`) before it may be written (`storage`)
- **Validation** (`validate`): physics-bounds checks; stale (> 2h) and outlier records are flagged with `QualityFlag` — never dropped silently
- **Backfill** (`backfill`): 7-day historical window per `BBOX` with per-collection provenance in `result`.

```bash
uv run python -m inversa.ingestion.backfill   # or: make backfill
```

Configuration comes from `.env`: `BBOX` (`min_lon,min_lat,max_lon,max_lat`), `DATA_DIR`, `FIRMS_MAP_KEY`, `OPENAQ_API_KEY` (Open-Meteo needs no key).

The package lives under the `inversa` PEP 420 namespace (`inversa.ingestion`) with pydantic models as value objects.

Governing spec: [`specs/02-ingestion-pipelines.md`](../../specs/02-ingestion-pipelines.md)
