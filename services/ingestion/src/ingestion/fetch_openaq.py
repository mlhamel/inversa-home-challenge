from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import httpx
import polars as pl
from inversa.v1 import telemetry_pb2 as telemetry

from ingestion.config import Settings
from ingestion.contract import AIR_QUALITY_SCHEMA, air_quality_rows
from ingestion.http_retry import Pacer, get_with_retry
from ingestion.result import CollectorError, CollectorResult
from ingestion.validate import air_quality

BASE_URL: Final = "https://api.openaq.org/v3"
PM25_PARAMETER_ID: Final[int] = 2
PAGE_LIMIT: Final[int] = 1000
MAX_PAGES: Final[int] = 20
CONCURRENCY: Final[int] = 5
MIN_REQUEST_INTERVAL_SECONDS: Final[float] = 1.1


def openaq_pacer() -> Pacer:
    return Pacer(MIN_REQUEST_INTERVAL_SECONDS)


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    lat: float
    lon: float
    sensor_id: str


def _headers(api_key: str | None) -> dict[str, str]:
    if api_key is None:
        raise CollectorError("OPENAQ_API_KEY is not configured")
    return {"X-API-Key": api_key}


def _station_from_location(location: dict[str, object]) -> Station | None:
    identifier = location.get("id")
    coordinates = location.get("coordinates") or {}
    if not isinstance(identifier, int) or not isinstance(coordinates, dict):
        return None
    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")
    raw_sensors = location.get("sensors")
    sensors = raw_sensors if isinstance(raw_sensors, list) else []
    if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
        return None
    sensor_id = next(
        (
            sensor.get("id")
            for sensor in sensors
            if isinstance(sensor, dict)
            and isinstance(sensor.get("parameter"), dict)
            and sensor["parameter"].get("id") == PM25_PARAMETER_ID
            and isinstance(sensor.get("id"), int)
        ),
        None,
    )
    if sensor_id is None:
        return None
    return Station(
        id=str(identifier),
        name=str(location.get("name") or ""),
        lat=float(latitude),
        lon=float(longitude),
        sensor_id=str(sensor_id),
    )


async def collect_stations(
    client: httpx.AsyncClient,
    *,
    api_key: str | None,
    bbox: str,
    limit: int = PAGE_LIMIT,
    max_pages: int = MAX_PAGES,
    pacer: Pacer | None = None,
) -> list[Station]:
    stations: list[Station] = []
    for page in range(1, max_pages + 1):
        response = await get_with_retry(
            client,
            f"{BASE_URL}/locations",
            params={
                "bbox": bbox,
                "parameters_id": PM25_PARAMETER_ID,
                "monitor": "true",
                "limit": limit,
                "page": page,
            },
            headers=_headers(api_key),
            request_timeout=60.0,
            pacer=pacer,
        )
        payload = response.json()
        results = payload.get("results") or []
        stations.extend(
            station
            for station in (_station_from_location(entry) for entry in results)
            if station is not None
        )
        if len(results) < limit:
            break
    return stations


def _readings(
    rows: list[telemetry.AirQualityReading], rejected_by_validation: int
) -> CollectorResult:
    return CollectorResult(df=air_quality_rows(rows), rejected=rejected_by_validation)


def _parse_utc(stamp: dict[str, object]) -> datetime:
    if not isinstance(stamp, dict):
        raise ValueError(f"expected timestamp dict, got {type(stamp).__name__}")
    utc_text = stamp.get("utc")
    if not isinstance(utc_text, str) or not utc_text:
        raise ValueError(f"missing utc timestamp: {utc_text!r}")
    return datetime.fromisoformat(utc_text.replace("Z", "+00:00"))


def _coerce_pm25(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float | str):
        raise ValueError(f"value is not numeric: {value!r}")
    return float(value)


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def collect(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    ingested_at: datetime,
    pacer: Pacer | None = None,
) -> CollectorResult:
    stations = await collect_stations(
        client, api_key=settings.openaq_api_key, bbox=settings.bbox_str, pacer=pacer
    )
    if not stations:
        return _readings([], 0)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(station: Station) -> CollectorResult:
        async with semaphore:
            response = await get_with_retry(
                client,
                f"{BASE_URL}/locations/{station.id}/latest",
                headers=_headers(settings.openaq_api_key),
                request_timeout=60.0,
                pacer=pacer,
            )
        entry = next(
            (
                item
                for item in response.json().get("results") or []
                if str(item.get("sensorsId")) == station.sensor_id
            ),
            None,
        )
        if entry is None:
            return _readings([], 0)
        rows: list[telemetry.AirQualityReading] = []
        rejected = 0
        try:
            observed_at = _parse_utc(entry.get("datetime") or {})
            rows.append(
                air_quality(
                    observed_at=observed_at,
                    ingested_at=ingested_at,
                    station_id=station.id,
                    station_name=station.name,
                    lat=station.lat,
                    lon=station.lon,
                    pm25=_coerce_pm25(entry.get("value")),
                )
            )
        except ValueError:
            rejected += 1
        return _readings(rows, rejected)

    results = await asyncio.gather(*(one(station) for station in stations))
    frames = [result.df for result in results]
    df = pl.concat(frames, how="vertical") if frames else pl.DataFrame(schema=AIR_QUALITY_SCHEMA)
    return CollectorResult(df=df, rejected=sum(result.rejected for result in results))


async def collect_sensor_hours(
    client: httpx.AsyncClient,
    *,
    api_key: str | None,
    station: Station,
    datetime_from: datetime,
    datetime_to: datetime,
    ingested_at: datetime,
    pacer: Pacer | None = None,
) -> CollectorResult:
    rows: list[telemetry.AirQualityReading] = []
    rejected = 0
    for page in range(1, MAX_PAGES + 1):
        response = await get_with_retry(
            client,
            f"{BASE_URL}/sensors/{station.sensor_id}/hours",
            params={
                "datetime_from": _iso_utc(datetime_from),
                "datetime_to": _iso_utc(datetime_to),
                "limit": PAGE_LIMIT,
                "page": page,
            },
            headers=_headers(api_key),
            request_timeout=60.0,
            pacer=pacer,
        )
        payload = response.json()
        results = payload.get("results") or []
        for item in results:
            value = item.get("value")
            if value is None:
                continue
            period = item.get("period") or {}
            interval = period.get("datetimeFrom") or {}
            try:
                observed_at = _parse_utc(interval)
                rows.append(
                    air_quality(
                        observed_at=observed_at,
                        ingested_at=ingested_at,
                        station_id=station.id,
                        station_name=station.name,
                        lat=station.lat,
                        lon=station.lon,
                        pm25=_coerce_pm25(value),
                    )
                )
            except ValueError:
                rejected += 1
        if len(results) < PAGE_LIMIT:
            break
    return _readings(rows, rejected)
