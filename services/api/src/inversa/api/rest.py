"""REST endpoints for map and timeline state (spec-05 section 1)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import duckdb
from fastapi import APIRouter, Request, Response
from fastapi.encoders import jsonable_encoder
from inversa.api.db.engine import open_cursor
from inversa.api.db.queries import Snapshot, TimelineRow, run_snapshot, run_timeline_summary

router = APIRouter(prefix="/api", tags=["gateway"])

CACHE_CONTROL: str = "public, max-age=60, must-revalidate"


@router.get("/timeline/summary", response_model=list[TimelineRow])
def timeline_summary(start: datetime, end: datetime, request: Request) -> Response:
    """Hourly pre-aggregated buckets powering 60fps timeline scrubbing (spec-05 section 1)."""
    with _query_cursor() as cursor:
        rows = run_timeline_summary(cursor, start_ts=start, end_ts=end)
    return _etag_response(rows, request)


@router.get("/snapshot", response_model=Snapshot)
def snapshot(timestamp: datetime, request: Request) -> Response:
    """Map state at one instant: trailing fires, latest stations, wind vectors (spec-05)."""
    with _query_cursor() as cursor:
        state = run_snapshot(cursor, target_ts=timestamp)
    return _etag_response(state, request)


@contextmanager
def _query_cursor() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield an isolated, UTC-pinned DuckDB cursor and always dispose it."""
    cursor = open_cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _etag_matches(if_none_match: str, etag: str) -> bool:
    """RFC 9110 If-None-Match weak comparison: wildcard, weak tags, and comma lists."""
    if if_none_match.strip() == "*":
        return True

    def _opaque(tag: str) -> str:
        trimmed = tag.strip()
        return trimmed[2:] if trimmed.startswith("W/") else trimmed

    return etag in {_opaque(tag) for tag in if_none_match.split(",")}


def _etag_response(payload: Snapshot | list[TimelineRow], request: Request) -> Response:
    """Serialize once, attach a strong ETag + short cache lifetime, honor If-None-Match.

    Snapshots and bucket sums are deterministic for their query window's data:
    the ETag only needs to survive revalidation long enough to absorb scrubbing
    replays of the same instant without hiding late FIRMS/OAQ arrivals for long.
    """
    body = json.dumps(jsonable_encoder(payload)).encode()
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL, "Vary": "Accept-Encoding"}
    if_none_match = request.headers.get("if-none-match")
    if if_none_match is not None and _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
