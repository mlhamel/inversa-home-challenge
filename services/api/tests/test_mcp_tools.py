"""Envelope pins for the four FastMCP tools and both spec-04 resources."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastmcp.exceptions import ToolError
from inversa.api.mcp.server import FIRMS_LATENCY_NOTE
from mcp_client import call_tool, read_resource

TS = "2026-11-17T14:00:00Z"
START = "2026-11-17T13:00:00Z"
END = "2026-11-17T15:00:00Z"
EARLY_START = "2026-11-17T12:00:00Z"
EARLY_END = "2026-11-17T13:00:00Z"

MATCH_STALE: dict[str, Any] = {
    "fire_id": "FIRE-1",
    "fire_frp": 55.0,
    "station_id": "STA-DOWN",
    "station_name": "Downslope Ridge",
    "pm25": 500.0,
    "quality_flag": "QUALITY_FLAG_STALE",
    "distance_km": 55.5,
    "plume_bearing_deg": 180.0,
    "wind_speed_10m": 20.0,
    "angle_diff_deg": 0.0,
}
MATCH_VALID: dict[str, Any] = {**MATCH_STALE, "pm25": 85.0, "quality_flag": "QUALITY_FLAG_VALID"}
STALE_NOTE = (
    "1 retained station reading(s) are stale or missing PM2.5 (STA-DOWN); those matches "
    "keep the raw PM2.5 under a non-valid quality flag, so treat them as no-data."
)
UNCONSTRAINED_NOTE = (
    "No fire -> station downwind correlations met the constraints at this timestamp."
)
T1_HIT: dict[str, Any] = {
    "summary_for_llm": (
        "2 fire->station downwind correlation(s) for 2026-11-17T14:00:00Z: 1 active fire(s) "
        "feeding 1 station(s) within 150 km of a +/-25 degree plume cone. Closest link: "
        "Downslope Ridge (STA-DOWN) downwind of FIRE-1 at 55.5 km, plume bearing 180.0 deg, "
        "wind 20.0 km/h, PM2.5 500.0 ug/m3."
    ),
    "data_quality_notes": [FIRMS_LATENCY_NOTE, STALE_NOTE],
    "evidence_refs": {
        "fire_ids": ["FIRE-1"],
        "station_ids": ["STA-DOWN"],
        "focus_timestamp": TS,
        "bbox_focus": [-122.0, 37.0, -122.0, 37.5],
    },
    "matches": [MATCH_STALE, MATCH_VALID],
}
T1_EMPTY: dict[str, Any] = {
    "summary_for_llm": (
        "No downwind impact correlations at 2026-11-17T14:00:00Z within 150 km and a +/-25 "
        "degree plume cone."
    ),
    "data_quality_notes": [FIRMS_LATENCY_NOTE, UNCONSTRAINED_NOTE],
    "evidence_refs": {"focus_timestamp": TS, "fire_ids": [], "station_ids": []},
    "matches": [],
}
STATION_BUCKET: dict[str, Any] = {
    "hour_bucket": "2026-11-17T13:00:00Z",
    "pm25_avg_ug_m3": 85.0,
    "pm25_max_ug_m3": 85.0,
    "reading_count": 2,
    "valid_count": 1,
    "stale_count": 1,
    "outlier_count": 0,
    "wind_speed_kmh": 15.0,
    "wind_direction_deg": 180.0,
    "nearby_fire_count": 1,
    "nearest_fire_id": "FIRE-1",
    "nearest_fire_frp_mw": 55.0,
    "nearest_fire_distance_km": 55.5,
}
WIND_ONLY_BUCKET: dict[str, Any] = {
    "hour_bucket": "2026-11-17T14:00:00Z",
    "pm25_avg_ug_m3": None,
    "pm25_max_ug_m3": None,
    "reading_count": 0,
    "valid_count": 0,
    "stale_count": 0,
    "outlier_count": 0,
    "wind_speed_kmh": 12.0,
    "wind_direction_deg": 90.0,
    "nearby_fire_count": 0,
    "nearest_fire_id": None,
    "nearest_fire_frp_mw": None,
    "nearest_fire_distance_km": None,
}
T2_HIT: dict[str, Any] = {
    "summary_for_llm": (
        "Hourly PM2.5 profile for Downslope Ridge (STA-DOWN) between 2026-11-17T13:00:00Z and "
        "2026-11-17T15:00:00Z: 2 hourly bucket(s); peak 85.0 ug/m3."
    ),
    "data_quality_notes": [
        "1 stale and 0 outlier reading(s) in the window are kept in per-hour counts but "
        "excluded from PM2.5 averages (transparency rule)."
    ],
    "evidence_refs": {
        "fire_ids": ["FIRE-1"],
        "station_ids": ["STA-DOWN"],
        "focus_timestamp": END,
        "bbox_focus": [-122.0, 37.0, -122.0, 37.5],
    },
    "matches": [],
    "timeseries": [STATION_BUCKET, WIND_ONLY_BUCKET],
}
T2_NO_DATA: dict[str, Any] = {
    "summary_for_llm": (
        f"No hourly data found for station STA-NONE between {START} and {END}."
    ),
    "data_quality_notes": ["Station STA-NONE returned no records for the requested window."],
    "evidence_refs": {"station_ids": ["STA-NONE"], "focus_timestamp": END, "fire_ids": []},
    "matches": [],
    "timeseries": [],
}
EVENT_SIDE: dict[str, Any] = {
    "station_id": "STA-SIDE",
    "station_name": "Sidewinder Park",
    "lat": 37.4,
    "lon": -121.5,
    "pm25_ug_m3": 95.0,
    "observed_at": "2026-11-17T13:55:00Z",
    "readings_excluded_stale_or_outlier": 2,
}
EVENT_DOWN: dict[str, Any] = {
    **EVENT_SIDE,
    "station_id": "STA-DOWN",
    "station_name": "Downslope Ridge",
    "lat": 37.0,
    "lon": -122.0,
    "pm25_ug_m3": 85.0,
}
EVENT_FAR: dict[str, Any] = {
    **EVENT_SIDE,
    "station_id": "STA-FAR",
    "station_name": "Faraway Flats",
    "lat": 39.0,
    "lon": -118.0,
    "pm25_ug_m3": 70.0,
}
RANK_EXCLUDED_NOTE = (
    "2 stale/outlier reading(s) across ranked stations were excluded from the valid-only "
    "PM2.5 ranking (preserved in counts per station)."
)
T3_HIT: dict[str, Any] = {
    "summary_for_llm": (
        "Top 3 PM2.5 peak(s) between 2026-11-17T13:00:00Z and 2026-11-17T15:00:00Z: leader "
        "Sidewinder Park (STA-SIDE) at 95.0 ug/m3 observed 2026-11-17T13:55:00Z."
    ),
    "data_quality_notes": [RANK_EXCLUDED_NOTE],
    "evidence_refs": {
        "station_ids": ["STA-DOWN", "STA-FAR", "STA-SIDE"],
        "focus_timestamp": "2026-11-17T13:55:00Z",
        "fire_ids": [],
        "bbox_focus": [-122.0, 37.0, -118.0, 39.0],
    },
    "matches": [],
    "events": [EVENT_SIDE, EVENT_DOWN, EVENT_FAR],
}
T3_EMPTY: dict[str, Any] = {
    "summary_for_llm": f"No valid PM2.5 peaks between {EARLY_START} and {EARLY_END}.",
    "data_quality_notes": [f"No valid PM2.5 readings between {EARLY_START} and {EARLY_END}."],
    "evidence_refs": {"focus_timestamp": EARLY_END, "fire_ids": [], "station_ids": []},
    "matches": [],
    "events": [],
}
FIRE_DOWN: dict[str, Any] = {
    "fire_id": "FIRE-1",
    "observed_at": "2026-11-17T13:55:00Z",
    "lat": 37.5,
    "lon": -122.0,
    "frp_mw": 55.0,
    "confidence": "nominal",
    "satellite": "VIIRS-375",
}
FIRE_SIDE: dict[str, Any] = {
    **FIRE_DOWN,
    "fire_id": "FIRE-2",
    "observed_at": "2026-11-17T13:50:00Z",
    "lat": 37.1,
    "lon": -121.9,
    "frp_mw": 80.0,
    "confidence": "low",
}
T4_HIT: dict[str, Any] = {
    "summary_for_llm": (
        "2 active fire detection(s) in the trailing 4 h window at 2026-11-17T14:00:00Z: "
        "leader FIRE-2 at (37.1000, -121.9000) with FRP 80.0 MW, observed 2026-11-17T13:50:00Z."
    ),
    "data_quality_notes": [FIRMS_LATENCY_NOTE],
    "evidence_refs": {
        "fire_ids": ["FIRE-1", "FIRE-2"],
        "station_ids": [],
        "focus_timestamp": TS,
        "bbox_focus": [-122.0, 37.1, -121.9, 37.5],
    },
    "matches": [],
    "fires": [FIRE_DOWN, FIRE_SIDE],
}
T4_EMPTY: dict[str, Any] = {
    "summary_for_llm": (
        f"No active fires at {EARLY_END} in the trailing 4 h window."
    ),
    "data_quality_notes": [
        FIRMS_LATENCY_NOTE,
        "No FIRMS active-fire detections in the trailing 4 h snapshot window at this timestamp.",
    ],
    "evidence_refs": {"focus_timestamp": EARLY_END, "fire_ids": [], "station_ids": []},
    "matches": [],
}
T4_REGION: dict[str, Any] = {
    **T4_HIT,
    "summary_for_llm": (
        "1 active fire detection(s) in the trailing 4 h window at 2026-11-17T14:00:00Z: "
        "leader FIRE-2 at (37.1000, -121.9000) with FRP 80.0 MW, observed 2026-11-17T13:50:00Z."
    ),
    "evidence_refs": {
        "fire_ids": ["FIRE-2"],
        "station_ids": [],
        "focus_timestamp": TS,
        "bbox_focus": [-122.5, 37.0, -121.5, 37.25],
    },
    "fires": [FIRE_SIDE],
}
FRESH_STABLE: dict[str, dict[str, Any]] = {
    "nasa_firms": {
        "last_run_at": "2026-11-17T14:30:00Z",
        "latest_data_ts": "2026-11-17T13:55:00Z",
        "known_latency_minutes": 180,
        "records_written": 3,
        "status": "success",
    },
    "openaq": {
        "last_run_at": "2026-11-17T14:30:00Z",
        "latest_data_ts": "2026-11-17T13:55:00Z",
        "known_latency_minutes": 15,
        "records_written": 6,
        "status": "success",
    },
    "open_meteo": {
        "last_run_at": "2026-11-17T14:30:00Z",
        "latest_data_ts": "2026-11-17T14:50:00Z",
        "known_latency_minutes": 0,
        "records_written": 4,
        "status": "success",
    },
}
RES_CAPS: dict[str, Any] = {
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
    "geographic_bounds": {
        "stations": {
            "records": 5,
            "min_lat": 37.0,
            "max_lat": 39.0,
            "min_lon": -122.0,
            "max_lon": -118.0,
        },
        "active_fires": {
            "records": 2,
            "min_lat": 37.1,
            "max_lat": 37.5,
            "min_lon": -122.0,
            "max_lon": -121.9,
        },
        "wind_grid": {
            "records": 3,
            "min_lat": 37.0,
            "max_lat": 37.5,
            "min_lon": -122.0,
            "max_lon": -122.0,
        },
    },
    "notes": [],
}


def test_tool1_cone_hit(mcp_server: Any) -> None:
    """Station downwind of FIRE-1 inside the plume cone returns two flagged matches."""
    assert call_tool(mcp_server, "analyze_downwind_impact", {"timestamp_iso": TS}) == T1_HIT


def test_tool1_region_keep_reports_requested_bbox(mcp_server: Any) -> None:
    """A bbox that keeps the match is echoed verbatim as bbox_focus."""
    bbox = [-122.5, 36.5, -121.0, 37.2]
    expected = {**T1_HIT, "evidence_refs": {**T1_HIT["evidence_refs"], "bbox_focus": bbox}}
    assert (
        call_tool(mcp_server, "analyze_downwind_impact", {"timestamp_iso": TS, "region_bbox": bbox})
        == expected
    )


def test_tool1_region_excluding_everything_empties_envelope(mcp_server: Any) -> None:
    """A bbox with no stations drops the match and the bbox_focus key entirely."""
    payload = call_tool(
        mcp_server,
        "analyze_downwind_impact",
        {"timestamp_iso": TS, "region_bbox": [-110.0, 30.0, -100.0, 35.0]},
    )
    assert payload == T1_EMPTY


def test_tool1_small_radius_empties_envelope(mcp_server: Any) -> None:
    """A 50 km radius keeps no downwind links and the summary says 'within 50 km'."""
    expected = {
        **T1_EMPTY,
        "summary_for_llm": (
            "No downwind impact correlations at 2026-11-17T14:00:00Z within 50 km and a "
            "+/-25 degree plume cone."
        ),
    }
    assert (
        call_tool(mcp_server, "analyze_downwind_impact", {"timestamp_iso": TS, "radius_km": 50.0})
        == expected
    )


def test_tool2_hourly_profile(mcp_server: Any) -> None:
    """STA-DOWN's window keeps stale rows in counts and averages only valid rows."""
    assert (
        call_tool(
            mcp_server,
            "get_station_timeseries",
            {"station_id": "STA-DOWN", "start_iso": START, "end_iso": END},
        )
        == T2_HIT
    )


