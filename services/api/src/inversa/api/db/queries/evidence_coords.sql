-- Resolve lat/lon for given fire and station ids: envelope evidence (bbox_focus) and the
-- region_bbox post-filter for the analyze tool. Parameters: $fire_ids (LIST(VARCHAR)),
-- $station_ids (LIST(VARCHAR)).
WITH station_latest AS (
    SELECT station_id, lat, lon
    FROM v_air_quality
    WHERE station_id IS NOT NULL
      AND lat IS NOT NULL
      AND lon IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY ingested_at DESC) = 1
)
SELECT
    'fire' AS kind,
    fire_id AS id,
    lat,
    lon
FROM v_fires
WHERE list_contains($fire_ids, fire_id)
  AND lat IS NOT NULL
  AND lon IS NOT NULL
UNION ALL
SELECT
    'station' AS kind,
    station_id AS id,
    lat,
    lon
FROM station_latest
WHERE list_contains($station_ids, station_id);
