-- spec-05 §1 snapshot: every OpenAQ station with its latest reading at/before the
-- target instant, quality_flag preserved verbatim (stale/outlier stay visible).
-- Parameters: $target_ts (TIMESTAMP)
SELECT
    station_id,
    station_name,
    lat,
    lon,
    pm25,
    quality_flag,
    observed_at
FROM v_air_quality
WHERE observed_at <= CAST($target_ts AS TIMESTAMP)
QUALIFY ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY observed_at DESC) = 1
ORDER BY station_id ASC;