def test_tool2_unknown_station_reports_no_data(mcp_server: Any) -> None:
    """An absent station yields empty timeseries with an explicit no-records note."""
    assert (
        call_tool(
            mcp_server,
            "get_station_timeseries",
            {"station_id": "STA-NONE", "start_iso": START, "end_iso": END},
        )
        == T2_NO_DATA
    )


def test_tool3_ranks_valid_peaks(mcp_server: Any) -> None:
    """A limit-3 window ranks the three stations by valid PM2.5, leader 95.0."""
    assert (
        call_tool(
            mcp_server,
            "find_worst_air_quality_events",
            {"start_iso": START, "end_iso": END, "limit": 3},
        )
        == T3_HIT
    )


def test_tool3_empty_window(mcp_server: Any) -> None:
    """A window before the first reading still reports an events list, empty."""
    assert (
        call_tool(
            mcp_server,
            "find_worst_air_quality_events",
            {"start_iso": EARLY_START, "end_iso": EARLY_END},
        )
        == T3_EMPTY
    )


def test_tool4_lists_scene_fires(mcp_server: Any) -> None:
    """TS=14:00Z sees both VIIRS-375 detections, keyed under a fires envelope entry."""
    assert call_tool(mcp_server, "list_active_fires", {"timestamp_iso": TS}) == T4_HIT


