from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import httpx
import polars as pl
import pytest
from inversa.ingestion.backfill import backfill as run_backfill
from inversa.ingestion.config import Settings
from samples import (
    EMPTY_FIRMS_CSV,
    FIRMS_HEADER,
    FIRMS_ROW_A,
    FIRMS_ROW_BAD_CONFIDENCE,
    FIRMS_ROW_D,
    FRESH_UTC,
    TEST_BBOX,
    meteo_batch,
    openaq_hours_entry,
    openaq_location,
)

FIRMS_OLDER_PATH: Final[str] = f"/{TEST_BBOX}/5/2026-11-14"
OLDER_ROWS: Final[str] = "\n".join([FIRMS_HEADER, FIRMS_ROW_A, FIRMS_ROW_D])
PARTIAL_ROWS: Final[str] = "\n".join([FIRMS_HEADER, FIRMS_ROW_A, FIRMS_ROW_BAD_CONFIDENCE])


async def test_backfill_records_all_three_sources(
    settings: Settings, run_at: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mount_transport(
        monkeypatch,
        _handler(
            recent=EMPTY_FIRMS_CSV,
            older=OLDER_ROWS,
            openaq_locations=httpx.Response(200, json={"results": [openaq_location()]}),
        ),
    )

    statuses = await run_backfill(settings, run_at=run_at)
    assert statuses == {
        "nasa_firms:default": "success",
        "openaq:default": "success",
        "open_meteo:default": "success",
    }

    root = settings.data_dir
    fires = pl.read_parquet(root / "fires" / "date=2026-11-14" / "fires_default_1800.parquet")
    assert fires.height == 2
    assert fires["region"].unique().to_list() == ["default"]
    air = pl.read_parquet(
        root / "air_quality" / "date=2026-11-17" / "openaq_default_1800.parquet"
    )
    assert air["pm25"].item() == pytest.approx(8.5)
    assert air["quality_flag"].item() == "valid"
    weather = pl.read_parquet(
        root / "weather" / "date=2026-11-17" / "meteo_default_1800.parquet"
    )
    assert weather.height == 4

    log = _log(root)
    assert log["known_latency_minutes"].to_list() == [180, 15, 0]
    assert log["status"].to_list() == ["success", "success", "success"]
    assert log["region"].unique().to_list() == ["default"]


async def test_backfill_flags_partial_when_firms_rejects(
    settings: Settings, run_at: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mount_transport(
        monkeypatch,
        _handler(
            recent=EMPTY_FIRMS_CSV,
            older=PARTIAL_ROWS,
            openaq_locations=httpx.Response(200, json={"results": [openaq_location()]}),
        ),
    )

    statuses = await run_backfill(settings, run_at=run_at)
    assert statuses == {
        "nasa_firms:default": "partial",
        "openaq:default": "success",
        "open_meteo:default": "success",
    }

    log = _log(settings.data_dir)
    assert log["status"].to_list() == ["partial", "success", "success"]
    assert log["records_written"].to_list()[0] == 1
    fires = pl.read_parquet(
        settings.data_dir / "fires" / "date=2026-11-14" / "fires_default_1800.parquet"
    )
    assert fires.height == 1
    assert fires["confidence"].unique().to_list() == ["high"]


async def test_backfill_logs_failure_when_openaq_fails(
    settings: Settings, run_at: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mount_transport(
        monkeypatch,
        _handler(
            recent=EMPTY_FIRMS_CSV,
            older=OLDER_ROWS,
            openaq_locations=httpx.Response(500, text="boom"),
        ),
    )

    statuses = await run_backfill(settings, run_at=run_at)
    assert statuses == {
        "nasa_firms:default": "success",
        "openaq:default": "failed",
        "open_meteo:default": "success",
    }

    root = settings.data_dir
    log = _log(root)
    assert log["status"].to_list() == ["success", "failed", "success"]
    assert log["records_written"].to_list() == [2, 0, 4]
    assert not (root / "air_quality").exists()


async def test_backfill_emits_info_flow_lines(
    settings: Settings,
    run_at: datetime,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _mount_transport(
        monkeypatch,
        _handler(
            recent=EMPTY_FIRMS_CSV,
            older=OLDER_ROWS,
            openaq_locations=httpx.Response(200, json={"results": [openaq_location()]}),
        ),
    )
    with caplog.at_level(logging.INFO):
        statuses = await run_backfill(settings, run_at=run_at)

    assert statuses == {
        "nasa_firms:default": "success",
        "openaq:default": "success",
        "open_meteo:default": "success",
    }
    messages = [record.message for record in caplog.records]
    starts = [message for message in messages if message.startswith("backfill start:")]
    assert len(starts) == 1
    assert f"regions=default={TEST_BBOX}" in starts[0]
    assert "window=2026-11-10..2026-11-17" in starts[0]
    assert f"dir={settings.data_dir}" in starts[0]
    assert "nasa_firms: range 4d: 0 fires, 0 rejected" in messages
    assert "nasa_firms: range 5d: 2 fires, 0 rejected" in messages
    assert "openaq/default: 1 stations in bbox" in messages
    station_lines = [message for message in messages if message.startswith("openaq: station 2009:")]
    assert station_lines == ["openaq: station 2009: 1 rows, 0 rejected"]
    assert any(message.startswith("open_meteo: ") for message in messages)
    assert any(
        message.startswith("open_meteo: 4 rows across 1 regions, 0 rejected, ")
        for message in messages
    )
    summaries = [message for message in messages if message.startswith("backfill complete:")]
    assert len(summaries) == 1
    assert (
        "nasa_firms:default=success openaq:default=success open_meteo:default=success"
        in summaries[0]
    )
    assert "wall " in summaries[0] and summaries[0].endswith(")")


async def test_backfill_logs_source_failure(
    settings: Settings,
    run_at: datetime,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _mount_transport(
        monkeypatch,
        _handler(
            recent=EMPTY_FIRMS_CSV,
            older=OLDER_ROWS,
            openaq_locations=httpx.Response(500, text="boom"),
        ),
    )
    with caplog.at_level(logging.INFO):
        statuses = await run_backfill(settings, run_at=run_at)

    assert statuses["openaq:default"] == "failed"
    messages = [record.message for record in caplog.records]
    assert "storage: openaq/default: run failed, recorded in ingestion log" in messages
    summaries = [message for message in messages if message.startswith("backfill complete:")]
    assert "openaq:default=failed" in summaries[0]


def _handler(
    *, recent: str, older: str, openaq_locations: httpx.Response
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/4"):
            return httpx.Response(200, text=recent)
        if path.endswith(FIRMS_OLDER_PATH):
            return httpx.Response(200, text=older)
        if path.endswith("/v3/locations"):
            return openaq_locations
        if "/v3/sensors/" in path:
            entry = openaq_hours_entry(value=8.5, utc=FRESH_UTC)
            return httpx.Response(200, json={"results": [entry]})
        lats = request.url.params["latitude"].split(",")
        lons = request.url.params["longitude"].split(",")
        return httpx.Response(
            200,
            json=[meteo_batch(float(lat), float(lon)) for lat, lon in zip(lats, lons, strict=True)],
        )

    return handler


def _mount_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    transport = httpx.MockTransport(handler)
    client_class = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return client_class(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _log(root: Path) -> pl.DataFrame:
    return pl.read_parquet(root / "meta" / "ingestion_log.parquet")
