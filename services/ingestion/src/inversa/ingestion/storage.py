from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Final, NamedTuple

import polars as pl
from inversa.ingestion.contract import DATETIME

LOG_SCHEMA: Final[pl.Schema] = pl.Schema({
    "source": pl.String(),
    "run_at": DATETIME,
    "latest_data_ts": DATETIME,
    "known_latency_minutes": pl.Int32(),
    "records_written": pl.Int32(),
    "status": pl.String(),
})


class SourceSpec(NamedTuple):
    folder: str
    prefix: str
    latency_minutes: int


SOURCE_SPECS: Final[dict[str, SourceSpec]] = {
    "nasa_firms": SourceSpec(folder="fires", prefix="fires", latency_minutes=180),
    "openaq": SourceSpec(folder="air_quality", prefix="openaq", latency_minutes=15),
    "open_meteo": SourceSpec(folder="weather", prefix="meteo", latency_minutes=0),
}


def _append_log(
    root: Path,
    *,
    source: str,
    run_at: datetime,
    records: int,
    latest: datetime | None,
    status: str,
) -> None:
    row = pl.DataFrame(
        {
            "source": [source],
            "run_at": [run_at],
            "latest_data_ts": [latest],
            "known_latency_minutes": [SOURCE_SPECS[source].latency_minutes],
            "records_written": [records],
            "status": [status],
        },
        schema=LOG_SCHEMA,
    )
    path = root / "meta" / "ingestion_log.parquet"
    table = row if not path.exists() else pl.read_parquet(path).vstack(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.write_parquet(path, compression="zstd")


def record_batch(
    df: pl.DataFrame,
    *,
    root: Path,
    source: str,
    run_at: datetime,
    rejected: int = 0,
) -> list[Path]:
    spec = SOURCE_SPECS[source]
    paths: list[Path] = []
    if df.height:
        suffix = run_at.strftime("%H%M")
        sliced = df.with_columns(_partition=pl.col("observed_at").dt.strftime("%Y-%m-%d"))
        for date in sliced["_partition"].unique().sort():
            part = sliced.filter(pl.col("_partition") == date).select(df.columns)
            directory = root / spec.folder / f"date={date}"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{spec.prefix}_{suffix}.parquet"
            part.write_parquet(path, compression="zstd")
            paths.append(path)
    observed_max = df["observed_at"].max() if df.height else None
    latest = observed_max if isinstance(observed_max, datetime) else None
    status = "partial" if rejected else "success"
    _append_log(root, source=source, run_at=run_at, records=df.height, latest=latest, status=status)
    return paths


def record_failure(root: Path, *, source: str, run_at: datetime) -> None:
    _append_log(root, source=source, run_at=run_at, records=0, latest=None, status="failed")
