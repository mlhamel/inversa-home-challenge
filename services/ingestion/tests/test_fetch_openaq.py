from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from inversa.ingestion import fetch_openaq
from inversa.ingestion.config import Settings
from inversa.ingestion.contract import AIR_QUALITY_SCHEMA
from inversa.ingestion.result import CollectorError
from samples import (
    FRESH_UTC,
    RUN_AT,
    TEST_BBOX,
    openaq_hours_entry,
    openaq_latest_entry,
    openaq_location,
)


async def test_collect_stations_discovers_pm25_sensor(settings: Settings) -> None:
    captured: list[httpx.Request] = []
    routes = {"/v3/locations": {"results": [openaq_location()]}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler(captured, routes))
    ) as client:
        stations = await fetch_openaq.collect_stations(
            client, api_key=settings.openaq_api_key, bbox=TEST_BBOX
        )

    assert [(station.id, station.name, station.lat, station.lon) for station in stations] == [
        ("2009", "San Francisco", 37.7658, -122.3978)
    ]
    assert stations[0].sensor_id == "3569"
    assert captured[0].url.params["bbox"] == TEST_BBOX
    assert captured[0].url.params["parameters_id"] == "2"
    assert captured[0].headers["X-API-Key"] == "test-openaq-key"


async def test_collect_stations_drops_locations_without_pm25(settings: Settings) -> None:
    location: dict[str, object] = {
        "id": 7,
        "name": "CO only",
        "coordinates": {"latitude": 38.0, "longitude": -121.0},
        "sensors": [
            {
                "id": 999,
                "name": "co ppm",
                "parameter": {"id": 8, "name": "co", "units": "ppm", "displayName": None},
            }
        ],
    }
    routes = {"/v3/locations": {"results": [location]}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        stations = await fetch_openaq.collect_stations(
            client, api_key=settings.openaq_api_key, bbox=TEST_BBOX
        )

    assert stations == []


async def test_collect_stations_requires_api_key() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    ) as client:
        with pytest.raises(CollectorError, match="is not configured"):
            await fetch_openaq.collect_stations(client, api_key=None, bbox=TEST_BBOX)


