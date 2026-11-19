---
id: spec-01-data-contracts
title: Canonical Protobuf Contracts, Buf Codegen, and Parquet Storage
version: 2.1.0
depends_on: [spec-00-context]
---

# 1. Schema Authority Strategy (Protobuf -> Parquet & JSON)
Protocol Buffers (`proto3`) serve as the single source of truth across all system boundaries:
- **Ingestion (`services/ingestion`):** Validates normalized external API payloads against generated Python dataclasses before writing to Parquet.
- **MCP & API (`services/api`):** Serializes FastMCP tool outputs (`McpToolEnvelope`, `EvidenceRefs`) and REST/SSE payloads (`TimelineBucket`, `MapSnapshot`) using canonical Proto3 JSON mapping.
- **Frontend (`apps/web`):** Consumes generated TypeScript interfaces for end-to-end type safety across MapLibre/Deck.gl layers and SSE stream parsers.

## 1.1 Buf Toolchain (`packages/proto/`)
Managed via `buf` (`buf generate` invoked via `make proto`):

    packages/proto/
    ├── buf.yaml
    ├── buf.gen.yaml
    └── inversa/v1/
        ├── telemetry.proto        # Domain entities: FireDetection, AirQualityReading, WindVector
        └── grounding.proto        # API & MCP contracts: EvidenceRefs, DownwindMatch, TimelineBucket

- **Python Target:** Outputs to `packages/shared-schemas/src/inversa_schemas/v1/` (installed as an editable workspace package in both `services/ingestion` and `services/api`).
- **TypeScript Target:** Outputs to `apps/web/src/generated/inversa/v1/` via `@bufbuild/protoc-gen-es`.

---

# 2. Canonical `.proto` Definitions

## 2.1 `packages/proto/inversa/v1/telemetry.proto`

    syntax = "proto3";
    package inversa.v1;

    import "google/protobuf/timestamp.proto";

    enum FireConfidence {
      FIRE_CONFIDENCE_UNSPECIFIED = 0;
      FIRE_CONFIDENCE_LOW = 1;
      FIRE_CONFIDENCE_NOMINAL = 2;
      FIRE_CONFIDENCE_HIGH = 3;
    }

    enum QualityFlag {
      QUALITY_FLAG_UNSPECIFIED = 0;
      QUALITY_FLAG_VALID = 1;
      QUALITY_FLAG_OUTLIER = 2;
      QUALITY_FLAG_STALE = 3;
    }

    message FireDetection {
      string fire_id = 1;
      google.protobuf.Timestamp observed_at = 2;
      google.protobuf.Timestamp ingested_at = 3;
      double lat = 4;
      double lon = 5;
      optional float frp = 6;
      FireConfidence confidence = 7;
      string satellite = 8;
    }

    message AirQualityReading {
      string measurement_id = 1;
      string station_id = 2;
      string station_name = 3;
      google.protobuf.Timestamp observed_at = 4;
      google.protobuf.Timestamp ingested_at = 5;
      double lat = 6;
      double lon = 7;
      optional float pm25 = 8;
      QualityFlag quality_flag = 9;
    }

    message WindVector {
      string grid_id = 1;
      google.protobuf.Timestamp observed_at = 2;
      google.protobuf.Timestamp ingested_at = 3;
      double lat = 4;
      double lon = 5;
      float wind_speed_10m = 6;
      float wind_direction_10m = 7;
      optional float boundary_layer_height = 8;
    }

