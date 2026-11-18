"""Seven-day backfill orchestration across FIRMS, OpenAQ, and Open-Meteo."""

from __future__ import annotations

import asyncio
import logging
import time
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
logger: Final[logging.Logger] = logging.getLogger(__name__)


async def backfill(settings: Settings, *, run_at: datetime | None = None) -> dict[str, str]:
    """Run one backfill pass over all sources; return per-source status."""
    moment = (run_at or datetime.now(UTC)).astimezone(UTC)
    start = moment - timedelta(days=BACKFILL_DAYS)
    statuses: dict[str, str] = {}
    wall_start = time.perf_counter()
    logger.info(
        "backfill start: BBOX=%s window=%s..%s dir=%s",
        settings.bbox_str,
        start.date().isoformat(),
        moment.date().isoformat(),
        settings.data_dir,
    )
    fires_df: pl.DataFrame | None = None
    openaq_df: pl.DataFrame | None = None
    pacer = fetch_openaq.openaq_pacer()
    async with httpx.AsyncClient() as client:
        firms_clock = time.perf_counter()
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
            logger.info(
                "nasa_firms: %d fires, %d rejected, %s",
                fires_df.height,
                rejected,
                _fmt_duration(time.perf_counter() - firms_clock),
            )
        except HANDLED_ERRORS:
            record_failure(settings.data_dir, source="nasa_firms", run_at=moment)
            statuses["nasa_firms"] = "failed"
        openaq_clock = time.perf_counter()
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
            logger.info(
                "openaq: %d rows, %d rejected, %s",
                openaq_df.height,
                rejected,
                _fmt_duration(time.perf_counter() - openaq_clock),
            )
        except HANDLED_ERRORS:
            record_failure(settings.data_dir, source="openaq", run_at=moment)
            statuses["openaq"] = "failed"
        meteo_clock = time.perf_counter()
        try:
            points = fetch_open_meteo.points_from_frames(openaq_df, fires_df)
            logger.info("open_meteo: %d points, %d-day history", len(points), WEATHER_PAST_DAYS)
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
            logger.info(
                "open_meteo: %d rows, %d rejected, %s",
                weather.df.height,
                weather.rejected,
                _fmt_duration(time.perf_counter() - meteo_clock),
            )
        except HANDLED_ERRORS:
            record_failure(settings.data_dir, source="open_meteo", run_at=moment)
            statuses["open_meteo"] = "failed"
    logger.info(
        "backfill complete: %s (wall %s)",
        " ".join(f"{source}={status}" for source, status in statuses.items()),
        _fmt_duration(time.perf_counter() - wall_start),
    )
    return statuses


def main() -> None:
    """CLI entry point: configure logging, run the backfill, log the summary."""
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    for quiet in ("httpx", "httpcore"):
        logging.getLogger(quiet).setLevel(logging.WARNING)
    asyncio.run(backfill(load_settings()))


async def _collect_firms(
    client: httpx.AsyncClient, settings: Settings, run_at: datetime
) -> tuple[pl.DataFrame, int]:
    recent = await fetch_firms.collect(
        client, settings, ingested_at=run_at, day_range=FIRMS_RECENT_RANGE
    )
    logger.info(
        "nasa_firms: range %dd: %d fires, %d rejected",
        FIRMS_RECENT_RANGE,
        recent.df.height,
        recent.rejected,
    )
    older = await fetch_firms.collect(
        client,
        settings,
        ingested_at=run_at,
        day_range=FIRMS_OLDER_RANGE,
        end_date=(run_at - FIRMS_OLDER_OFFSET).date(),
    )
    logger.info(
        "nasa_firms: range %dd: %d fires, %d rejected",
        FIRMS_OLDER_RANGE,
        older.df.height,
        older.rejected,
    )
    results = [recent, older]
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
    logger.info("openaq: discovering stations in BBOX %s", settings.bbox_str)
    stations = await fetch_openaq.collect_stations(
        client, api_key=settings.openaq_api_key, bbox=settings.bbox_str, pacer=pacer
    )
    logger.info("openaq: %d stations in BBOX", len(stations))
    if not stations:
        logger.warning("openaq: no stations found, skipping sensor history")
        return pl.DataFrame(schema=AIR_QUALITY_SCHEMA), 0
    semaphore = asyncio.Semaphore(fetch_openaq.CONCURRENCY)

    async def one(station: fetch_openaq.Station) -> CollectorResult:
        async with semaphore:
            result = await fetch_openaq.collect_sensor_hours(
                client,
                api_key=settings.openaq_api_key,
                station=station,
                datetime_from=start,
                datetime_to=run_at,
                ingested_at=run_at,
                pacer=pacer,
            )
            logger.info(
                "openaq: station %s: %d rows, %d rejected",
                station.id,
                result.df.height,
                result.rejected,
            )
            return result

    responses = await asyncio.gather(*(one(station) for station in stations))
    frames = [response.df for response in responses]
    return (
        pl.concat(frames, how="vertical"),
        sum(response.rejected for response in responses),
    )


def _fmt_duration(seconds: float) -> str:
    """Format a wall duration for logs: seconds below a minute, else minutes."""
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    return f"{seconds / 60.0:.1f}m"


if __name__ == "__main__":
    main()
