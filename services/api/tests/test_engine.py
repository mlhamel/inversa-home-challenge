"""Engine lifecycle, per-cursor axis pinning, dedup views, and stub fallbacks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import pytest
from inversa.api.config import Settings
from inversa.api.db.engine import (
    active_settings,
    close_engine,
    get_engine,
    initialize_engine,
    open_cursor,
)
from inversa.ingestion.contract import AIR_QUALITY_SCHEMA
from inversa.ingestion.storage import record_batch
from scene import RUN_AT, ts

CURSOR_NOT_INITIALIZED = (
    "Engine not initialized: the app lifespan or the test fixture "
    "must call initialize_engine() first."
)
SETTINGS_NOT_INITIALIZED = "Engine not initialized: call initialize_engine() first."


def scalar(cursor: duckdb.DuckDBPyConnection, sql: str) -> Any:
    row = cursor.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_open_cursor_fails_fast_before_initialization() -> None:
    close_engine()
    with pytest.raises(RuntimeError, match=re.escape(CURSOR_NOT_INITIALIZED)):
        open_cursor()


def test_active_settings_fails_fast_before_initialization() -> None:
    close_engine()
    with pytest.raises(RuntimeError, match=re.escape(SETTINGS_NOT_INITIALIZED)):
        active_settings()


def test_initialize_engine_is_idempotent(booted_engine: Settings) -> None:
    booted = get_engine(booted_engine)
    assert initialize_engine(booted_engine) is booted
    assert active_settings() == booted_engine


def test_close_engine_is_idempotent(booted_engine: Settings) -> None:
    close_engine()
    close_engine()
    with pytest.raises(RuntimeError, match=re.escape(CURSOR_NOT_INITIALIZED)):
        open_cursor()


def test_open_cursor_pins_utc_and_spec_axis_order(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        distance_km = scalar(
            cursor,
            "SELECT ST_Distance_Spheroid(ST_Point(37.5, -122.0), ST_Point(37.0, -122.0)) / 1000.0",
        )
        bearing_deg = scalar(
            cursor, "SELECT degrees(ST_Azimuth(ST_Point(-122.0, 37.5), ST_Point(-122.0, 37.0)))"
        )
        timezone = scalar(cursor, "SELECT current_setting('TimeZone')")
        always_xy = scalar(cursor, "SELECT current_setting('geometry_always_xy')")
    finally:
        cursor.close()
    assert distance_km == pytest.approx(55.49116779542044)
    assert bearing_deg == pytest.approx(180.0)
    assert timezone == "UTC"
    assert always_xy is False


def test_logical_views_keep_latest_ingested_per_key(booted_engine: Settings) -> None:
    cursor = open_cursor()
    try:
        fires = cursor.execute("SELECT fire_id, frp FROM v_fires ORDER BY fire_id").fetchall()
        air_rows = scalar(cursor, "SELECT count(*) FROM v_air_quality")
        weather = cursor.execute(
            "SELECT grid_id, observed_at, boundary_layer_height "
            "FROM v_weather ORDER BY grid_id, observed_at"
        ).fetchall()
    finally:
        cursor.close()
    assert fires == [("FIRE-1", 55.0), ("FIRE-2", 80.0)]
    assert air_rows == 5
    assert weather == [
        ("WX-DOWN", ts(13, 58), 400.0),
        ("WX-DOWN", ts(14, 50), 350.0),
        ("WX-HOME", ts(13, 45), 600.0),
    ]


def test_missing_source_tables_boot_as_empty_stubs(tmp_path: Path) -> None:
    air_only = pl.DataFrame(
        [
            {
                "measurement_id": "MSOLO",
                "station_id": "STA-SOLO",
                "station_name": "Solo Post",
                "observed_at": RUN_AT,
                "ingested_at": None,
                "lat": 37.0,
                "lon": -122.0,
                "pm25": 42.0,
                "quality_flag": "valid",
            }
        ],
        schema=AIR_QUALITY_SCHEMA,
    )
    record_batch(air_only, root=tmp_path, source="openaq", run_at=RUN_AT)
    close_engine()
    initialize_engine(Settings(data_dir=tmp_path))
    cursor = open_cursor()
    try:
        fire_rows = scalar(cursor, "SELECT count(*) FROM v_fires")
        air_rows = scalar(cursor, "SELECT count(*) FROM v_air_quality")
    finally:
        cursor.close()
    close_engine()
    assert fire_rows == 0
    assert air_rows == 1
