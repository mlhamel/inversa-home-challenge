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
from inversa.ingestion.config import Region, Settings, load_settings
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
    """Run one backfill pass over all sources per region; return per-source-region status."""
    moment = (run_at or datetime.now(UTC)).astimezone(UTC)
    start = moment - timedelta(days=BACKFILL_DAYS)
    statuses: dict[str, str] = {}
    wall_start = time.perf_counter()
    logger.info(
        "backfill start: regions=%s window=%s..%s dir=%s",
        " ".join(f"{region.id}={region.bbox_str}" for region in settings.regions),
        start.date().isoformat(),
        moment.date().isoformat(),
        settings.data_dir,
    )
    region_fires: dict[str, pl.DataFrame | None] = {}
    region_openaq: dict[str, pl.DataFrame | None] = {}
    pacer = fetch_openaq.openaq_pacer()
    async with httpx.AsyncClient() as client:
        for region in settings.regions:
            firms_clock = time.perf_counter()
            try:
                fires_df, rejected = await _collect_firms(client, settings, region, moment)
                record_batch(
                    fires_df,
                    root=settings.data_dir,
                    source="nasa_firms",
                    region=region.id,
                    run_at=moment,
                    rejected=rejected,
                )
                region_fires[region.id] = fires_df
                statuses[f"nasa_firms:{region.id}"] = "partial" if rejected else "success"
                logger.info(
                    "nasa_firms/%s: %d fires, %d rejected, %s",
                    region.id,
                    fires_df.height,
                    rejected,
                    _fmt_duration(time.perf_counter() - firms_clock),
                )
            except HANDLED_ERRORS:
                region_fires[region.id] = None
                record_failure(
                    settings.data_dir, source="nasa_firms", region=region.id, run_at=moment
                )
                statuses[f"nasa_firms:{region.id}"] = "failed"
            openaq_clock = time.perf_counter()
            try:
                openaq_df, rejected = await _collect_openaq_hours(
                    client, settings, region, moment, start, pacer
                )
                record_batch(
                    openaq_df,
                    root=settings.data_dir,
                    source="openaq",
                    region=region.id,
                    run_at=moment,
                    rejected=rejected,
                )
                region_openaq[region.id] = openaq_df
                statuses[f"openaq:{region.id}"] = "partial" if rejected else "success"
                logger.info(
                    "openaq/%s: %d rows, %d rejected, %s",
                    region.id,
                    openaq_df.height,
                    rejected,
                    _fmt_duration(time.perf_counter() - openaq_clock),
                )
            except HANDLED_ERRORS:
                region_openaq[region.id] = None
                record_failure(settings.data_dir, source="openaq", region=region.id, run_at=moment)
                statuses[f"openaq:{region.id}"] = "failed"
        meteo_clock = time.perf_counter()
        try:
            fires_frames = [df for df in region_fires.values() if df is not None]
            openaq_frames = [df for df in region_openaq.values() if df is not None]
            points = fetch_open_meteo.points_from_frames(*openaq_frames, *fires_frames)
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
            weather_rows_by_region = _split_by_region(weather.df, settings.regions)
            for region in settings.regions:
                record_batch(
                    weather_rows_by_region[region.id],
                    root=settings.data_dir,
                    source="open_meteo",
                    region=region.id,
                    run_at=moment,
                    rejected=weather.rejected,
                )
                statuses[f"open_meteo:{region.id}"] = "partial" if weather.rejected else "success"
            logger.info(
                "open_meteo: %d rows across %d regions, %d rejected, %s",
                weather.df.height,
                len(settings.regions),
                weather.rejected,
                _fmt_duration(time.perf_counter() - meteo_clock),
            )
        except HANDLED_ERRORS:
            for region in settings.regions:
                record_failure(
                    settings.data_dir, source="open_meteo", region=region.id, run_at=moment
                )
                statuses[f"open_meteo:{region.id}"] = "failed"
    logger.info(
        "backfill complete: %s (wall %s)",
        " ".join(f"{key}={status}" for key, status in statuses.items()),
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
    client: httpx.AsyncClient, settings: Settings, region: Region, run_at: datetime
) -> tuple[pl.DataFrame, int]:
    recent = await fetch_firms.collect(
        client, settings, ingested_at=run_at, bbox=region.bbox_str, day_range=FIRMS_RECENT_RANGE
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
        bbox=region.bbox_str,
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
    region: Region,
    run_at: datetime,
    start: datetime,
    pacer: Pacer,
) -> tuple[pl.DataFrame, int]:
    logger.info("openaq/%s: discovering stations in bbox %s", region.id, region.bbox_str)
    stations = await fetch_openaq.collect_stations(
        client, api_key=settings.openaq_api_key, bbox=region.bbox_str, pacer=pacer
    )
    logger.info("openaq/%s: %d stations in bbox", region.id, len(stations))
    if not stations:
        logger.warning("openaq/%s: no stations found, skipping sensor history", region.id)
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


def _split_by_region(
    df: pl.DataFrame, regions: tuple[Region, ...]
) -> dict[str, pl.DataFrame]:
    """Partition weather rows by the region owning each grid point (nearest-bbox fallback)."""
    if df.height == 0:
        return {region.id: df for region in regions}
    points = df.select("lat", "lon").unique()
    lats: list[float] = []
    lons: list[float] = []
    owners: list[str] = []
    for lat, lon in points.iter_rows():
        lats.append(lat)
        lons.append(lon)
        owners.append(_nearest_region(lat, lon, regions).id)
    tagged = df.join(
        pl.DataFrame({"lat": lats, "lon": lons, "_point_region": owners}),
        on=["lat", "lon"],
        how="inner",
    )
    return {
        region.id: tagged.filter(pl.col("_point_region") == region.id).drop("_point_region")
        for region in regions
    }


def _nearest_region(lat: float, lon: float, regions: tuple[Region, ...]) -> Region:
    """Containment wins; otherwise the bbox with the smallest degree distance, id tie-break."""

    def distance(candidate: Region) -> tuple[float, str]:
        min_lon, min_lat, max_lon, max_lat = candidate.bbox
        dx = max(min_lon - lon, 0.0, lon - max_lon)
        dy = max(min_lat - lat, 0.0, lat - max_lat)
        return dx * dx + dy * dy, candidate.id

    return min(regions, key=distance)


def _fmt_duration(seconds: float) -> str:
    """Format a wall duration for logs: seconds below a minute, else minutes."""
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    return f"{seconds / 60.0:.1f}m"


if __name__ == "__main__":
    main()
