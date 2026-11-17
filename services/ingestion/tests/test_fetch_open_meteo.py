from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import httpx
import polars as pl
import pytest
from ingestion import fetch_open_meteo
from ingestion.config import Settings
from ingestion.contract import WEATHER_SCHEMA
from ingestion.result import CollectorError
from ingestion.validate import grid_id
from samples import (
    METEO_DIRECTIONS,
    METEO_HEIGHTS,
    METEO_SPEEDS,
    METEO_TIMES,
    RUN_AT,
    meteo_batch,
)

GRID_A: Final[tuple[float, float]] = (37.75, -122.5)
GRID_B: Final[tuple[float, float]] = (38.5, -121.5)
WINDOW_START: Final[datetime] = RUN_AT - timedelta(days=7)


def _capturing_handler(
    payload: Any, captured: list[httpx.Request]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload)

    return handler


def test_points_from_frames_rounds_dedupes_and_sorts() -> None:
    frame = pl.DataFrame({"lat": [38.5816, 37.7658], "lon": [-121.4944, -122.3978]})
    dupes = pl.DataFrame({"lat": [37.7749], "lon": [-122.4194]})

    points = fetch_open_meteo.points_from_frames(None, dupes, frame)

    assert points == [GRID_A, GRID_B]


async def test_collect_rounds_dedupes_and_filters_window(
    settings: Settings, run_at: datetime
) -> None:
    captured: list[httpx.Request] = []
    batches = [meteo_batch(GRID_A[0], GRID_A[1]), meteo_batch(GRID_B[0], GRID_B[1])]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_capturing_handler(batches, captured))
    ) as client:
        result = await fetch_open_meteo.collect(
            client,
            settings,
            ingested_at=run_at,
            points=[(37.7658, -122.3978), (38.5816, -121.4944), (37.7749, -122.4194)],
            start=WINDOW_START,
            end=run_at,
        )

    assert captured[0].url.params["latitude"] == "37.75,38.50"
    assert captured[0].url.params["longitude"] == "-122.50,-121.50"
    assert captured[0].url.params["hourly"] == fetch_open_meteo.HOURLY_VARIABLES
    assert captured[0].url.params["timezone"] == "UTC"
    assert result.df.schema == WEATHER_SCHEMA
    assert result.df.height == 4
    assert result.rejected == 0
    assert result.df["grid_id"].to_list() == [grid_id(*GRID_A)] * 2 + [grid_id(*GRID_B)] * 2
    assert result.df["observed_at"].to_list() == [
        datetime(2026, 11, 17, 16, 0, tzinfo=UTC),
        datetime(2026, 11, 17, 17, 0, tzinfo=UTC),
    ] * 2
    assert result.df["wind_speed_10m"].to_list() == [pytest.approx(v) for v in (4.0, 6.0, 4.0, 6.0)]
    assert result.df["wind_direction_10m"].to_list() == [
        pytest.approx(v) for v in (270.0, 180.0, 270.0, 180.0)
    ]
    assert result.df["boundary_layer_height"].to_list() == [
        pytest.approx(v) for v in (500.0, 510.0, 500.0, 510.0)
    ]


async def test_collect_accepts_single_object_payload(settings: Settings, run_at: datetime) -> None:
    captured: list[httpx.Request] = []
    handler = _capturing_handler(meteo_batch(GRID_B[0], GRID_B[1]), captured)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_open_meteo.collect(
            client,
            settings,
            ingested_at=run_at,
            points=[(38.5816, -121.4944)],
            start=WINDOW_START,
            end=run_at,
        )

    assert result.df.height == 2
    assert result.rejected == 0
    assert result.df["grid_id"].unique().to_list() == [grid_id(*GRID_B)]


async def test_collect_keeps_null_boundary_layer(settings: Settings, run_at: datetime) -> None:
    payload: dict[str, object] = {
        "hourly": {
            "time": list(METEO_TIMES),
            "wind_speed_10m": list(METEO_SPEEDS),
            "wind_direction_10m": list(METEO_DIRECTIONS),
            "boundary_layer_height": [None, 510.0, 700.0],
        }
    }
    captured: list[httpx.Request] = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_capturing_handler(payload, captured))
    ) as client:
        result = await fetch_open_meteo.collect(
            client,
            settings,
            ingested_at=run_at,
            points=[(37.7658, -122.3978)],
            start=WINDOW_START,
            end=run_at,
        )

    assert result.df.height == 2
    assert result.rejected == 0
    rows = result.df.sort("observed_at").rows(named=True)
    assert rows[0]["boundary_layer_height"] is None
    assert rows[1]["boundary_layer_height"] == pytest.approx(510.0)


async def test_collect_rejects_out_of_bounds_wind(settings: Settings, run_at: datetime) -> None:
    payload: dict[str, object] = {
        "hourly": {
            "time": list(METEO_TIMES),
            "wind_speed_10m": [-1.0, 6.0, 9.0],
            "wind_direction_10m": list(METEO_DIRECTIONS),
            "boundary_layer_height": list(METEO_HEIGHTS),
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_capturing_handler(payload, []))
    ) as client:
        result = await fetch_open_meteo.collect(
            client,
            settings,
            ingested_at=run_at,
            points=[(37.7658, -122.3978)],
            start=WINDOW_START,
            end=run_at,
        )

    assert result.rejected == 1
    assert result.df.height == 1
    assert result.df["wind_speed_10m"].to_list() == [pytest.approx(6.0)]
    assert result.df["observed_at"].to_list() == [datetime(2026, 11, 17, 17, 0, tzinfo=UTC)]


async def test_collect_mismatched_batch_count_raises(settings: Settings, run_at: datetime) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_capturing_handler(meteo_batch(GRID_A[0], GRID_A[1]), []))
    ) as client:
        with pytest.raises(CollectorError, match="1 batches for 2 grid points"):
            await fetch_open_meteo.collect(
                client,
                settings,
                ingested_at=run_at,
                points=[(37.7658, -122.3978), (38.5816, -121.4944)],
                start=WINDOW_START,
                end=run_at,
            )


async def test_collect_without_points_makes_no_request(
    settings: Settings, run_at: datetime
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        raise AssertionError("no HTTP call expected for empty points")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_open_meteo.collect(
            client,
            settings,
            ingested_at=run_at,
            points=[],
            start=WINDOW_START,
            end=run_at,
        )

    assert result.df.height == 0
    assert result.df.schema == WEATHER_SCHEMA
    assert result.rejected == 0
    assert captured == []
