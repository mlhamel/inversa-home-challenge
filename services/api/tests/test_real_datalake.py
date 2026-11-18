"""Envelope validation against the real local datalake; skipped when ./.local_datalake is absent."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastmcp import FastMCP
from inversa.api.config import Settings, load_settings
from inversa.api.db.engine import (
    VIEW_NAMES,
    active_settings,
    close_engine,
    initialize_engine,
    open_cursor,
)
from inversa.api.mcp.server import build_mcp
from mcp_client import call_tool, read_resource
from test_mcp_tools import END, RES_CAPS, START, T1_EMPTY, T2_NO_DATA, TS

REAL_SETTINGS = load_settings()

requires_datalake = pytest.mark.skipif(
    not REAL_SETTINGS.data_dir.exists(),
    reason="the local datalake is absent; rerun the phase-2 ingestion backfill to enable",
)
pytestmark = requires_datalake

FRESH_LATENCY: dict[str, int] = {"nasa_firms": 180, "openaq": 15, "open_meteo": 0}
INGESTION_STATUSES = {"success", "partial", "failed"}  # written by inversa.ingestion.storage
ENVELOPE_KEYS = {"summary_for_llm", "data_quality_notes", "evidence_refs", "matches", "events"}
EVENT_KEYS = {
    "station_id",
    "station_name",
    "lat",
    "lon",
    "pm25_ug_m3",
    "observed_at",
    "readings_excluded_stale_or_outlier",
}
SOURCE_KEYS = {
    "last_run_at",
    "latest_data_ts",
    "age_minutes",
    "known_latency_minutes",
    "records_written",
    "status",
}
BOUNDS_KEYS = {"records", "min_lat", "max_lat", "min_lon", "max_lon"}


@pytest.fixture
def real_engine() -> Iterator[Settings]:
    """Boot the engine singleton on the real local datalake and guarantee teardown."""
    close_engine()
    initialize_engine(REAL_SETTINGS)
    yield REAL_SETTINGS
    close_engine()


@pytest.fixture
def real_mcp(real_engine: Settings) -> Iterator[FastMCP]:
    """Expose the FastMCP tool surface backed by the real local datalake."""
    yield build_mcp(real_engine)


def test_engine_boots_on_the_real_datalake(real_engine: Settings) -> None:
    """The in-memory engine comes up over the phase-2 files without extra configuration."""
    assert active_settings() == REAL_SETTINGS


def test_source_folders_back_the_logical_views(real_engine: Settings) -> None:
    """A view counts zero rows exactly when its date-partitioned source folder is empty."""
    counts: dict[str, int] = {}
    cursor = open_cursor()
    try:
        for table, view in VIEW_NAMES.items():
            row = cursor.execute(f"SELECT count(*) FROM {view}").fetchone()
            assert row is not None
            counts[table] = row[0]
    finally:
        cursor.close()
    for table in VIEW_NAMES:
        batches = list((REAL_SETTINGS.data_dir / table).glob("date=*/*.parquet"))
        assert (counts[table] == 0) == (not batches), table


def test_tool1_reports_no_downwind_impact_without_fires(real_mcp: FastMCP) -> None:
    """With no fires ingested the analyze envelope is empty but fully shaped."""
    if list((REAL_SETTINGS.data_dir / "fires").glob("date=*/*.parquet")):
        pytest.skip("the fires backfill has run; the empty-envelope pins no longer hold")
    assert (
        call_tool(real_mcp, "analyze_downwind_impact", {"timestamp_iso": TS})
        == T1_EMPTY
    )


def test_tool2_unknown_station_reports_no_data(real_mcp: FastMCP) -> None:
    """STA-NONE exists in no datalake, so the real lake yields the no-records envelope."""
    assert (
        call_tool(
            real_mcp,
            "get_station_timeseries",
            {"station_id": "STA-NONE", "start_iso": START, "end_iso": END},
        )
        == T2_NO_DATA
    )


def test_tool3_envelope_shape_on_the_real_lake(real_mcp: FastMCP) -> None:
    """Whatever the backfill ingested, the worst-events envelope stays structurally honest."""
    payload = call_tool(
        real_mcp, "find_worst_air_quality_events", {"start_iso": START, "end_iso": END}
    )
    assert set(payload) == ENVELOPE_KEYS
    peaks = [event["pm25_ug_m3"] for event in payload["events"]]
    assert peaks == sorted(peaks, reverse=True)
    for event in payload["events"]:
        assert set(event) == EVENT_KEYS
    bbox = payload["evidence_refs"].get("bbox_focus")
    if bbox is not None:
        assert len(bbox) == 4
    if payload["events"]:
        assert payload["evidence_refs"]["focus_timestamp"] == payload["events"][0]["observed_at"]


def test_freshness_pins_per_source_latency(real_mcp: FastMCP) -> None:
    """Real ingested data keeps the source latency contract regardless of backfill volume."""
    payload = read_resource(real_mcp, "resource://data/freshness")
    assert set(payload) == {"sources", "notes"}
    assert set(payload["sources"]) == set(FRESH_LATENCY)
    for name, expected in FRESH_LATENCY.items():
        source = payload["sources"][name]
        assert set(source) == SOURCE_KEYS, name
        assert source["known_latency_minutes"] == expected, name
        assert source["status"] in INGESTION_STATUSES, name
        assert isinstance(source["last_run_at"], str)
        if source["latest_data_ts"] is None:
            assert source["records_written"] == 0
            assert source["age_minutes"] is None
        else:
            assert isinstance(source["age_minutes"], float)


def test_capabilities_units_thresholds_and_bounds_shape(real_mcp: FastMCP) -> None:
    """Units and thresholds are spec constants; bounds stay data-shaped over the real lake."""
    payload = read_resource(real_mcp, "resource://schema/capabilities")
    assert set(payload) == set(RES_CAPS)
    assert payload["units"] == RES_CAPS["units"]
    assert payload["pm25_reference_thresholds"] == RES_CAPS["pm25_reference_thresholds"]
    bounds = payload["geographic_bounds"]
    assert set(bounds) == {"stations", "active_fires", "wind_grid"}
    for layer, info in bounds.items():
        assert set(info) == BOUNDS_KEYS, layer
        if info["records"] > 0:
            for key in ("min_lat", "max_lat", "min_lon", "max_lon"):
                assert isinstance(info[key], float), f"{layer}.{key}"
        else:
            assert info["min_lat"] is None, layer
