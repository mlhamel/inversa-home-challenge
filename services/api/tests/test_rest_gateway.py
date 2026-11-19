"""REST gateway endpoints serve map and timeline state (spec-05 section 1)."""

from __future__ import annotations

import statistics
import time
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from typing import Any

import duckdb
import pytest
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from inversa.api import rest as api_rest
from inversa.api.app import _StreamingSafeGzip, create_app
from inversa.api.config import Region, Settings
from inversa.api.db.queries import Snapshot, TimelineRow, run_snapshot, run_timeline_summary
from inversa.api.rest import CACHE_CONTROL
from starlette.testclient import TestClient

TIMELINE_START: str = "2026-11-17T12:00:00Z"
TIMELINE_END: str = "2026-11-17T16:00:00Z"
SHIFTED_END: str = "2026-11-17T18:00:00Z"
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


def test_timeline_summary_serves_preaggregated_buckets_under_50ms(
    api_settings: Settings,
) -> None:
    """The aggregation query itself stays fast enough for 60fps scrubbing (spec-05)."""
    app = create_app(api_settings.model_copy(update={"state_cache_ttl_ms": 0}))
    with TestClient(app) as client:
        timings: list[float] = []
        for _ in range(12):
            started = time.perf_counter()
            response = client.get(
                "/api/timeline/summary", params={"start": TIMELINE_START, "end": TIMELINE_END}
            )
            timings.append(time.perf_counter() - started)
            assert response.status_code == 200
    assert statistics.median(timings) < 0.050


def test_snapshot_returns_layers_and_regions(gateway: TestClient) -> None:
    """The map layers at one instant are fires, stations, wind, and regions (spec-05 § 1)."""
    snap = _json(gateway.get("/api/snapshot", params={"timestamp": SNAPSHOT_TS}))
    assert set(snap) == {"fires", "stations", "wind", "regions"}
    assert snap["regions"] == []

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


def test_snapshot_exposes_configured_region_rects(api_settings: Settings) -> None:
    """Env-configured study areas ride along so the map can outline every bbox."""
    regions = (
        Region(id="california", label="California", bbox=(-124.4, 36.0, -115.4, 42.0)),
    )
    app = create_app(api_settings.model_copy(update={"regions": regions}))
    with TestClient(app) as client:
        snap = _json(client.get("/api/snapshot", params={"timestamp": SNAPSHOT_TS}))

    assert snap["regions"] == [
        {"id": "california", "label": "California", "bbox": [-124.4, 36.0, -115.4, 42.0]}
    ]


def test_state_endpoints_revalidate_with_etags(gateway: TestClient) -> None:
    """Scrubbing replays of the same instant revalidate to cheap 304s (spec-05)."""
    for path, params in (
        ("/api/snapshot", {"timestamp": SNAPSHOT_TS}),
        ("/api/timeline/summary", {"start": TIMELINE_START, "end": TIMELINE_END}),
    ):
        response = gateway.get(path, params=params)
        assert response.status_code == 200
        assert response.headers["cache-control"] == CACHE_CONTROL
        assert "Accept-Encoding" in _vary_members(response)
        etag = response.headers["etag"]
        assert etag.startswith('"') and etag.endswith('"')

        cases = (
            etag,
            f"W/{etag}",
            "*",
            f'"stale-tag", {etag}',
        )
        for if_none_match in cases:
            revalidated = gateway.get(path, params=params, headers={"If-None-Match": if_none_match})
            assert revalidated.status_code == 304
            assert revalidated.headers["etag"] == etag
            assert revalidated.content == b""
            assert "Accept-Encoding" in _vary_members(revalidated)

        mismatch = gateway.get(path, params=params, headers={"If-None-Match": '"stale-tag"'})
        assert mismatch.status_code == 200
        assert mismatch.headers["etag"] == etag


def test_gzip_compresses_state_responses_but_not_chat_stream() -> None:
    """Large JSON travels compressed; the SSE stream must bypass the gzip window."""
    app = FastAPI()
    app.add_middleware(_StreamingSafeGzip)

    @app.get("/api/snapshot")
    def snapshot() -> Response:
        return Response(content=b'{"fires": []}' + b"x" * 2048, media_type="application/json")

    @app.post("/api/chat")
    async def chat() -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            yield "data: hello\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    with TestClient(app) as client:
        compressed = client.get("/api/snapshot")
        assert compressed.status_code == 200
        assert compressed.headers["content-encoding"] == "gzip"
        assert compressed.content == b'{"fires": []}' + b"x" * 2048

        stream = client.post("/api/chat")
        assert stream.status_code == 200
        assert "content-encoding" not in stream.headers
        assert stream.text.startswith("data: hello")


def test_snapshot_cache_collapses_replay_scrubs_into_one_query(
    gateway: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same-instant scrub replays hit the TTL cache; ETag 304s skip the engine too."""
    calls = _count_snapshot_queries(monkeypatch)
    url = f"/api/snapshot?timestamp={SNAPSHOT_TS}"

    first = gateway.get(url)
    replay = gateway.get(url)
    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.content == first.content
    assert replay.headers["etag"] == first.headers["etag"]
    assert len(calls) == 1

    revalidated = gateway.get(url, headers={"if-none-match": first.headers["etag"]})
    assert revalidated.status_code == 304
    assert len(calls) == 1


def test_timeline_summary_cache_serves_each_window_once(
    gateway: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cached window replays without querying; a shifted window is a cache miss."""
    calls = _count_summary_queries(monkeypatch)
    window = f"/api/timeline/summary?start={TIMELINE_START}&end={TIMELINE_END}"

    first = gateway.get(window)
    replay = gateway.get(window)
    shifted = gateway.get(f"/api/timeline/summary?start={TIMELINE_START}&end={SHIFTED_END}")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.headers["etag"] == first.headers["etag"]
    assert shifted.status_code == 200
    assert len(calls) == 2


def test_zero_ttl_disables_the_state_cache(
    api_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """STATE_CACHE_TTL_MS=0 falls back to querying (and rebuilding) on every request."""
    calls = _count_snapshot_queries(monkeypatch)
    app = create_app(api_settings.model_copy(update={"state_cache_ttl_ms": 0}))
    with TestClient(app) as client:
        first = client.get(f"/api/snapshot?timestamp={SNAPSHOT_TS}")
        replay = client.get(f"/api/snapshot?timestamp={SNAPSHOT_TS}")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert len(calls) == 2


def _json(response: Any) -> Any:
    """Assert OK and decode the JSON body."""
    assert response.status_code == 200
    return response.json()


def _vary_members(response: Any) -> set[str]:
    """Split the Vary header value into its member tokens."""
    return {member.strip() for member in response.headers["vary"].split(",")}


def _count_snapshot_queries(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Route rest.run_snapshot through a call-counting wrapper; return the counter."""
    calls: list[int] = []

    def counting(cursor: duckdb.DuckDBPyConnection, *, target_ts: datetime) -> Snapshot:
        calls.append(1)
        return run_snapshot(cursor, target_ts=target_ts)

    monkeypatch.setattr(api_rest, "run_snapshot", counting)
    return calls


def _count_summary_queries(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Route rest.run_timeline_summary through a call-counting wrapper; return the counter."""
    calls: list[int] = []

    def counting(
        cursor: duckdb.DuckDBPyConnection, *, start_ts: datetime, end_ts: datetime
    ) -> list[TimelineRow]:
        calls.append(1)
        return run_timeline_summary(cursor, start_ts=start_ts, end_ts=end_ts)

    monkeypatch.setattr(api_rest, "run_timeline_summary", counting)
    return calls
