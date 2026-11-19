"""Canonical DuckDB queries (spec-03 §3) plus spec-04 MCP tool query helpers.

Runners receive an isolated cursor from :func:`inversa.api.db.engine.open_cursor`
so every statement executes under UTC and the lon/lat axis order the spec SQL
was written for.
"""

from __future__ import annotations

from datetime import datetime
from importlib import resources
from threading import Lock
from typing import Any

import duckdb
from pydantic import BaseModel, ConfigDict

DEFAULT_RADIUS_KM: float = 150.0
DEFAULT_CONE_HALF_ANGLE: float = 25.0
DEFAULT_EVENT_LIMIT: int = 5
SNAPSHOT_FIRE_WINDOW_HOURS: int = 4


class AnalyzeMatch(BaseModel):
    """One fire -> wind -> station correlation row from analyze_downwind.sql."""

    model_config = ConfigDict(frozen=True)

    fire_id: str
    fire_frp: float | None
    station_id: str
    station_name: str
    pm25: float | None
    quality_flag: str
    distance_km: float
    plume_bearing_deg: float
    wind_speed_10m: float
    angle_diff_deg: float


class TimelineRow(BaseModel):
    """One hourly bucket of the pre-aggregated timeline summary."""

    model_config = ConfigDict(frozen=True)

    hour_bucket: datetime
    active_fires_count: int
    avg_pm25: float | None
    max_pm25: float | None
    active_stations: int
    stale_stations: int


class StationHourRow(BaseModel):
    """One hourly bucket for a station: PM2.5 stats, wind vector, nearby fires."""

    model_config = ConfigDict(frozen=True)

    hour_bucket: datetime
    avg_pm25: float | None
    max_pm25: float | None
    reading_count: int
    valid_count: int
    stale_count: int
    outlier_count: int
    wind_speed_10m: float | None
    wind_direction_10m: float | None
    fire_count: int
    fire_id: str | None
    fire_frp: float | None
    fire_distance_km: float | None
    station_id: str
    station_name: str
    station_lat: float
    station_lon: float


class WorstEventRow(BaseModel):
    """One per-station peak PM2.5 event with its exact reading timestamp."""

    model_config = ConfigDict(frozen=True)

    station_id: str
    station_name: str
    lat: float
    lon: float
    pm25: float
    observed_at: datetime
    stale_outlier_excluded: int


class SnapshotFireRow(BaseModel):
    """One FIRMS active-fire detection inside the snapshot's trailing 4 h window."""

    model_config = ConfigDict(frozen=True)

    fire_id: str
    observed_at: datetime
    lat: float
    lon: float
    frp: float | None
    confidence: str
    satellite: str


class SnapshotStationRow(BaseModel):
    """One OpenAQ station's latest reading at/before the target instant."""

    model_config = ConfigDict(frozen=True)

    station_id: str
    station_name: str
    lat: float
    lon: float
    pm25: float | None
    quality_flag: str
    observed_at: datetime


class SnapshotWindRow(BaseModel):
    """One Open-Meteo grid point's latest wind vector and boundary-layer height."""

    model_config = ConfigDict(frozen=True)

    grid_id: str
    observed_at: datetime
    lat: float
    lon: float
    wind_speed_10m: float | None
    wind_direction_10m: float | None
    boundary_layer_height: float | None


class SnapshotRegion(BaseModel):
    """One configured study area exposed to the map as a rect outline."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    bbox: tuple[float, float, float, float]


class Snapshot(BaseModel):
    """The three map layers rendered at one instant (spec-05 section 1)."""

    model_config = ConfigDict(frozen=True)

    fires: list[SnapshotFireRow]
    stations: list[SnapshotStationRow]
    wind: list[SnapshotWindRow]
    regions: list[SnapshotRegion] = []


class EvidenceCoords(BaseModel):
    """Resolved coordinates for the ids referenced by an envelope's evidence refs."""

    model_config = ConfigDict(frozen=True)

    fires: dict[str, tuple[float, float]]
    stations: dict[str, tuple[float, float]]


def run_analyze_downwind(
    cursor: duckdb.DuckDBPyConnection,
    *,
    target_ts: datetime,
    radius_km: float = DEFAULT_RADIUS_KM,
    cone_half_angle: float = DEFAULT_CONE_HALF_ANGLE,
) -> list[AnalyzeMatch]:
    """Execute spec-03 §3.1 verbatim and return fire->wind->station matches."""
    rows = _fetch(
        cursor,
        _load_sql("analyze_downwind.sql"),
        {
            "target_ts": target_ts,
            "radius_km": radius_km,
            "cone_half_angle": cone_half_angle,
        },
    )
    return [
        AnalyzeMatch(
            fire_id=row[0],
            fire_frp=row[1],
            station_id=row[2],
            station_name=row[3],
            pm25=row[4],
            quality_flag=row[5],
            distance_km=row[6],
            plume_bearing_deg=row[7],
            wind_speed_10m=row[8],
            angle_diff_deg=row[9],
        )
        for row in rows
    ]


