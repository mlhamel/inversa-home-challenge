from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import httpx
import polars as pl
import pytest
from ingestion.backfill import backfill as run_backfill
from ingestion.config import Settings
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
            json=[
                meteo_batch(float(lat), float(lon)) for lat, lon in zip(lats, lons, strict=True)
            ],
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
    assert statuses == {"nasa_firms": "success", "openaq": "success", "open_meteo": "success"}

    root = settings.data_dir
    fires = pl.read_parquet(root / "fires" / "date=2026-11-14" / "fires_1800.parquet")
    assert fires.height == 2
    air = pl.read_parquet(root / "air_quality" / "date=2026-11-17" / "openaq_1800.parquet")
    assert air["pm25"].item() == pytest.approx(8.5)
    assert air["quality_flag"].item() == "valid"
    weather = pl.read_parquet(root / "weather" / "date=2026-11-17" / "meteo_1800.parquet")
    assert weather.height == 4

    log = _log(root)
    assert log["known_latency_minutes"].to_list() == [180, 15, 0]
    assert log["status"].to_list() == ["success", "success", "success"]


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
    assert statuses == {"nasa_firms": "partial", "openaq": "success", "open_meteo": "success"}

    log = _log(settings.data_dir)
    assert log["status"].to_list() == ["partial", "success", "success"]
    assert log["records_written"].to_list()[0] == 1
    fires = pl.read_parquet(settings.data_dir / "fires" / "date=2026-11-14" / "fires_1800.parquet")
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
    assert statuses == {"nasa_firms": "success", "openaq": "failed", "open_meteo": "success"}

    root = settings.data_dir
    log = _log(root)
    assert log["status"].to_list() == ["success", "failed", "success"]
    assert log["records_written"].to_list() == [2, 0, 4]
    assert not (root / "air_quality").exists()
