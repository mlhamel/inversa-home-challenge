"""Shared fixtures: a synthetic datalake exercising every query behavior."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
from fastmcp import FastMCP
from inversa.api.config import Settings
from inversa.api.db.engine import close_engine, initialize_engine
from inversa.api.mcp.server import build_mcp
from inversa.ingestion.contract import AIR_QUALITY_SCHEMA, FIRES_SCHEMA, WEATHER_SCHEMA
from inversa.ingestion.storage import record_batch
from scene import RUN_AT, STATION_NAMES, ts


def _write_scene(root: Path) -> None:
    fires = pl.DataFrame(
        [
            {
                "fire_id": "FIRE-1",
                "observed_at": ts(13, 55),
                "ingested_at": ts(13, 56),
                "lat": 37.5,
                "lon": -122.0,
                "frp": 40.0,
                "confidence": "nominal",
                "satellite": "VIIRS-375",
            },
            {
                "fire_id": "FIRE-1",
                "observed_at": ts(13, 55),
                "ingested_at": ts(13, 58),
                "lat": 37.5,
                "lon": -122.0,
                "frp": 55.0,
                "confidence": "nominal",
                "satellite": "VIIRS-375",
            },
            {
                "fire_id": "FIRE-2",
                "observed_at": ts(13, 50),
                "ingested_at": ts(13, 51),
                "lat": 37.1,
                "lon": -121.9,
                "frp": 80.0,
                "confidence": "low",
                "satellite": "VIIRS-375",
            },
        ],
        schema=FIRES_SCHEMA,
    )
    air_quality = pl.DataFrame(
        [
            {
                "measurement_id": "MDOWN-STALE",
                "station_id": "STA-DOWN",
                "station_name": STATION_NAMES["STA-DOWN"],
                "observed_at": ts(13, 20),
                "ingested_at": ts(13, 25),
                "lat": 37.0,
                "lon": -122.0,
                "pm25": 500.0,
                "quality_flag": "stale",
            },
            {
                "measurement_id": "MDOWN-VALID",
                "station_id": "STA-DOWN",
                "station_name": STATION_NAMES["STA-DOWN"],
                "observed_at": ts(13, 55),
                "ingested_at": ts(13, 59),
                "lat": 37.0,
                "lon": -122.0,
                "pm25": 80.0,
                "quality_flag": "valid",
            },
            {
                "measurement_id": "MDOWN-VALID",
                "station_id": "STA-DOWN",
                "station_name": STATION_NAMES["STA-DOWN"],
                "observed_at": ts(13, 55),
                "ingested_at": ts(14, 0),
                "lat": 37.0,
                "lon": -122.0,
                "pm25": 85.0,
                "quality_flag": "valid",
            },
            {
                "measurement_id": "MSIDE-VALID",
                "station_id": "STA-SIDE",
                "station_name": STATION_NAMES["STA-SIDE"],
                "observed_at": ts(13, 55),
                "ingested_at": ts(13, 56),
                "lat": 37.4,
                "lon": -121.5,
                "pm25": 95.0,
                "quality_flag": "valid",
            },
            {
                "measurement_id": "MFAR-VALID",
                "station_id": "STA-FAR",
                "station_name": STATION_NAMES["STA-FAR"],
                "observed_at": ts(13, 55),
                "ingested_at": ts(13, 56),
                "lat": 39.0,
                "lon": -118.0,
                "pm25": 70.0,
                "quality_flag": "valid",
            },
            {
                "measurement_id": "MFAR-OUTLIER",
                "station_id": "STA-FAR",
                "station_name": STATION_NAMES["STA-FAR"],
                "observed_at": ts(13, 15),
                "ingested_at": ts(13, 16),
                "lat": 39.0,
                "lon": -118.0,
                "pm25": 9000.0,
                "quality_flag": "outlier",
            },
        ],
        schema=AIR_QUALITY_SCHEMA,
    )
    weather = pl.DataFrame(
        [
            {
                "grid_id": "WX-HOME",
                "observed_at": ts(13, 45),
                "ingested_at": ts(13, 46),
                "lat": 37.5,
                "lon": -122.0,
                "wind_speed_10m": 20.0,
                "wind_direction_10m": 0.0,
                "boundary_layer_height": 500.0,
            },
            {
                "grid_id": "WX-HOME",
                "observed_at": ts(13, 45),
                "ingested_at": ts(13, 50),
                "lat": 37.5,
                "lon": -122.0,
                "wind_speed_10m": 20.0,
                "wind_direction_10m": 0.0,
                "boundary_layer_height": 600.0,
            },
            {
                "grid_id": "WX-DOWN",
                "observed_at": ts(13, 58),
                "ingested_at": ts(13, 59),
                "lat": 37.0,
                "lon": -122.0,
                "wind_speed_10m": 15.0,
                "wind_direction_10m": 180.0,
                "boundary_layer_height": 400.0,
            },
            {
                "grid_id": "WX-DOWN",
                "observed_at": ts(14, 50),
                "ingested_at": ts(14, 51),
                "lat": 37.0,
                "lon": -122.0,
                "wind_speed_10m": 12.0,
                "wind_direction_10m": 90.0,
                "boundary_layer_height": 350.0,
            },
        ],
        schema=WEATHER_SCHEMA,
    )
    record_batch(fires, root=root, source="nasa_firms", region="default", run_at=RUN_AT)
    record_batch(air_quality, root=root, source="openaq", region="default", run_at=RUN_AT)
    record_batch(weather, root=root, source="open_meteo", region="default", run_at=RUN_AT)


@pytest.fixture
def scene_dir(tmp_path: Path) -> Path:
    """A datalake covering dedup, ASOF pick, cone math, and quality flags."""
    _write_scene(tmp_path)
    return tmp_path


@pytest.fixture
def api_settings(scene_dir: Path) -> Settings:
    return Settings(data_dir=scene_dir)


@pytest.fixture
def mcp_server(api_settings: Settings) -> Iterator[FastMCP]:
    """Boot the engine on the scene and expose the FastMCP tool surface in-process."""
    close_engine()
    initialize_engine(api_settings)
    yield build_mcp(api_settings)
    close_engine()


@pytest.fixture
def booted_engine(api_settings: Settings) -> Iterator[Settings]:
    """Boot the engine singleton on the scene and guarantee teardown."""
    close_engine()
    initialize_engine(api_settings)
    yield api_settings
    close_engine()