## 2.2 `packages/proto/inversa/v1/grounding.proto`

    syntax = "proto3";
    package inversa.v1;

    import "google/protobuf/timestamp.proto";
    import "inversa/v1/telemetry.proto";

    message BoundingBox {
      double min_lon = 1;
      double min_lat = 2;
      double max_lon = 3;
      double max_lat = 4;
    }

    message EvidenceRefs {
      repeated string fire_ids = 1;
      repeated string station_ids = 2;
      google.protobuf.Timestamp focus_timestamp = 3;
      optional BoundingBox bbox_focus = 4;
    }

    message DownwindMatch {
      string fire_id = 1;
      float fire_frp = 2;
      string station_id = 3;
      string station_name = 4;
      optional float pm25 = 5;
      QualityFlag quality_flag = 6;
      double distance_km = 7;
      float plume_bearing_deg = 8;
      float wind_speed_10m = 9;
      double angle_diff_deg = 10;
    }

    message McpToolEnvelope {
      string summary_for_llm = 1;
      repeated string data_quality_notes = 2;
      EvidenceRefs evidence_refs = 3;
      repeated DownwindMatch matches = 4;
    }

    message TimelineBucket {
      google.protobuf.Timestamp hour_bucket = 1;
      int32 active_fires_count = 2;
      optional float avg_pm25 = 3;
      optional float max_pm25 = 4;
      int32 active_stations = 5;
      int32 stale_stations = 6;
    }

    message MapSnapshot {
      google.protobuf.Timestamp timestamp = 1;
      repeated FireDetection fires = 2;
      repeated AirQualityReading stations = 3;
      repeated WindVector wind_vectors = 4;
    }

---

# 3. GCS Parquet Storage Layout & Mapping Rules
All validated Protobuf entities are persisted as ZSTD-compressed Apache Parquet files in `gs://${GCS_BUCKET_NAME}/` partitioned by source and UTC date:

    gs://${GCS_BUCKET_NAME}/
    ├── fires/date=YYYY-MM-DD/fires_<region>_<HHMM>.parquet
    ├── air_quality/date=YYYY-MM-DD/openaq_<region>_<HHMM>.parquet
    ├── weather/date=YYYY-MM-DD/meteo_<region>_<HHMM>.parquet
    └── meta/ingestion_log.parquet

`<region>` is the lowercased id of the study area sourced from the `REGION_*` environment contract (spec-02 section 1), so batches from different regions never collide on a filename; legacy pre-region files keep their `fires_HHMM.parquet` shape and read back with a NULL `region` column.

## 3.1 Protobuf-to-Parquet Mapping Rules
- **Timestamps:** `google.protobuf.Timestamp` maps to Polars `Datetime('us', 'UTC')`.
- **Enums:** `FireConfidence` and `QualityFlag` are stored as lowercase string literals (`'high'`, `'nominal'`, `'low'`; `'valid'`, `'outlier'`, `'stale'`) in Parquet so DuckDB SQL queries remain human-readable, and are hydrated back into Protobuf enums when building API responses.
- **`fire_id` Rule:** Deterministic 16-char SHA-256 hash of `f"{lat:.4f}_{lon:.4f}_{observed_at_iso}"`.
- **Region Scoping:** every fire, air-quality, weather, and ingestion-log row carries a `region` string column with the id of the study area it was collected for (spec-02 section 1); the DuckDB engine unions it away as NULL for legacy files.
- **`measurement_id` Rule:** `f"{station_id}_{observed_at_iso}"`.
- **`quality_flag` Rules (OpenAQ):**
  1. If `pm25 < 0.0` or `pm25 > 1500.0`: `QUALITY_FLAG_OUTLIER` (`'outlier'`) and `pm25 = null`.
  2. If `(ingested_at - observed_at) > 2 hours`: `QUALITY_FLAG_STALE` (`'stale'`).
  3. Otherwise: `QUALITY_FLAG_VALID` (`'valid'`).

## 3.2 `ingestion_log` Table (Observability & Freshness)
| Column | Polars/Arrow Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `source` | `Utf8` | No | `'nasa_firms'`, `'openaq'`, or `'open_meteo'`. |
| `run_at` | `Datetime('us', 'UTC')` | No | Job execution timestamp. |
| `latest_data_ts` | `Datetime('us', 'UTC')` | Yes | Maximum `observed_at` received in this batch. |
| `known_latency_minutes` | `Int32` | No | Structural source latency: `180` for FIRMS, `15` for OpenAQ, `0` for Open-Meteo[cite: 1]. |
| `records_written` | `Int32` | No | Number of rows persisted. |
| `status` | `Utf8` | No | `'success'`, `'partial'`, or `'failed'`. |
