-- canonical spec-03 §3.2 pre-aggregated timeline summary
-- Parameters: $start_ts (TIMESTAMP), $end_ts (TIMESTAMP)
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