def run_timeline_summary(
    cursor: duckdb.DuckDBPyConnection,
    *,
    start_ts: datetime,
    end_ts: datetime,
) -> list[TimelineRow]:
    """Execute spec-03 §3.2 verbatim and return hourly timeline buckets."""
    rows = _fetch(
        cursor,
        _load_sql("timeline_summary.sql"),
        {"start_ts": start_ts, "end_ts": end_ts},
    )
    return [
        TimelineRow(
            hour_bucket=row[0],
            active_fires_count=row[1],
            avg_pm25=row[2],
            max_pm25=row[3],
            active_stations=row[4],
            stale_stations=row[5],
        )
        for row in rows
    ]


def run_snapshot(
    cursor: duckdb.DuckDBPyConnection,
    *,
    target_ts: datetime,
    fire_window_hours: int = SNAPSHOT_FIRE_WINDOW_HOURS,
) -> Snapshot:
    """Return the spec-05 map state at one instant: trailing fires, latest stations, wind."""
    fires = [
        SnapshotFireRow(
            fire_id=row[0],
            observed_at=row[1],
            lat=row[2],
            lon=row[3],
            frp=row[4],
            confidence=row[5],
            satellite=row[6],
        )
        for row in _fetch(cursor, _load_sql("snapshot_fires.sql"), {"target_ts": target_ts})
    ]
    stations = [
        SnapshotStationRow(
            station_id=row[0],
            station_name=row[1],
            lat=row[2],
            lon=row[3],
            pm25=row[4],
            quality_flag=row[5],
            observed_at=row[6],
        )
        for row in _fetch(cursor, _load_sql("snapshot_stations.sql"), {"target_ts": target_ts})
    ]
    wind = [
        SnapshotWindRow(
            grid_id=row[0],
            observed_at=row[1],
            lat=row[2],
            lon=row[3],
            wind_speed_10m=row[4],
            wind_direction_10m=row[5],
            boundary_layer_height=row[6],
        )
        for row in _fetch(cursor, _load_sql("snapshot_wind.sql"), {"target_ts": target_ts})
    ]
    return Snapshot(fires=fires, stations=stations, wind=wind)


def run_station_timeseries(
    cursor: duckdb.DuckDBPyConnection,
    *,
    station_id: str,
    start_ts: datetime,
    end_ts: datetime,
) -> list[StationHourRow]:
    """Execute the spec-04 tool 2 query and return the station's hourly profile."""
    rows = _fetch(
        cursor,
        _load_sql("station_timeseries.sql"),
        {"station_id": station_id, "start_ts": start_ts, "end_ts": end_ts},
    )
    return [
        StationHourRow(
            hour_bucket=row[0],
            avg_pm25=row[1],
            max_pm25=row[2],
            reading_count=row[3],
            valid_count=row[4],
            stale_count=row[5],
            outlier_count=row[6],
            wind_speed_10m=row[7],
            wind_direction_10m=row[8],
            fire_count=row[9],
            fire_id=row[10],
            fire_frp=row[11],
            fire_distance_km=row[12],
            station_id=row[13],
            station_name=row[14],
            station_lat=row[15],
            station_lon=row[16],
        )
        for row in rows
    ]


def run_worst_air_quality_events(
    cursor: duckdb.DuckDBPyConnection,
    *,
    start_ts: datetime,
    end_ts: datetime,
    limit: int = DEFAULT_EVENT_LIMIT,
) -> list[WorstEventRow]:
    """Execute the spec-04 tool 3 query and return the ranked PM2.5 peaks."""
    rows = _fetch(
        cursor,
        _load_sql("worst_air_quality_events.sql"),
        {"start_ts": start_ts, "end_ts": end_ts, "limit": limit},
    )
    return [
        WorstEventRow(
            station_id=row[0],
            station_name=row[1],
            lat=row[2],
            lon=row[3],
            pm25=row[4],
            observed_at=row[5],
            stale_outlier_excluded=row[6],
        )
        for row in rows
    ]


def lookup_evidence_coords(
    cursor: duckdb.DuckDBPyConnection,
    *,
    fire_ids: list[str],
    station_ids: list[str],
) -> EvidenceCoords:
    """Resolve lat/lon for named fire and station ids (lon, lat tuples)."""
    fires: dict[str, tuple[float, float]] = {}
    stations: dict[str, tuple[float, float]] = {}
    if not fire_ids and not station_ids:
        return EvidenceCoords(fires=fires, stations=stations)
    rows = _fetch(
        cursor,
        _load_sql("evidence_coords.sql"),
        {"fire_ids": fire_ids, "station_ids": station_ids},
    )
    for row in rows:
        kind, identifier, lat, lon = row[0], row[1], row[2], row[3]
        coord = (float(lon), float(lat))
        if kind == "fire":
            fires[str(identifier)] = coord
        else:
            stations[str(identifier)] = coord
    return EvidenceCoords(fires=fires, stations=stations)


_SQL_CACHE: dict[str, str] = {}
_SQL_LOCK = Lock()


def _fetch(
    cursor: duckdb.DuckDBPyConnection,
    sql: str,
    params: dict[str, Any],
) -> list[tuple[Any, ...]]:
    return cursor.execute(sql, params).fetchall()


def _load_sql(name: str) -> str:
    with _SQL_LOCK:
        cached = _SQL_CACHE.get(name)
        if cached is not None:
            return cached
        sql = resources.files("inversa.api.db.queries").joinpath(name).read_text(encoding="utf-8")
        _SQL_CACHE[name] = sql
        return sql
