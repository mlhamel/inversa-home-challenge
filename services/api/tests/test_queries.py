"""Exact pinned rows from the five spec-03/spec-04 SQL runners."""

from __future__ import annotations

from typing import Any

import pytest
from inversa.api.config import Settings
from inversa.api.db import queries
from inversa.api.db.engine import open_cursor
from scene import ts

T13 = ts(13, 0)
T14 = ts(14, 0)
T15 = ts(15, 0)

DOWN_ROW_STALE: dict[str, Any] = {
    "fire_id": "FIRE-1",
    "fire_frp": 55.0,
    "station_id": "STA-DOWN",
    "station_name": "Downslope Ridge",
    "pm25": 500.0,
    "quality_flag": "stale",
    "distance_km": 55.5,
    "plume_bearing_deg": 180.0,
    "wind_speed_10m": 20.0,
    "angle_diff_deg": 0.0,
}
DOWN_ROW_VALID: dict[str, Any] = {**DOWN_ROW_STALE, "pm25": 85.0, "quality_flag": "valid"}
TIMELINE_ROW: dict[str, Any] = {
    "hour_bucket": ts(13, 0),
    "active_fires_count": 1,
    "avg_pm25": 83.3,
    "max_pm25": 95.0,
    "active_stations": 3,
    "stale_stations": 1,
}
STATION_HOUR_ROW: dict[str, Any] = {
    "hour_bucket": ts(13, 0),
    "avg_pm25": 85.0,
    "max_pm25": 85.0,
    "reading_count": 2,
    "valid_count": 1,
    "stale_count": 1,
    "outlier_count": 0,
    "wind_speed_10m": 15.0,
    "wind_direction_10m": 180.0,
    "fire_count": 1,
    "fire_id": "FIRE-1",
    "fire_frp": 55.0,
    "fire_distance_km": 55.5,
    "station_id": "STA-DOWN",
    "station_name": "Downslope Ridge",
    "station_lat": 37.0,
    "station_lon": -122.0,
}
WORST_ROWS: list[dict[str, Any]] = [
    {
        "station_id": "STA-SIDE",
        "station_name": "Sidewinder Park",
        "lat": 37.4,
        "lon": -121.5,
        "pm25": 95.0,
        "observed_at": ts(13, 55),
        "stale_outlier_excluded": 2,
    },
    {
        "station_id": "STA-DOWN",
        "station_name": "Downslope Ridge",
        "lat": 37.0,
        "lon": -122.0,
        "pm25": 85.0,
        "observed_at": ts(13, 55),
        "stale_outlier_excluded": 2,
    },
    {
        "station_id": "STA-FAR",
        "station_name": "Faraway Flats",
        "lat": 39.0,
        "lon": -118.0,
        "pm25": 70.0,
        "observed_at": ts(13, 55),
        "stale_outlier_excluded": 2,
    },
]


def test_runners_reject_positional_arguments(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        with pytest.raises(TypeError):
            queries.run_analyze_downwind(cursor, T14, 150.0, 25.0)  # type: ignore[call-arg]
    finally:
        cursor.close()


def test_run_analyze_downwind_returns_pinned_matches(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        rows = queries.run_analyze_downwind(cursor, target_ts=T14)
    finally:
        cursor.close()
    assert [row.model_dump() for row in rows] == [DOWN_ROW_STALE, DOWN_ROW_VALID]


def test_run_timeline_summary_returns_pinned_buckets(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        rows = queries.run_timeline_summary(cursor, start_ts=T13, end_ts=T15)
    finally:
        cursor.close()
    assert [row.model_dump() for row in rows] == [TIMELINE_ROW]


def test_run_timeline_summary_empty_before_first_reading(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        rows = queries.run_timeline_summary(cursor, start_ts=ts(12, 0), end_ts=T13)
    finally:
        cursor.close()
    assert rows == []


def test_run_station_timeseries_returns_pinned_profile(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        rows = queries.run_station_timeseries(
            cursor, station_id="STA-DOWN", start_ts=T13, end_ts=T15
        )
    finally:
        cursor.close()
    assert [row.model_dump() for row in rows] == [STATION_HOUR_ROW]


def test_run_worst_air_quality_events_ranks_valid_pm25_only(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        rows = queries.run_worst_air_quality_events(cursor, start_ts=T13, end_ts=T15)
    finally:
        cursor.close()
    assert [row.model_dump() for row in rows] == WORST_ROWS


def test_lookup_evidence_coords_reports_lon_lat_tuples(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        coords = queries.lookup_evidence_coords(
            cursor, fire_ids=["FIRE-1"], station_ids=["STA-DOWN"]
        )
    finally:
        cursor.close()
    assert coords.model_dump() == {
        "fires": {"FIRE-1": (-122.0, 37.5)},
        "stations": {"STA-DOWN": (-122.0, 37.0)},
    }
