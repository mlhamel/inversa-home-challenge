"""Seven-day backfill orchestration across FIRMS, OpenAQ, and Open-Meteo."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Final

import httpx
import polars as pl
from inversa.ingestion import fetch_firms, fetch_open_meteo, fetch_openaq
from inversa.ingestion.config import Settings, load_settings
from inversa.ingestion.contract import AIR_QUALITY_SCHEMA
from inversa.ingestion.http_retry import Pacer
from inversa.ingestion.result import CollectorError, CollectorResult
from inversa.ingestion.storage import record_batch, record_failure

BACKFILL_DAYS: Final[int] = 7
FIRMS_RECENT_RANGE: Final[int] = 4
FIRMS_OLDER_RANGE: Final[int] = 5
FIRMS_OLDER_OFFSET: Final[timedelta] = timedelta(days=3)
WEATHER_PAST_DAYS: Final[int] = 7
HANDLED_ERRORS: Final[tuple[type[BaseException], ...]] = (
    CollectorError,
    pl.exceptions.PolarsError,
    httpx.HTTPError,
    ValueError,
)


async def backfill(settings: Settings, *, run_at: datetime | None = None) -> dict[str, str]:
    """Run one backfill pass over all sources; return per-source status."""
    moment = (run_at or datetime.now(UTC)).astimezone(UTC)
    start = moment - timedelta(days=BACKFILL_DAYS)
    statuses: dict[str, str] = {}
    fires_df: pl.DataFrame | None = None
    openaq_df: pl.DataFrame | None = None
    pacer = fetch_openaq.openaq_pacer()
    async with httpx.AsyncClient() as client:
        try:
            fires_df, rejected = await _collect_firms(client, settings, moment)
            record_batch(
                fires_df,
                root=settings.data_dir,
                source="nasa_firms",
                run_at=moment,
                rejected=rejected,
            )
            statuses["nasa_firms"] = "partial" if rejected else "success"
        except HANDLED_ERRORS:
            record_failure(settings.data_dir, source="nasa_firms", run_at=moment)
            statuses["nasa_firms"] = "failed"
        try:
            openaq_df, rejected = await _collect_openaq_hours(
                client, settings, moment, start, pacer
            )
            record_batch(
                openaq_df,
                root=settings.data_dir,
                source="openaq",
                run_at=moment,
                rejected=rejected,
            )
            statuses["openaq"] = "partial" if rejected else "success"
        except HANDLED_ERRORS:
            record_failure(settings.data_dir, source="openaq", run_at=moment)
            statuses["openaq"] = "failed"
        try:
            points = fetch_open_meteo.points_from_frames(openaq_df, fires_df)
            weather = await fetch_open_meteo.collect(
                client,
                settings,
                ingested_at=moment,
                points=points,
                start=start,
                end=moment,
                past_days=WEATHER_PAST_DAYS,
            )
            record_batch(
                weather.df,
                root=settings.data_dir,
                source="open_meteo",
                run_at=moment,
                rejected=weather.rejected,
            )
            statuses["open_meteo"] = "partial" if weather.rejected else "success"
        except HANDLED_ERRORS:
            record_failure(settings.data_dir, source="open_meteo", run_at=moment)
            statuses["open_meteo"] = "failed"
    return statuses


def main() -> None:
    """CLI entry point: load settings, run the backfill, print per-source status."""
    from dotenv import load_dotenv

    load_dotenv()
    summary = asyncio.run(backfill(load_settings()))
    for source, status in sorted(summary.items()):
        print(f"{source}: {status}")


async def _collect_firms(
    client: httpx.AsyncClient, settings: Settings, run_at: datetime
) -> tuple[pl.DataFrame, int]:
    results = [
        await fetch_firms.collect(
            client, settings, ingested_at=run_at, day_range=FIRMS_RECENT_RANGE
        ),
        await fetch_firms.collect(
            client,
            settings,
            ingested_at=run_at,
            day_range=FIRMS_OLDER_RANGE,
            end_date=(run_at - FIRMS_OLDER_OFFSET).date(),
        ),
    ]
    frames = [result.df for result in results]
    df = pl.concat(frames, how="vertical").unique(
        subset=["fire_id"], keep="first", maintain_order=True
    )
    return df, sum(result.rejected for result in results)


async def _collect_openaq_hours(
    client: httpx.AsyncClient,
    settings: Settings,
    run_at: datetime,
    start: datetime,
    pacer: Pacer,
) -> tuple[pl.DataFrame, int]:
    stations = await fetch_openaq.collect_stations(
        client, api_key=settings.openaq_api_key, bbox=settings.bbox_str, pacer=pacer
    )
    if not stations:
        return pl.DataFrame(schema=AIR_QUALITY_SCHEMA), 0
    semaphore = asyncio.Semaphore(fetch_openaq.CONCURRENCY)

    async def one(station: fetch_openaq.Station) -> CollectorResult:
        async with semaphore:
            return await fetch_openaq.collect_sensor_hours(
                client,
                api_key=settings.openaq_api_key,
                station=station,
                datetime_from=start,
                datetime_to=run_at,
                ingested_at=run_at,
                pacer=pacer,
            )

    responses = await asyncio.gather(*(one(station) for station in stations))
    frames = [response.df for response in responses]
    return (
        pl.concat(frames, how="vertical"),
        sum(response.rejected for response in responses),
    )


if __name__ == "__main__":
    main()
