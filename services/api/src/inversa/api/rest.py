"""REST endpoints for map and timeline state (spec-05 section 1)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import duckdb
from fastapi import APIRouter
from inversa.api.db.engine import open_cursor
from inversa.api.db.queries import Snapshot, TimelineRow, run_snapshot, run_timeline_summary

router = APIRouter(prefix="/api", tags=["gateway"])


@router.get("/timeline/summary")
def timeline_summary(start: datetime, end: datetime) -> list[TimelineRow]:
    """Hourly pre-aggregated buckets powering 60fps timeline scrubbing (spec-05 section 1)."""
    with _query_cursor() as cursor:
        return run_timeline_summary(cursor, start_ts=start, end_ts=end)


@router.get("/snapshot")
def snapshot(timestamp: datetime) -> Snapshot:
    """Map state at one instant: trailing fires, latest stations, wind vectors (spec-05)."""
    with _query_cursor() as cursor:
        return run_snapshot(cursor, target_ts=timestamp)


@contextmanager
def _query_cursor() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield an isolated, UTC-pinned DuckDB cursor and always dispose it."""
    cursor = open_cursor()
    try:
        yield cursor
    finally:
        cursor.close()