def test_tool4_region_keep_reports_requested_bbox(mcp_server: Any) -> None:
    """A bbox that keeps FIRE-2 echoes itself as bbox_focus and drops FIRE-1."""
    assert (
        call_tool(
            mcp_server,
            "list_active_fires",
            {"timestamp_iso": TS, "region_bbox": [-122.5, 37.0, -121.5, 37.25]},
        )
        == T4_REGION
    )


def test_tool4_region_excluding_everything_empties_envelope(mcp_server: Any) -> None:
    """A bbox with no fires drops them all and the bbox_focus key entirely."""
    payload = call_tool(
        mcp_server,
        "list_active_fires",
        {"timestamp_iso": TS, "region_bbox": [-110.0, 30.0, -100.0, 35.0]},
    )
    expected = {
        **T4_EMPTY,
        "summary_for_llm": f"No active fires at {TS} in the trailing 4 h window.",
        "evidence_refs": {**T4_EMPTY["evidence_refs"], "focus_timestamp": TS},
    }
    assert payload == expected


def test_tool4_empty_window(mcp_server: Any) -> None:
    """A target instant before the first detection returns the bare empty envelope."""
    assert (
        call_tool(mcp_server, "list_active_fires", {"timestamp_iso": EARLY_END}) == T4_EMPTY
    )


