-- canonical spec-03 §3.1 downwind smoke plume analysis
-- Parameters: $target_ts (TIMESTAMP), $radius_km (DOUBLE, default 150.0), $cone_half_angle (DOUBLE, default 25.0)
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
