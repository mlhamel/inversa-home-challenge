-- spec-05 §1 snapshot: latest Open-Meteo wind vector per grid point at/before the
-- target instant; hourly slots make gaps up to one hour legal.
-- Parameters: $target_ts (TIMESTAMP)
SELECT
    grid_id,
    observed_at,
    lat,
    lon,
    wind_speed_10m,
    wind_direction_10m,
    boundary_layer_height
FROM v_weather
WHERE observed_at <= CAST($target_ts AS TIMESTAMP)
QUALIFY ROW_NUMBER() OVER (PARTITION BY grid_id ORDER BY observed_at DESC) = 1
ORDER BY grid_id ASC;
