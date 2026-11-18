"""REST gateway endpoints serve map and timeline state (spec-05 section 1)."""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from typing import Any

import pytest
from inversa.api.app import create_app
from inversa.api.config import Settings
from starlette.testclient import TestClient

TIMELINE_START: str = "2026-11-17T12:00:00Z"
TIMELINE_END: str = "2026-11-17T16:00:00Z"
SNAPSHOT_TS: str = "2026-11-17T14:30:00Z"
TIMELINE_KEYS: set[str] = {
    "hour_bucket",
    "active_fires_count",
    "avg_pm25",
    "max_pm25",
    "active_stations",
    "stale_stations",
}


@pytest.fixture
def gateway(api_settings: Settings) -> Iterator[TestClient]:
    """Serve the real app with its engine-booting lifespan."""
    app = create_app(api_settings)
    with TestClient(app) as client:
        yield client


def _json(response: Any) -> Any:
    """Assert OK and decode the JSON body."""
    assert response.status_code == 200
    return response.json()


def test_timeline_summary_returns_hourly_aggregates(gateway: TestClient) -> None:
    """The timeline endpoint streams pre-aggregated hourly buckets (spec-03 section 3.2)."""
    rows = _json(
        gateway.get(
            "/api/timeline/summary",
            params={"start": TIMELINE_START, "end": TIMELINE_END},
        )
    )
    active = [row for row in rows if row["active_fires_count"] > 0]
    assert rows
    assert all(set(row) == TIMELINE_KEYS for row in rows)
    assert [row["hour_bucket"] for row in active] == ["2026-11-17T13:00:00Z"]


def test_timeline_summary_serves_preaggregated_buckets_under_50ms(gateway: TestClient) -> None:
    """Scrub-ready responses stay fast enough for 60fps timeline interaction (spec-05)."""
    timings: list[float] = []
    for _ in range(12):
        started = time.perf_counter()
        response = gateway.get(
            "/api/timeline/summary", params={"start": TIMELINE_START, "end": TIMELINE_END}
        )
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200
    assert statistics.median(timings) < 0.050


def test_snapshot_returns_all_three_layers(gateway: TestClient) -> None:
    """The map layers at one instant are fires, stations, and wind (spec-05 section 1)."""
    snap = _json(gateway.get("/api/snapshot", params={"timestamp": SNAPSHOT_TS}))
    assert set(snap) == {"fires", "stations", "wind"}

    fires = snap["fires"]
    assert {row["fire_id"] for row in fires} == {"FIRE-1", "FIRE-2"}
    assert all(row["satellite"] == "VIIRS-375" for row in fires)

    station = next(s for s in snap["stations"] if s["station_id"] == "STA-DOWN")
    assert station["quality_flag"] == "valid"
    assert station["pm25"] == 85.0

    wind = {row["grid_id"]: row for row in snap["wind"]}
    assert set(wind) == {"WX-HOME", "WX-DOWN"}
    assert wind["WX-HOME"]["boundary_layer_height"] == 600.0
    assert wind["WX-DOWN"]["wind_speed_10m"] == 15.0
