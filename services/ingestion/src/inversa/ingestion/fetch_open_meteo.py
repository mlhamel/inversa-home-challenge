"""Open-Meteo historical-forecast wind and boundary-layer collector."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import httpx
import polars as pl
from inversa.ingestion.config import Settings
from inversa.ingestion.contract import WEATHER_SCHEMA, wind_rows
from inversa.ingestion.http_retry import get_with_retry
from inversa.ingestion.result import CollectorError, CollectorResult
from inversa.ingestion.validate import ValidationError, grid_point, wind_vector
from inversa.v1 import telemetry_pb2 as telemetry

BASE_URL: Final = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES: Final = "wind_speed_10m,wind_direction_10m,boundary_layer_height"


Point = tuple[float, float]


def points_from_frames(*frames: pl.DataFrame | None) -> list[Point]:
    """Collect rounded, deduplicated grid points from fire and air-quality frames."""
    points: set[Point] = set()
    for frame in frames:
        if frame is None or frame.height == 0:
            continue
        points.update(
            _rounded((float(lat), float(lon)))
            for lat, lon in frame.select("lat", "lon").iter_rows()
        )
    return sorted(points)


async def collect(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    ingested_at: datetime,
    points: list[Point],
    start: datetime,
    end: datetime,
    past_days: int = 1,
    forecast_days: int = 1,
) -> CollectorResult:
    """Fetch hourly wind variables for grid points over a UTC time window."""
    if not points:
        return CollectorResult(df=pl.DataFrame(schema=WEATHER_SCHEMA), rejected=0)
    rounded = [_rounded(point) for point in points]
    unique: dict[Point, None] = dict.fromkeys(rounded)
    grid = list(unique)
    response = await get_with_retry(
        client,
        BASE_URL,
        params={
            "latitude": ",".join(f"{point[0]:.2f}" for point in grid),
            "longitude": ",".join(f"{point[1]:.2f}" for point in grid),
            "hourly": HOURLY_VARIABLES,
            "timezone": "UTC",
            "past_days": past_days,
            "forecast_days": forecast_days,
        },
        request_timeout=60.0,
    )
    payload = response.json()
    batches = payload if isinstance(payload, list) else [payload]
    if len(batches) != len(grid):
        msg = f"Open-Meteo returned {len(batches)} batches for {len(grid)} grid points"
        raise CollectorError(msg)
    rows: list[telemetry.WindVector] = []
    rejected = 0
    ingested = ingested_at.astimezone(UTC)
    for point, batch in zip(grid, batches, strict=True):
        hourly = batch.get("hourly") or {}
        times = hourly.get("time") or []
        speeds = hourly.get("wind_speed_10m") or []
        directions = hourly.get("wind_direction_10m") or []
        heights = hourly.get("boundary_layer_height") or []
        for index, moment in enumerate(times):
            observed_at = datetime.fromisoformat(f"{moment}+00:00" if len(moment) == 16 else moment)
            if not start <= observed_at <= end:
                continue
            try:
                rows.append(
                    wind_vector(
                        observed_at=observed_at,
                        ingested_at=ingested,
                        lat=point[0],
                        lon=point[1],
                        wind_speed_10m=float(speeds[index]),
                        wind_direction_10m=float(directions[index]),
                        boundary_layer_height=(
                            float(heights[index]) if heights[index] is not None else None
                        ),
                    )
                )
            except ValidationError:
                rejected += 1
    return CollectorResult(df=wind_rows(rows), rejected=rejected)


def _rounded(point: Point) -> Point:
    lat, lon = grid_point(point[0], point[1])
    return (float(lat), float(lon))
