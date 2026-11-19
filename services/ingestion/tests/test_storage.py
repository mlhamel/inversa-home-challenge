from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from inversa.ingestion import fetch_firms
from inversa.ingestion.contract import FIRES_SCHEMA, air_quality_rows
from inversa.ingestion.storage import LOG_SCHEMA, record_batch, record_failure
from inversa.ingestion.validate import air_quality
from samples import FIRMS_HEADER, FIRMS_ROW_A, FIRMS_ROW_D, RUN_AT


def test_record_batch_writes_partitioned_parquet(tmp_path: Path, run_at: datetime) -> None:
    paths = record_batch(
        _fires_frame(), root=tmp_path, source="nasa_firms", region="default", run_at=run_at
    )

    expected = tmp_path / "fires" / "date=2026-11-14" / "fires_default_1800.parquet"
    assert paths == [expected]
    back = pl.read_parquet(expected)
    assert back.height == 2
    assert back["region"].unique().to_list() == ["default"]
    assert back.select(FIRES_SCHEMA.names()).schema == FIRES_SCHEMA


def test_record_batch_splits_partitions_by_observed_date(tmp_path: Path, run_at: datetime) -> None:
    paths = record_batch(
        _air_frame(), root=tmp_path, source="openaq", region="default", run_at=run_at
    )

    assert [path.relative_to(tmp_path).as_posix() for path in paths] == [
        "air_quality/date=2026-11-16/openaq_default_1800.parquet",
        "air_quality/date=2026-11-17/openaq_default_1800.parquet",
    ]
    for path in paths:
        assert pl.read_parquet(path).height == 1


def test_record_batch_appends_ingestion_log(tmp_path: Path, run_at: datetime) -> None:
    record_batch(
        _fires_frame(), root=tmp_path, source="nasa_firms", region="default", run_at=run_at
    )
    record_batch(
        _fires_frame(), root=tmp_path, source="nasa_firms", region="default", run_at=run_at
    )

    log = pl.read_parquet(tmp_path / "meta" / "ingestion_log.parquet")
    assert log.schema == LOG_SCHEMA
    assert log.height == 2
    row = log.row(0, named=True)
    assert row["source"] == "nasa_firms"
    assert row["status"] == "success"
    assert row["records_written"] == 2
    assert row["known_latency_minutes"] == 180
    assert row["run_at"] == run_at
    assert row["latest_data_ts"] == datetime(2026, 11, 14, 18, 30, tzinfo=UTC)


def test_record_batch_flags_partial_on_rejected(tmp_path: Path, run_at: datetime) -> None:
    record_batch(
        _fires_frame(), root=tmp_path, source="nasa_firms", region="default", run_at=run_at,
        rejected=1,
    )

    log = pl.read_parquet(tmp_path / "meta" / "ingestion_log.parquet")
    assert log["status"].item() == "partial"
    assert log["records_written"].item() == 2
    assert log["region"].item() == "default"


def test_record_batch_empty_frame_writes_no_files_but_logs(
    tmp_path: Path, run_at: datetime
) -> None:
    schema_frame = fetch_firms.collect_sync(FIRMS_HEADER, ingested_at=RUN_AT).df
    paths = record_batch(
        schema_frame, root=tmp_path, source="nasa_firms", region="default", run_at=run_at
    )

    assert paths == []
    assert not (tmp_path / "fires").exists()
    log = pl.read_parquet(tmp_path / "meta" / "ingestion_log.parquet")
    row = log.row(0, named=True)
    assert row["records_written"] == 0
    assert row["latest_data_ts"] is None
    assert row["status"] == "success"


def test_record_failure_logs_failed_row(tmp_path: Path, run_at: datetime) -> None:
    record_failure(tmp_path, source="open_meteo", region="default", run_at=run_at)

    log = pl.read_parquet(tmp_path / "meta" / "ingestion_log.parquet")
    row = log.row(0, named=True)
    assert row["source"] == "open_meteo"
    assert row["region"] == "default"
    assert row["status"] == "failed"
    assert row["records_written"] == 0
    assert row["known_latency_minutes"] == 0
    assert row["latest_data_ts"] is None
    assert not (tmp_path / "weather").exists()


def _fires_frame() -> pl.DataFrame:
    payload = "\n".join([FIRMS_HEADER, FIRMS_ROW_A, FIRMS_ROW_D])
    return fetch_firms.collect_sync(payload, ingested_at=RUN_AT).df


def _air_frame() -> pl.DataFrame:
    readings = [
        air_quality(
            observed_at=datetime(2026, 11, 16, 23, 0, tzinfo=UTC),
            ingested_at=RUN_AT,
            station_id="2009",
            station_name="San Francisco",
            lat=37.7658,
            lon=-122.3978,
            pm25=7.5,
        ),
        air_quality(
            observed_at=datetime(2026, 11, 17, 0, 0, tzinfo=UTC),
            ingested_at=RUN_AT,
            station_id="2009",
            station_name="San Francisco",
            lat=37.7658,
            lon=-122.3978,
            pm25=8.1,
        ),
    ]
    return air_quality_rows(readings)