def test_freshness_stable_fields(mcp_server: Any) -> None:
    """Freshness pins per-source latency and never depends on wall-clock age."""
    payload = read_resource(mcp_server, "resource://data/freshness")
    assert set(payload) == {"sources", "notes"}
    assert payload["notes"] == []
    for name, stable in FRESH_STABLE.items():
        source = payload["sources"][name]
        for key, value in stable.items():
            assert source[key] == value, f"{name}.{key}"
        assert isinstance(source["age_minutes"], float)


def test_schema_capabilities_exact(mcp_server: Any) -> None:
    """Capabilities reproduce units, thresholds, and scene bounds verbatim."""
    assert read_resource(mcp_server, "resource://schema/capabilities") == RES_CAPS


def test_tool2_rejects_reversed_window(mcp_server: Any) -> None:
    with pytest.raises(
        ToolError,
        match=re.escape(
            "Error calling tool 'get_station_timeseries': end_iso must not precede start_iso."
        ),
    ):
        call_tool(
            mcp_server,
            "get_station_timeseries",
            {"station_id": "STA-DOWN", "start_iso": END, "end_iso": START},
        )


def test_tool3_rejects_reversed_window(mcp_server: Any) -> None:
    with pytest.raises(
        ToolError,
        match=re.escape(
            "Error calling tool 'find_worst_air_quality_events': "
            "end_iso must not precede start_iso."
        ),
    ):
        call_tool(
            mcp_server,
            "find_worst_air_quality_events",
            {"start_iso": END, "end_iso": START},
        )


