"""NASA FIRMS active-fire collector over the area CSV API."""
from __future__ import annotations

from datetime import UTC, date, datetime
from io import StringIO
from typing import Final

import httpx
import polars as pl
from inversa.ingestion.config import Settings
from inversa.ingestion.contract import FIRES_SCHEMA, fire_rows
from inversa.ingestion.http_retry import get_with_retry
from inversa.ingestion.result import CollectorError, CollectorResult
from inversa.ingestion.validate import ValidationError, detect_fire
from inversa.v1 import telemetry_pb2 as telemetry

BASE_URL: Final = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
MAX_DAY_RANGE: Final[int] = 5


RAW_SCHEMA: Final[pl.Schema] = pl.Schema({
    "latitude": pl.Float64(),
    "longitude": pl.Float64(),
    "acq_date": pl.String(),
    "acq_time": pl.String(),
    "satellite": pl.String(),
    "confidence": pl.String(),
    "frp": pl.Float64(),
})


def collect_sync(
    payload: str,
    *,
    ingested_at: datetime,
) -> CollectorResult:
    """Parse a FIRMS CSV payload into FireDetections, counting unusable rows."""
    text = payload.strip()
    if not text:
        return CollectorResult(df=pl.DataFrame(schema=FIRES_SCHEMA), rejected=0)
    if "invalid" in text.lower():
        raise CollectorError(f"FIRMS API rejected the query: {text!r}")
    try:
        raw = pl.read_csv(StringIO(text), schema_overrides=RAW_SCHEMA)
    except Exception as exc:
        raise CollectorError(f"FIRMS CSV parsing failed: {exc}") from exc
    if "acq_date" not in raw.columns or "acq_time" not in raw.columns:
        raise CollectorError(f"FIRMS CSV is missing acq columns, got {raw.columns}")
    observed = _parse_observed_at(raw)
    detections: list[telemetry.FireDetection] = []
    rejected = 0
    for record, observed_at in zip(raw.iter_rows(named=True), observed, strict=True):
        try:
            detections.append(
                detect_fire(
                    observed_at=observed_at,
                    ingested_at=ingested_at,
                    lat=record["latitude"],
                    lon=record["longitude"],
                    frp=record["frp"],
                    confidence_symbol=record["confidence"],
                    satellite=record["satellite"],
                )
            )
        except ValidationError:
            rejected += 1
    df = fire_rows(detections).unique(subset=["fire_id"], keep="first", maintain_order=True)
    return CollectorResult(df=df, rejected=rejected)


def window_payload(
    *, day_range: int = 1, end_date: date | None = None
) -> dict[str, int | date | None]:
    """Build the FIRMS query window: day_range with optional end_date."""
    return {"day_range": day_range, "end_date": end_date}


async def collect(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    ingested_at: datetime,
    day_range: int = 1,
    end_date: date | None = None,
) -> CollectorResult:
    """Fetch one FIRMS window with the configured map key and parse it."""
    if settings.firms_map_key is None:
        raise CollectorError("FIRMS_MAP_KEY is not configured")
    response = await get_with_retry(
        client, _url(settings, day_range, end_date), request_timeout=60.0
    )
    return collect_sync(response.text, ingested_at=ingested_at.astimezone(UTC))


def _url(settings: Settings, day_range: int, end_date: date | None) -> str:
    if not 1 <= day_range <= MAX_DAY_RANGE:
        msg = f"FIRMS day_range must be within [1..{MAX_DAY_RANGE}], got {day_range}"
        raise CollectorError(msg)
    base = f"{BASE_URL}/{settings.firms_map_key}/VIIRS_NOAA20_NRT/{settings.bbox_str}/{day_range}"
    return f"{base}/{end_date.isoformat()}" if end_date is not None else base


def _parse_observed_at(raw: pl.DataFrame) -> pl.Series:
    return raw.select(
        pl.format("{} {}", pl.col("acq_date"), pl.col("acq_time").cast(pl.String).str.zfill(4))
        .str.to_datetime("%Y-%m-%d %H%M", time_zone="UTC")
        .alias("observed_at")
    ).get_column("observed_at")
