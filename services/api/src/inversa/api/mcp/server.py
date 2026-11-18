"""FastMCP tool surface (spec-04): three grounding tools and two data resources.

Every tool returns the spec-04 section 2 envelope JSON (``summary_for_llm``,
``data_quality_notes``, ``evidence_refs``). The proto ``DownwindMatch`` record is
shaped for tool 1's fire -> wind -> station correlation, so tools 2 and 3 keep
the envelope keys and carry their rows under a ``timeseries`` / ``events`` key.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from fastmcp import FastMCP
from inversa.api.config import Settings
from inversa.api.db import queries
from inversa.api.db.engine import open_cursor
from inversa.api.mcp.grounding import build_envelope, empty_envelope

FIRMS_LATENCY_NOTE: Final[str] = (
    "NASA FIRMS active-fire detections arrive ~3 h after real time (satellite latency); "
    "read resource://data/freshness for the exact per-source latency."
)

INGESTION_LOG_NOTE: Final[str] = "No ingestion log found; run services/ingestion first."

STATION_COLUMNS: Final[tuple[str, ...]] = (
    "source",
    "run_at",
    "latest_data_ts",
    "known_latency_minutes",
    "records_written",
    "status",
)


def build_mcp(settings: Settings) -> FastMCP:
    """Assemble the FastMCP server bound to the given datalake settings."""
    mcp = FastMCP(name="inversa-geo-explorer")

    @mcp.tool
    def analyze_downwind_impact(
        timestamp_iso: str,
        region_bbox: list[float] | None = None,
        radius_km: float = queries.DEFAULT_RADIUS_KM,
    ) -> dict[str, Any]:
        """Correlate active fires -> wind -> PM2.5 spikes at an instant (spec-03 section 3.1).

        Args:
            timestamp_iso: ISO-8601 instant; naive values are treated as UTC.
            region_bbox: optional [min_lon, min_lat, max_lon, max_lat]; keeps matches
                whose monitoring station lies inside the box and reports the box as
                bbox_focus so the UI keeps the requested viewport.
            radius_km: station search radius around the wind corridor (default 150).
        """
        target_ts = _parse_iso(timestamp_iso)
        cursor = open_cursor()
        try:
            matches = queries.run_analyze_downwind(
                cursor,
                target_ts=target_ts,
                radius_km=radius_km,
                cone_half_angle=queries.DEFAULT_CONE_HALF_ANGLE,
            )
            coords = queries.lookup_evidence_coords(
                cursor,
                fire_ids=sorted({match.fire_id for match in matches}),
                station_ids=sorted({match.station_id for match in matches}),
            )
        finally:
            cursor.close()
        if region_bbox is not None:
            matches = _filter_by_region(matches, coords, region_bbox)
        kept_fire_ids = sorted({match.fire_id for match in matches})
        kept_station_ids = sorted({match.station_id for match in matches})
        notes = [FIRMS_LATENCY_NOTE]
        blind_spots = sorted(
            {
                match.station_id
                for match in matches
                if match.quality_flag != "valid" or match.pm25 is None
            }
        )
        if blind_spots:
            notes.append(
                f"{len(blind_spots)} retained station reading(s) are stale or missing PM2.5 "
                f"({', '.join(blind_spots)}); those matches keep the raw PM2.5 under a "
                f"non-valid quality flag, so treat them as no-data."
            )
        if not matches:
            notes.append(
                "No fire -> station downwind correlations met the constraints at this "
                "timestamp."
            )
            return empty_envelope(
                summary_for_llm=(
                    f"No downwind impact correlations at {_iso_z(target_ts)} "
                    f"within {radius_km:.0f} km and a "
                    f"+/-{queries.DEFAULT_CONE_HALF_ANGLE:.0f} degree plume cone."
                ),
                notes=notes,
                focus_timestamp=target_ts,
            )
        points = [coords.fires[fire_id] for fire_id in kept_fire_ids]
        points += [coords.stations[station_id] for station_id in kept_station_ids]
        nearest = min(matches, key=lambda match: match.distance_km)
        summary = (
            f"{len(matches)} fire->station downwind correlation(s) for {_iso_z(target_ts)}: "
            f"{len(kept_fire_ids)} active fire(s) feeding {len(kept_station_ids)} station(s) "
            f"within {radius_km:.0f} km of a +/-{queries.DEFAULT_CONE_HALF_ANGLE:.0f} "
            f"degree plume cone. "
            f"Closest link: {nearest.station_name} ({nearest.station_id}) downwind of "
            f"{nearest.fire_id} at {nearest.distance_km:.1f} km, plume bearing "
            f"{nearest.plume_bearing_deg:.1f} deg, wind {nearest.wind_speed_10m:.1f} km/h, "
            f"PM2.5 {_pm25_label(nearest.pm25)}."
        )
        return build_envelope(
            summary_for_llm=summary,
            data_quality_notes=notes,
            fire_ids=kept_fire_ids,
            station_ids=kept_station_ids,
            focus_timestamp=target_ts,
            bbox_focus=(
                _normalize_bbox(region_bbox)
                if region_bbox is not None
                else _bbox_from_points(points)
            ),
            matches=[match.model_dump() for match in matches],
        )

    @mcp.tool
    def get_station_timeseries(station_id: str, start_iso: str, end_iso: str) -> dict[str, Any]:
        """Hourly PM2.5, local wind vector, and nearby fire counts for one station (spec-04 tool 2).

        Args:
            station_id: OpenAQ station identifier, as returned in tool 1 evidence_refs.
            start_iso: ISO-8601 window start (naive values treated as UTC).
            end_iso: ISO-8601 window end; must not precede start_iso.
        """
        start_ts = _parse_iso(start_iso)
        end_ts = _parse_iso(end_iso)
        if end_ts < start_ts:
            raise ValueError("end_iso must not precede start_iso.")
        cursor = open_cursor()
        try:
            rows = queries.run_station_timeseries(
                cursor,
                station_id=station_id,
                start_ts=start_ts,
                end_ts=end_ts,
            )
            fire_ids = sorted({row.fire_id for row in rows if row.fire_id})
            coords = queries.lookup_evidence_coords(
                cursor, fire_ids=fire_ids, station_ids=[station_id]
            )
        finally:
            cursor.close()
        notes: list[str] = []
        stale_total = sum(row.stale_count for row in rows)
        outlier_total = sum(row.outlier_count for row in rows)
        if stale_total or outlier_total:
            notes.append(
                f"{stale_total} stale and {outlier_total} outlier reading(s) in the window are "
                "kept in per-hour counts but excluded from PM2.5 averages (transparency rule)."
            )
        if not rows:
            notes.append(f"Station {station_id} returned no records for the requested window.")
        station_point = coords.stations.get(station_id)
        if station_point is None and rows:
            station_point = (rows[0].station_lon, rows[0].station_lat)
        points: list[tuple[float, float]] = []
        if station_point is not None:
            points.append(station_point)
        points += [coords.fires[fire_id] for fire_id in fire_ids if fire_id in coords.fires]
        peak = max((row.max_pm25 for row in rows if row.max_pm25 is not None), default=None)
        station_name = rows[0].station_name if rows else None
        if station_name:
            summary = (
                f"Hourly PM2.5 profile for {station_name} ({station_id}) between "
                f"{_iso_z(start_ts)} and {_iso_z(end_ts)}: {len(rows)} hourly bucket(s); "
                f"peak {_pm25_label(peak)}."
            )
        else:
            summary = (
                f"No hourly data found for station {station_id} between "
                f"{_iso_z(start_ts)} and {_iso_z(end_ts)}."
            )
        envelope = build_envelope(
            summary_for_llm=summary,
            data_quality_notes=notes,
            fire_ids=fire_ids,
            station_ids=[station_id],
            focus_timestamp=end_ts,
            bbox_focus=_bbox_from_points(points),
            matches=[],
        )
        envelope["timeseries"] = [
            {
                "hour_bucket": _iso_z(_as_utc(row.hour_bucket)),
                "pm25_avg_ug_m3": row.avg_pm25,
                "pm25_max_ug_m3": row.max_pm25,
                "reading_count": row.reading_count,
                "valid_count": row.valid_count,
                "stale_count": row.stale_count,
                "outlier_count": row.outlier_count,
                "wind_speed_kmh": row.wind_speed_10m,
                "wind_direction_deg": row.wind_direction_10m,
                "nearby_fire_count": row.fire_count,
                "nearest_fire_id": row.fire_id,
                "nearest_fire_frp_mw": row.fire_frp,
                "nearest_fire_distance_km": row.fire_distance_km,
            }
            for row in rows
        ]
        return envelope

    @mcp.tool
    def find_worst_air_quality_events(
        start_iso: str,
        end_iso: str,
        limit: int = queries.DEFAULT_EVENT_LIMIT,
    ) -> dict[str, Any]:
        """Rank the top PM2.5 peaks over a window with exact timestamps (spec-04 tool 3).

        Args:
            start_iso: ISO-8601 window start (naive values treated as UTC).
            end_iso: ISO-8601 window end.
            limit: maximum number of ranked station events (default 5).
        """
        start_ts = _parse_iso(start_iso)
        end_ts = _parse_iso(end_iso)
        if end_ts < start_ts:
            raise ValueError("end_iso must not precede start_iso.")
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        cursor = open_cursor()
        try:
            rows = queries.run_worst_air_quality_events(
                cursor,
                start_ts=start_ts,
                end_ts=end_ts,
                limit=limit,
            )
        finally:
            cursor.close()
        events = [
            {
                "station_id": row.station_id,
                "station_name": row.station_name,
                "lat": row.lat,
                "lon": row.lon,
                "pm25_ug_m3": row.pm25,
                "observed_at": _iso_z(_as_utc(row.observed_at)),
                "readings_excluded_stale_or_outlier": row.stale_outlier_excluded,
            }
            for row in rows
        ]
        notes: list[str] = []
        excluded_total = max((row.stale_outlier_excluded for row in rows), default=0)
        if excluded_total:
            notes.append(
                f"{excluded_total} stale/outlier reading(s) across ranked stations were "
                "excluded from the valid-only PM2.5 ranking (preserved in counts per station)."
            )
        if not rows:
            notes.append(
                f"No valid PM2.5 readings between {_iso_z(start_ts)} and {_iso_z(end_ts)}."
            )
        if events:
            leader = events[0]
            summary = (
                f"Top {len(events)} PM2.5 peak(s) between {_iso_z(start_ts)} and "
                f"{_iso_z(end_ts)}: leader {leader['station_name']} ({leader['station_id']}) at "
                f"{leader['pm25_ug_m3']:.1f} ug/m3 observed {leader['observed_at']}."
            )
        else:
            summary = f"No valid PM2.5 peaks between {_iso_z(start_ts)} and {_iso_z(end_ts)}."
        envelope = build_envelope(
            summary_for_llm=summary,
            data_quality_notes=notes,
            fire_ids=[],
            station_ids=sorted({row.station_id for row in rows}),
            focus_timestamp=_as_utc(rows[0].observed_at) if rows else end_ts,
            bbox_focus=_bbox_from_points([(row.lon, row.lat) for row in rows]),
            matches=[],
        )
        envelope["events"] = events
        return envelope

    @mcp.resource("resource://data/freshness")
    def data_freshness() -> str:
        """Per-source ingested-data age plus structural satellite latency (spec-04 section 4)."""
        return json.dumps(_freshness_report(settings), indent=2)

    @mcp.resource("resource://schema/capabilities")
    def schema_capabilities() -> str:
        """Measurement units, PM2.5 reference thresholds, and the datalake footprint."""
        return json.dumps(_capabilities_report(), indent=2)

    return mcp


def _freshness_report(settings: Settings) -> dict[str, Any]:
    """Aggregate the ingestion log into per-source freshness and latency facts."""
    log_path = settings.data_dir / "meta" / "ingestion_log.parquet"
    if not log_path.exists():
        return {"sources": {}, "notes": [INGESTION_LOG_NOTE]}
    cursor = open_cursor()
    try:
        rows = cursor.execute(
            f"SELECT {', '.join(STATION_COLUMNS)} FROM read_parquet(?)",
            [str(log_path)],
        ).fetchall()
    finally:
        cursor.close()
    latest_per_source: dict[str, tuple[Any, ...]] = {}
    for row in rows:
        source = str(row[0])
        if source not in latest_per_source or row[1] > latest_per_source[source][1]:
            latest_per_source[source] = row
    now = datetime.now(UTC)
    sources: dict[str, dict[str, Any]] = {}
    skew: list[str] = []
    quiet: list[str] = []
    for source, row in latest_per_source.items():
        latest_data_ts = _as_utc(row[2]) if row[2] is not None else None
        age_minutes: float | None = None
        if latest_data_ts is not None:
            age_minutes = round((now - latest_data_ts).total_seconds() / 60, 1)
            if age_minutes < 0:
                skew.append(source)
        elif int(row[4]) == 0:
            quiet.append(source)
        sources[source] = {
            "last_run_at": _iso_z(_as_utc(row[1])),
            "latest_data_ts": _iso_z(latest_data_ts) if latest_data_ts is not None else None,
            "age_minutes": age_minutes,
            "known_latency_minutes": row[3],
            "records_written": int(row[4]),
            "status": str(row[5]),
        }
    notes: list[str] = []
    if skew:
        notes.append(
            f"{', '.join(skew)} report data ahead of this host's clock; "
            "age_minutes is approximate."
        )
    if quiet:
        notes.append(
            f"{', '.join(quiet)} has runs without any records written; "
            "its queries return empty results."
        )
    return {"sources": sources, "notes": notes}


def _capabilities_report() -> dict[str, Any]:
    """Document units, PM2.5 reference thresholds, and the data-derived bounds."""
    cursor = open_cursor()
    try:
        rows = cursor.execute(
            "SELECT layer, records, min_lat, max_lat, min_lon, max_lon FROM ("
            "SELECT 'stations' AS layer, COUNT(*) AS records, "
            "MIN(lat) AS min_lat, MAX(lat) AS max_lat, MIN(lon) AS min_lon, MAX(lon) "
            "AS max_lon FROM v_air_quality "
            "UNION ALL SELECT 'active_fires', COUNT(*), MIN(lat), MAX(lat), MIN(lon), MAX(lon) "
            "FROM v_fires "
            "UNION ALL SELECT 'wind_grid', COUNT(*), MIN(lat), MAX(lat), MIN(lon), MAX(lon) "
            "FROM v_weather)"
        ).fetchall()
    finally:
        cursor.close()
    footprint = {
        str(row[0]): {
            "records": int(row[1]),
            "min_lat": row[2],
            "max_lat": row[3],
            "min_lon": row[4],
            "max_lon": row[5],
        }
        for row in rows
    }
    notes: list[str] = []
    if all(info["records"] == 0 for info in footprint.values()):
        notes.append("Datalake views are empty; bounds stay null until ingestion completes.")
    return {
        "units": {
            "pm25": "ug/m3",
            "wind_speed": "km/h (10 m above ground)",
            "wind_direction": "degrees from north, clockwise",
            "fire_radiative_power": "MW",
            "distance": "km",
            "plume_bearing": "degrees (0 = north, clockwise)",
        },
        "pm25_reference_thresholds": [
            {"standard": "WHO 2021 24-hour guideline", "pm25_ug_m3": 15.0},
            {"standard": "EPA 24-hour NAAQS (2024)", "pm25_ug_m3": 35.0},
        ],
        "geographic_bounds": footprint,
        "notes": notes,
    }


def _filter_by_region(
    matches: Sequence[queries.AnalyzeMatch],
    coords: queries.EvidenceCoords,
    region_bbox: Sequence[float],
) -> list[queries.AnalyzeMatch]:
    """Keep matches whose station lies inside the requested bounding box."""
    if len(region_bbox) != 4:
        raise ValueError(
            "region_bbox must carry exactly four values: [min_lon, min_lat, max_lon, max_lat]."
        )
    min_lon, min_lat, max_lon, max_lat = _normalize_bbox(list(region_bbox))
    return [
        match
        for match in matches
        if (coord := coords.stations.get(match.station_id)) is not None
        and min_lon <= coord[0] <= max_lon
        and min_lat <= coord[1] <= max_lat
    ]


def _normalize_bbox(bbox: Sequence[float]) -> tuple[float, float, float, float]:
    """Order a [min_lon, min_lat, max_lon, max_lat] quadruple defensively."""
    return (
        min(bbox[0], bbox[2]),
        min(bbox[1], bbox[3]),
        max(bbox[0], bbox[2]),
        max(bbox[1], bbox[3]),
    )


def _bbox_from_points(
    points: Iterable[tuple[float, float]]
) -> tuple[float, float, float, float] | None:
    """Compute (min_lon, min_lat, max_lon, max_lat) from (lon, lat) points."""
    located = list(points)
    if not located:
        return None
    lons = [lon for lon, _ in located]
    lats = [lat for _, lat in located]
    return (min(lons), min(lats), max(lons), max(lats))


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 instant; naive values are pinned to UTC."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO-8601 timestamp {value!r}.") from exc
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    """Normalize naive datetimes to UTC and rebase aware ones."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso_z(value: datetime) -> str:
    """Render a datetime as an RFC 3339 'Z' timestamp, as in spec-04 examples."""
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _pm25_label(value: float | None) -> str:
    """Format a PM2.5 value with the spec-04 unit, or the no-reading caveat."""
    return f"{value:.1f} ug/m3" if value is not None else "no valid reading"
