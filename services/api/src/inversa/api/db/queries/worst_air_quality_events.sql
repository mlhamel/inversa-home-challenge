-- spec-04 tool 3 (find_worst_air_quality_events): per-station-hour argmax of valid PM2.5,
-- ranked across the window with exact reading timestamps. No canonical SQL in the spec.
-- Stale and outlier readings are excluded from ranking but counted for data_quality_notes.
-- Parameters: $start_ts (TIMESTAMP), $end_ts (TIMESTAMP), $limit (BIGINT)
WITH ranked AS (
    SELECT
        station_id,
        station_name,
        lat,
        lon,
        pm25,
        observed_at,
        ROW_NUMBER() OVER (
            PARTITION BY station_id, date_trunc('hour', observed_at)
            ORDER BY pm25 DESC NULLS LAST, ingested_at DESC
        ) AS rn
    FROM v_air_quality
    WHERE observed_at BETWEEN CAST($start_ts AS TIMESTAMP) AND CAST($end_ts AS TIMESTAMP)
      AND quality_flag = 'valid'
      AND pm25 IS NOT NULL
      AND lat IS NOT NULL
      AND lon IS NOT NULL
),
hourly_peaks AS (
    SELECT * FROM ranked WHERE rn = 1
),
excluded AS (
    SELECT
        COUNT(*) FILTER (WHERE quality_flag = 'stale') AS stale_excluded,
        COUNT(*) FILTER (WHERE quality_flag = 'outlier') AS outlier_excluded
    FROM v_air_quality
    WHERE observed_at BETWEEN CAST($start_ts AS TIMESTAMP) AND CAST($end_ts AS TIMESTAMP)
      AND quality_flag != 'valid'
)
SELECT
    hp.station_id,
    hp.station_name,
    hp.lat,
    hp.lon,
    hp.pm25,
    hp.observed_at,
    COALESCE(e.stale_excluded, 0) + COALESCE(e.outlier_excluded, 0) AS stale_outlier_excluded
FROM hourly_peaks hp
CROSS JOIN excluded e
ORDER BY hp.pm25 DESC
LIMIT $limit;
