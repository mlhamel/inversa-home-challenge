-- spec-05 §1 snapshot: FIRMS active-fire detections in the trailing 4 h window
-- Parameters: $target_ts (TIMESTAMP)
SELECT
    fire_id,
    observed_at,
    lat,
    lon,
    frp,
    confidence,
    satellite
FROM v_fires
WHERE observed_at > CAST($target_ts AS TIMESTAMP) - INTERVAL '4' HOUR
  AND observed_at <= CAST($target_ts AS TIMESTAMP)
ORDER BY observed_at DESC, fire_id ASC;
