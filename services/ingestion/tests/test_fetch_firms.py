from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from inversa.ingestion import fetch_firms
from inversa.ingestion.config import Settings, load_settings
from inversa.ingestion.contract import FIRES_SCHEMA
from inversa.ingestion.result import CollectorError
from samples import (
    EMPTY_FIRMS_CSV,
    FIRMS_HEADER,
    FIRMS_ROW_A,
    FIRMS_ROW_A_DUP,
    FIRMS_ROW_BAD_CONFIDENCE,
    FIRMS_ROW_BAD_LAT,
    FIRMS_ROW_D,
    INVALID_DAY_RANGE_CSV,
    RUN_AT,
    TEST_BBOX,
)


def test_collect_sync_with_empty_payload_yields_empty_frame() -> None:
    result = fetch_firms.collect_sync(EMPTY_FIRMS_CSV, ingested_at=RUN_AT)
    assert result.df.height == 0
    assert result.rejected == 0
    assert result.df.schema == FIRES_SCHEMA


def test_collect_sync_rejects_error_payload() -> None:
    with pytest.raises(CollectorError, match="FIRMS API rejected"):
        fetch_firms.collect_sync(INVALID_DAY_RANGE_CSV, ingested_at=RUN_AT)


def test_collect_sync_requires_acq_columns() -> None:
    with pytest.raises(CollectorError, match="missing acq columns"):
        fetch_firms.collect_sync("latitude,longitude\n37.0,-122.0", ingested_at=RUN_AT)


def test_collect_sync_dedupes_identical_detections_keeping_first() -> None:
    payload = "\n".join([FIRMS_HEADER, FIRMS_ROW_A, FIRMS_ROW_A_DUP])
    result = fetch_firms.collect_sync(payload, ingested_at=RUN_AT)
    assert result.df.height == 1
    assert result.df["frp"].item() == pytest.approx(12.3)
    assert result.rejected == 0


def test_collect_sync_rejects_unknown_confidence() -> None:
    payload = "\n".join([FIRMS_HEADER, FIRMS_ROW_BAD_CONFIDENCE])
    result = fetch_firms.collect_sync(payload, ingested_at=RUN_AT)
    assert result.df.height == 0
    assert result.rejected == 1


def test_collect_sync_rejects_out_of_bounds_latitude() -> None:
    payload = "\n".join([FIRMS_HEADER, FIRMS_ROW_BAD_LAT])
    result = fetch_firms.collect_sync(payload, ingested_at=RUN_AT)
    assert result.df.height == 0
    assert result.rejected == 1


def test_collect_sync_pads_four_digit_acq_time() -> None:
    payload = "\n".join([FIRMS_HEADER, FIRMS_ROW_D])
    result = fetch_firms.collect_sync(payload, ingested_at=RUN_AT)
    assert result.df.height == 1
    observed = result.df["observed_at"].item()
    assert isinstance(observed, datetime)
    assert observed == datetime(2026, 11, 14, 6, 30, tzinfo=UTC)


async def test_collect_builds_recent_and_dated_window_urls(settings: Settings) -> None:
    captured_recent: list[httpx.Request] = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_capture(captured_recent, EMPTY_FIRMS_CSV))
    ) as client:
        recent = await fetch_firms.collect(
            client, settings, ingested_at=RUN_AT, bbox=TEST_BBOX, day_range=4
        )
    assert recent.df.height == 0
    assert captured_recent[0].url.path.endswith(f"/{TEST_BBOX}/4")

    captured_dated: list[httpx.Request] = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_capture(captured_dated, EMPTY_FIRMS_CSV))
    ) as client:
        await fetch_firms.collect(
            client,
            settings,
            ingested_at=RUN_AT,
            bbox=TEST_BBOX,
            day_range=5,
            end_date=date(2026, 11, 14),
        )
    assert captured_dated[0].url.path.endswith(f"/{TEST_BBOX}/5/2026-11-14")


async def test_collect_rejects_day_range_out_of_bounds(settings: Settings) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_capture([], ""))) as client:
        with pytest.raises(CollectorError, match="day_range"):
            await fetch_firms.collect(
                client, settings, ingested_at=RUN_AT, bbox=TEST_BBOX, day_range=6
            )


async def test_collect_requires_map_key(tmp_path: Path) -> None:
    unkeyed = load_settings({"BBOX": TEST_BBOX, "DATA_DIR": str(tmp_path)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(_capture([], ""))) as client:
        with pytest.raises(CollectorError, match="FIRMS_MAP_KEY"):
            await fetch_firms.collect(
                client, unkeyed, ingested_at=RUN_AT, bbox=TEST_BBOX, day_range=1
            )


async def test_collect_raises_on_http_error(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="denied")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_firms.collect(
                client, settings, ingested_at=RUN_AT, bbox=TEST_BBOX, day_range=1
            )


def _capture(captured: list[httpx.Request], body: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text=body)

    return handler