def test_tool3_rejects_zero_limit(mcp_server: Any) -> None:
    with pytest.raises(
        ToolError,
        match=re.escape(
            "Error calling tool 'find_worst_air_quality_events': limit must be at least 1."
        ),
    ):
        call_tool(
            mcp_server,
            "find_worst_air_quality_events",
            {"start_iso": START, "end_iso": END, "limit": 0},
        )


def test_tool4_rejects_short_region_bbox(mcp_server: Any) -> None:
    with pytest.raises(
        ToolError,
        match=re.escape(
            "Error calling tool 'list_active_fires': region_bbox must carry exactly four "
            "values: [min_lon, min_lat, max_lon, max_lat]."
        ),
    ):
        call_tool(
            mcp_server,
            "list_active_fires",
            {"timestamp_iso": TS, "region_bbox": [-122.0, 37.0]},
        )


def test_tool4_rejects_unparseable_timestamp(mcp_server: Any) -> None:
    with pytest.raises(
        ToolError,
        match=re.escape(
            "Error calling tool 'list_active_fires': Invalid ISO-8601 timestamp 'not-a-ts'."
        ),
    ):
        call_tool(mcp_server, "list_active_fires", {"timestamp_iso": "not-a-ts"})


def test_tool1_rejects_short_region_bbox(mcp_server: Any) -> None:
    with pytest.raises(
        ToolError,
        match=re.escape(
            "Error calling tool 'analyze_downwind_impact': region_bbox must carry exactly four "
            "values: [min_lon, min_lat, max_lon, max_lat]."
        ),
    ):
        call_tool(
            mcp_server,
            "analyze_downwind_impact",
            {"timestamp_iso": TS, "region_bbox": [-122.0, 37.0]},
        )


def test_tool1_rejects_unparseable_timestamp(mcp_server: Any) -> None:
    with pytest.raises(
        ToolError,
        match=re.escape(
            "Error calling tool 'analyze_downwind_impact': Invalid ISO-8601 timestamp 'not-a-ts'."
        ),
    ):
        call_tool(mcp_server, "analyze_downwind_impact", {"timestamp_iso": "not-a-ts"})
