"""Parquet datalake writes with a per-run ingestion log."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Final, NamedTuple

import polars as pl
from inversa.ingestion.contract import DATETIME

LOG_SCHEMA: Final[pl.Schema] = pl.Schema(
    {
        "source": pl.String(),
        "region": pl.String(),
        "run_at": DATETIME,
        "latest_data_ts": DATETIME,
        "known_latency_minutes": pl.Int32(),
        "records_written": pl.Int32(),
        "status": pl.String(),
    }
)


class SourceSpec(NamedTuple):
    """Parquet layout facts for one source: folder, file prefix, known latency."""

    folder: str
    prefix: str
    latency_minutes: int


SOURCE_SPECS: Final[dict[str, SourceSpec]] = {
    "nasa_firms": SourceSpec(folder="fires", prefix="fires", latency_minutes=180),
    "openaq": SourceSpec(folder="air_quality", prefix="openaq", latency_minutes=15),
    "open_meteo": SourceSpec(folder="weather", prefix="meteo", latency_minutes=0),
}
logger: Final[logging.Logger] = logging.getLogger(__name__)


def record_batch(
    df: pl.DataFrame,
    *,
    root: Path,
    source: str,
    region: str,
    run_at: datetime,
    rejected: int = 0,
) -> list[Path]:
    """Write date-partitioned Parquet and append the run log; return written paths."""
    spec = SOURCE_SPECS[source]
    tagged = df.with_columns(region=pl.lit(region, dtype=pl.String))
    paths: list[Path] = []
    if tagged.height:
        suffix = run_at.strftime("%H%M")
        sliced = tagged.with_columns(_partition=pl.col("observed_at").dt.strftime("%Y-%m-%d"))
        for date in sliced["_partition"].unique().sort():
            part = sliced.filter(pl.col("_partition") == date).select(tagged.columns)
            directory = root / spec.folder / f"date={date}"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{spec.prefix}_{region}_{suffix}.parquet"
            part.write_parquet(path, compression="zstd")
            paths.append(path)
    observed_max = tagged["observed_at"].max() if tagged.height else None
    latest = observed_max if isinstance(observed_max, datetime) else None
    status = "partial" if rejected else "success"
    _append_log(
        root,
        source=source,
        region=region,
        run_at=run_at,
        records=tagged.height,
        latest=latest,
        status=status,
    )
    logger.info(
        "storage: %s/%s: %d rows in %d file(s), status=%s",
        source,
        region,
        tagged.height,
        len(paths),
        status,
    )
    return paths


def record_failure(root: Path, *, source: str, region: str, run_at: datetime) -> None:
    """Append a failed-run log entry with zero records."""
    _append_log(
        root, source=source, region=region, run_at=run_at, records=0, latest=None, status="failed"
    )
    logger.warning("storage: %s/%s: run failed, recorded in ingestion log", source, region)


def _append_log(
    root: Path,
    *,
    source: str,
    region: str,
    run_at: datetime,
    records: int,
    latest: datetime | None,
    status: str,
) -> None:
    row = pl.DataFrame(
        {
            "source": [source],
            "region": [region],
            "run_at": [run_at],
            "latest_data_ts": [latest],
            "known_latency_minutes": [SOURCE_SPECS[source].latency_minutes],
            "records_written": [records],
            "status": [status],
        },
        schema=LOG_SCHEMA,
    )
    path = root / "meta" / "ingestion_log.parquet"
    if path.exists():
        table = pl.concat([pl.read_parquet(path), row], how="diagonal")
    else:
        table = row
    path.parent.mkdir(parents=True, exist_ok=True)
    table.write_parquet(path, compression="zstd")
