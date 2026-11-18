-- spec-04 tool 2 (get_station_timeseries): hourly PM2.5, local wind vector, and nearby
-- fire activity for one OpenAQ station. No canonical SQL in the spec; designed here.
-- Hour buckets come from the station's own readings; the wind vector is the single
-- nearest grid point (within 0.5 degrees) of the bucket; fire activity excludes
-- 'low' confidence detections within 0.5 degrees of the station.
-- Parameters: $station_id (VARCHAR), $start_ts (TIMESTAMP), $end_ts (TIMESTAMP)
WITH station AS (
    SELECT station_id, station_name, lat, lon
    FROM v_air_quality
    WHERE station_id = $station_id
      AND lat IS NOT NULL
      AND lon IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY ingested_at DESC) = 1
),
pm25_hourly AS (
    SELECT
        date_trunc('hour', observed_at) AS hour_bucket,
        COUNT(*) AS reading_count,
        ROUND(AVG(pm25) FILTER (WHERE quality_flag = 'valid'), 1) AS avg_pm25,
        ROUND(MAX(pm25) FILTER (WHERE quality_flag = 'valid'), 1) AS max_pm25,
        COUNT(*) FILTER (WHERE quality_flag = 'valid') AS valid_count,
        COUNT(*) FILTER (WHERE quality_flag = 'stale') AS stale_count,
        COUNT(*) FILTER (WHERE quality_flag = 'outlier') AS outlier_count
    FROM v_air_quality
    WHERE station_id = $station_id
      AND observed_at BETWEEN CAST($start_ts AS TIMESTAMP) - INTERVAL '59 minutes'
                          AND CAST($end_ts AS TIMESTAMP)
    GROUP BY 1
),
wind_hourly AS (
    SELECT
        date_trunc('hour', w.observed_at) AS hour_bucket,
        w.wind_speed_10m AS wind_speed_10m,
        w.wind_direction_10m AS wind_direction_10m
    FROM v_weather w
    CROSS JOIN station s
    WHERE (w.lon - s.lon) * (w.lon - s.lon) + (w.lat - s.lat) * (w.lat - s.lat) <= 0.25
      AND w.observed_at BETWEEN CAST($start_ts AS TIMESTAMP) - INTERVAL '59 minutes'
                            AND CAST($end_ts AS TIMESTAMP)
      AND w.wind_direction_10m IS NOT NULL
      AND w.wind_speed_10m IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY date_trunc('hour', w.observed_at)
        ORDER BY (w.lon - s.lon) * (w.lon - s.lon) + (w.lat - s.lat) * (w.lat - s.lat) ASC,
                 w.ingested_at DESC
    ) = 1
),
fires_ranked AS (
    SELECT
        date_trunc('hour', f.observed_at) AS hour_bucket,
        f.fire_id AS fire_id,
        f.frp AS fire_frp,
        ROUND(ST_Distance_Spheroid(
            ST_Point(f.lat, f.lon),
            ST_Point(s.lat, s.lon)
        ) / 1000.0, 1) AS fire_distance_km,
        COUNT(DISTINCT f.fire_id) OVER (
            PARTITION BY date_trunc('hour', f.observed_at)
        ) AS fire_count
    FROM v_fires f
    CROSS JOIN station s
    WHERE (f.lon - s.lon) * (f.lon - s.lon) + (f.lat - s.lat) * (f.lat - s.lat) <= 0.25
      AND f.observed_at BETWEEN CAST($start_ts AS TIMESTAMP) - INTERVAL '59 minutes'
                            AND CAST($end_ts AS TIMESTAMP)
      AND f.confidence != 'low'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY date_trunc('hour', f.observed_at)
        ORDER BY (f.lon - s.lon) * (f.lon - s.lon) + (f.lat - s.lat) * (f.lat - s.lat) ASC,
                 f.ingested_at DESC
    ) = 1
)
SELECT
    b.hour_bucket,
    COALESCE(b.avg_pm25, NULL) AS avg_pm25,
    COALESCE(b.max_pm25, NULL) AS max_pm25,
    COALESCE(b.reading_count, 0) AS reading_count,
    COALESCE(b.valid_count, 0) AS valid_count,
    COALESCE(b.stale_count, 0) AS stale_count,
    COALESCE(b.outlier_count, 0) AS outlier_count,
    w.wind_speed_10m,
    w.wind_direction_10m,
    COALESCE(fr.fire_count, 0) AS fire_count,
    fr.fire_id,
    fr.fire_frp,
    fr.fire_distance_km,
    s.station_id AS station_id,
    s.station_name AS station_name,
    s.lat AS station_lat,
    s.lon AS station_lon
FROM (
    SELECT hour_bucket FROM pm25_hourly
    UNION
    SELECT hour_bucket FROM wind_hourly
    UNION
    SELECT hour_bucket FROM fires_ranked
) buckets
LEFT JOIN pm25_hourly b ON b.hour_bucket = buckets.hour_bucket
LEFT JOIN wind_hourly w ON w.hour_bucket = buckets.hour_bucket
LEFT JOIN fires_ranked fr ON fr.hour_bucket = buckets.hour_bucket
CROSS JOIN station s
WHERE buckets.hour_bucket BETWEEN CAST($start_ts AS TIMESTAMP) AND CAST($end_ts AS TIMESTAMP)
ORDER BY buckets.hour_bucket ASC;
