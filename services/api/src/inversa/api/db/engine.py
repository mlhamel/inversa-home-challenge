"""In-memory DuckDB engine with deduplicated logical views over the Parquet datalake."""

from __future__ import annotations

import glob
import threading

import duckdb
from inversa.api.config import Settings, load_settings

VIEW_NAMES: dict[str, str] = {
    "fires": "v_fires",
    "air_quality": "v_air_quality",
    "weather": "v_weather",
}


def initialize_engine(settings: Settings) -> duckdb.DuckDBPyConnection:
    """Boot the in-memory engine singleton and materialize its logical views."""
    global _ENGINE, _SETTINGS
    with _ENGINE_LOCK:
        if _ENGINE is None:
            connection = _connect()
            _create_views(connection, settings)
            _ENGINE = connection
            _SETTINGS = settings
        return _ENGINE


def get_engine(settings: Settings | None = None) -> duckdb.DuckDBPyConnection:
    """Return the booted engine, lazily initializing on first use."""
    if _ENGINE is None:
        return initialize_engine(settings or load_settings())
    return _ENGINE


def active_settings() -> Settings:
    """Return the settings the engine was booted with."""
    if _SETTINGS is None:
        raise RuntimeError("Engine not initialized: call initialize_engine() first.")
    return _SETTINGS


def close_engine() -> None:
    """Close and forget the engine singleton."""
    global _ENGINE, _SETTINGS
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            _ENGINE.close()
            _ENGINE = None
            _SETTINGS = None


def open_cursor() -> duckdb.DuckDBPyConnection:
    """Acquire an isolated cursor pinned to UTC and the spec axis order.

    DuckDB cursors do not inherit connection-level SETTINGS, and the spatial
    extension's ``geometry_always_xy`` only resolves once ``LOAD spatial`` is
    cataloged; ``false`` keeps lon/lat as stored and makes the spec's
    ``ST_Distance_Spheroid(...) ST_Point(lat, lon) ...`` queries correct.
    Fails fast when the engine was never initialized instead of silently
    booting from ambient environment settings.
    """
    if _ENGINE is None:
        raise RuntimeError(
            "Engine not initialized: the app lifespan or the test fixture must call "
            "initialize_engine() first."
        )
    cursor = _ENGINE.cursor()
    cursor.execute("SET TimeZone='UTC'")
    cursor.execute("SET geometry_always_xy=false")
    return cursor


_ENGINE: duckdb.DuckDBPyConnection | None = None
_SETTINGS: Settings | None = None
_ENGINE_LOCK = threading.Lock()

_DEDUP_KEYS: dict[str, tuple[str, ...]] = {
    "fires": ("fire_id",),
    "air_quality": ("measurement_id",),
    "weather": ("grid_id", "observed_at"),
}

_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "fires": (
        ("fire_id", "VARCHAR"),
        ("observed_at", "TIMESTAMPTZ"),
        ("ingested_at", "TIMESTAMPTZ"),
        ("lat", "DOUBLE"),
        ("lon", "DOUBLE"),
        ("frp", "REAL"),
        ("confidence", "VARCHAR"),
        ("satellite", "VARCHAR"),
    ),
    "air_quality": (
        ("measurement_id", "VARCHAR"),
        ("station_id", "VARCHAR"),
        ("station_name", "VARCHAR"),
        ("observed_at", "TIMESTAMPTZ"),
        ("ingested_at", "TIMESTAMPTZ"),
        ("lat", "DOUBLE"),
        ("lon", "DOUBLE"),
        ("pm25", "REAL"),
        ("quality_flag", "VARCHAR"),
    ),
    "weather": (
        ("grid_id", "VARCHAR"),
        ("observed_at", "TIMESTAMPTZ"),
        ("ingested_at", "TIMESTAMPTZ"),
        ("lat", "DOUBLE"),
        ("lon", "DOUBLE"),
        ("wind_speed_10m", "REAL"),
        ("wind_direction_10m", "REAL"),
        ("boundary_layer_height", "REAL"),
    ),
}


def _connect() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("LOAD spatial")
    except duckdb.Error:
        connection.execute("INSTALL spatial")
        connection.execute("LOAD spatial")
    return connection


def _create_views(connection: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    for table, view in VIEW_NAMES.items():
        pattern = str(settings.data_dir / table / "date=*" / "*.parquet")
        if glob.glob(pattern):
            connection.execute(_dedup_view_ddl(table, view, pattern))
        else:
            connection.execute(_empty_stub_ddl(table, view))


def _dedup_view_ddl(table: str, view: str, pattern: str) -> str:
    keys = ", ".join(_DEDUP_KEYS[table])
    return (
        f"CREATE OR REPLACE VIEW {view} AS "
        f"SELECT * FROM read_parquet('{pattern}', union_by_name=true) "
        f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {keys} ORDER BY ingested_at DESC) = 1"
    )


def _empty_stub_ddl(table: str, view: str) -> str:
    columns = ", ".join(
        f"CAST(NULL AS {sql_type}) AS {name}" for name, sql_type in _COLUMNS[table]
    )
    return f"CREATE OR REPLACE VIEW {view} AS SELECT {columns} WHERE FALSE"