async def test_collect_stations_stops_on_short_page(settings: Settings) -> None:
    pages: dict[str, Any] = {
        "1": {"results": [openaq_location(identifier=2009)]},
        "2": {"results": [openaq_location(identifier=2010)]},
        "3": {"results": []},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = str(request.url.params["page"])
        return httpx.Response(200, json=pages[page])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        stations = await fetch_openaq.collect_stations(
            client, api_key=settings.openaq_api_key, bbox=TEST_BBOX, limit=1
        )

    assert [station.id for station in stations] == ["2009", "2010"]


async def test_collect_latest_matches_pm25_sensor_entry(settings: Settings, run_at: Any) -> None:
    routes: dict[str, Any] = {
        "/v3/locations": {"results": [openaq_location()]},
        "/latest": {
            "results": [
                openaq_latest_entry(sensors_id=25672, value=1.2, utc=FRESH_UTC),
                openaq_latest_entry(sensors_id=3569, value=8.5, utc=FRESH_UTC),
            ]
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        result = await fetch_openaq.collect(client, settings, ingested_at=run_at)

    assert result.df.height == 1
    assert result.df.schema == AIR_QUALITY_SCHEMA
    row = result.df.row(0, named=True)
    assert row["measurement_id"] == "2009_2026-11-17T17:00:00+00:00"
    assert row["pm25"] == pytest.approx(8.5)
    assert row["quality_flag"] == "valid"


async def test_collect_latest_preserves_missing_value_as_stale(
    settings: Settings, run_at: Any
) -> None:
    routes: dict[str, Any] = {
        "/v3/locations": {"results": [openaq_location()]},
        "/latest": {"results": [openaq_latest_entry(sensors_id=3569, value=None, utc=FRESH_UTC)]},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        result = await fetch_openaq.collect(client, settings, ingested_at=run_at)

    assert result.df.height == 1
    row = result.df.row(0, named=True)
    assert row["pm25"] is None
    assert row["quality_flag"] == "stale"
    assert result.rejected == 0


async def test_collect_latest_without_stations_yields_empty(
    settings: Settings, run_at: Any
) -> None:
    captured: list[httpx.Request] = []
    routes: dict[str, object] = {"/v3/locations": {"results": []}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler(captured, routes))
    ) as client:
        result = await fetch_openaq.collect(client, settings, ingested_at=run_at)

    assert result.df.height == 0
    assert result.rejected == 0
    assert len(captured) == 1


async def test_collect_sensor_hours_paginates_until_short_page(
    settings: Settings, run_at: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_openaq, "PAGE_LIMIT", 1)
    pages: dict[str, Any] = {
        "1": {"results": [openaq_hours_entry(value=8.5, utc="2026-11-17T16:00:00Z")]},
        "2": {"results": [openaq_hours_entry(value=9.5, utc=FRESH_UTC)]},
        "3": {"results": []},
    }
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url.params["page"]))
        return httpx.Response(200, json=pages[str(request.url.params["page"])])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_openaq.collect_sensor_hours(
            client,
            api_key=settings.openaq_api_key,
            station=_station(),
            datetime_from=RUN_AT - timedelta(days=7),
            datetime_to=run_at,
            ingested_at=run_at,
        )

    assert requested == ["1", "2", "3"]
    assert result.df.height == 2
    assert result.df["pm25"].to_list() == [pytest.approx(8.5), pytest.approx(9.5)]
    assert result.rejected == 0
    first = result.df.row(0, named=True)
    assert first["measurement_id"] == "2009_2026-11-17T16:00:00+00:00"


async def test_collect_latest_rejects_entry_with_missing_utc(
    settings: Settings, run_at: Any
) -> None:
    routes: dict[str, Any] = {
        "/v3/locations": {"results": [openaq_location()]},
        "/latest": {"results": [{"sensorsId": 3569, "value": 8.5, "datetime": {}}]},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        result = await fetch_openaq.collect(client, settings, ingested_at=run_at)

    assert result.rejected == 1
    assert result.df.height == 0


async def test_collect_latest_rejects_non_dict_datetime(
    settings: Settings, run_at: Any
) -> None:
    routes: dict[str, Any] = {
        "/v3/locations": {"results": [openaq_location()]},
        "/latest": {"results": [{"sensorsId": 3569, "value": 8.5, "datetime": "garbage"}]},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        result = await fetch_openaq.collect(client, settings, ingested_at=run_at)

    assert result.rejected == 1
    assert result.df.height == 0


async def test_collect_latest_rejects_non_numeric_value(
    settings: Settings, run_at: Any
) -> None:
    entry = openaq_latest_entry(sensors_id=3569, value=8.5, utc=FRESH_UTC)
    entry["value"] = "oops"
    routes: dict[str, Any] = {
        "/v3/locations": {"results": [openaq_location()]},
        "/latest": {"results": [entry]},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        result = await fetch_openaq.collect(client, settings, ingested_at=run_at)

    assert result.rejected == 1
    assert result.df.height == 0


async def test_collect_sensor_hours_rejects_entry_with_missing_utc(
    settings: Settings, run_at: Any
) -> None:
    routes: dict[str, Any] = {
        "/hours": {"results": [{"value": 8.5, "period": {"datetimeFrom": {}}}]},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        result = await fetch_openaq.collect_sensor_hours(
            client,
            api_key=settings.openaq_api_key,
            station=_station(),
            datetime_from=RUN_AT - timedelta(days=7),
            datetime_to=run_at,
            ingested_at=run_at,
        )

    assert result.rejected == 1
    assert result.df.height == 0


async def test_collect_sensor_hours_rejects_non_numeric_value(
    settings: Settings, run_at: Any
) -> None:
    entry = openaq_hours_entry(value=8.5, utc=FRESH_UTC)
    entry["value"] = "oops"
    routes: dict[str, Any] = {"/hours": {"results": [entry]}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_json_handler([], routes))
    ) as client:
        result = await fetch_openaq.collect_sensor_hours(
            client,
            api_key=settings.openaq_api_key,
            station=_station(),
            datetime_from=RUN_AT - timedelta(days=7),
            datetime_to=run_at,
            ingested_at=run_at,
        )

    assert result.rejected == 1
    assert result.df.height == 0


def _station() -> fetch_openaq.Station:
    return fetch_openaq.Station(
        id="2009", name="San Francisco", lat=37.7658, lon=-122.3978, sensor_id="3569"
    )


def _json_handler(
    captured: list[httpx.Request], routes: dict[str, Any]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        for suffix, payload in routes.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json=payload)
        raise AssertionError(f"unexpected route: {request.url.path}")

    return handler
