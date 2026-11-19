"""REST endpoints for map and timeline state (spec-05 section 1)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from urllib.parse import urlencode

import duckdb
from fastapi import APIRouter, Request, Response
from fastapi.encoders import jsonable_encoder
from inversa.api.db.engine import active_settings, open_cursor
from inversa.api.db.queries import (
    Snapshot,
    SnapshotRegion,
    TimelineRow,
    run_snapshot,
    run_timeline_summary,
)
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api", tags=["gateway"])

CACHE_CONTROL: str = "public, max-age=60, must-revalidate"

_MAX_ENTRIES: int = 512

_CacheBuild = Callable[[], Snapshot | list[TimelineRow]]


@router.get("/timeline/summary", response_model=list[TimelineRow])
def timeline_summary(start: datetime, end: datetime, request: Request) -> Response:
    """Hourly pre-aggregated buckets powering 60fps timeline scrubbing (spec-05 section 1)."""
    key = _cache_key("timeline/summary", start=_utc_instant(start), end=_utc_instant(end))

    def build() -> list[TimelineRow]:
        with _query_cursor() as cursor:
            return run_timeline_summary(cursor, start_ts=start, end_ts=end)

    return _cached_response(key, build, request)


@router.get("/snapshot", response_model=Snapshot)
def snapshot(timestamp: datetime, request: Request) -> Response:
    """Map state at one instant: trailing fires, latest stations, wind vectors (spec-05)."""
    key = _cache_key("snapshot", timestamp=_utc_instant(timestamp))

    def build() -> Snapshot:
        with _query_cursor() as cursor:
            data = run_snapshot(cursor, target_ts=timestamp)
        return data.model_copy(update={"regions": _snapshot_regions()})

    return _cached_response(key, build, request)


def _snapshot_regions() -> list[SnapshotRegion]:
    """Expose the configured study areas so the map can outline every bbox."""
    return [
        SnapshotRegion(id=region.id, label=region.label, bbox=region.bbox)
        for region in active_settings().regions
    ]


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


def _utc_instant(value: datetime) -> str:
    """Normalize a query timestamp to one stable UTC instant string for cache keys."""
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(UTC).isoformat()


def _cache_key(endpoint: str, **params: str) -> str:
    """Stable cache key: endpoint path plus sorted, urlencoded query params."""
    return f"{endpoint}?{urlencode(sorted(params.items()))}"


class _CacheEntry(BaseModel):
    """Immutable cached response: exact body bytes and the strong ETag over them."""

    model_config = ConfigDict(frozen=True)

    body: bytes
    etag: str


class _StateCache:
    """Thread-safe TTL cache of serialized state bodies, created per app in create_app.

    Endpoints run in Starlette's threadpool, so the entry dict is guarded by a
    single lock; concurrent misses rebuild deterministically into identical
    bytes, so per-key lock choreography buys nothing. The TTL keeps staleness
    far below the ingestion cadence while absorbing scrub replays of the same
    window — the repeated full-lakeside parquet rescans that dominate deployed
    latency. The server TTL (~120s) deliberately outlives the client-facing
    max-age=60: both sit far under the ~2h ingestion cadence, so the effective
    freshness floor is the TTL, not the client header.
    """

    def __init__(self, ttl_ms: int) -> None:
        self._ttl_s = ttl_ms / 1000
        self._entries: dict[str, tuple[_CacheEntry, float]] = {}
        self._guard = threading.Lock()

    @property
    def enabled(self) -> bool:
        """Whether caching is active at all (a non-positive TTL disables it)."""
        return self._ttl_s > 0

    def get(self, key: str) -> _CacheEntry | None:
        """Return the live entry for key, evicting it in place if expired."""
        if not self.enabled:
            return None
        with self._guard:
            hit = self._entries.get(key)
            if hit is None:
                return None
            if time.monotonic() - hit[1] >= self._ttl_s:
                del self._entries[key]
                return None
        return hit[0]

    def put(self, key: str, entry: _CacheEntry) -> None:
        """Store an entry, sweeping stale keys once the cache grows past _MAX_ENTRIES."""
        if not self.enabled:
            return
        with self._guard:
            self._entries[key] = (entry, time.monotonic())
            if len(self._entries) > _MAX_ENTRIES:
                self._sweep(time.monotonic())

    def _sweep(self, now: float) -> None:
        """Drop expired entries, then the oldest stamps, until back under _MAX_ENTRIES."""
        expired = [k for k, (_, stamped) in self._entries.items() if now - stamped >= self._ttl_s]
        for key in expired:
            del self._entries[key]
        overflow = len(self._entries) - _MAX_ENTRIES
        if overflow <= 0:
            return
        oldest = sorted(self._entries.items(), key=lambda item: item[1][1])
        for key, _ in oldest[:overflow]:
            del self._entries[key]


def _cached_response(key: str, build: _CacheBuild, request: Request) -> Response:
    """Serve state from the per-app TTL cache, rebuilding through build() on a miss.

    Cache hits skip the DuckDB scan entirely; an expired entry, a new query
    window, or a disabled cache falls back to the serialize-once path. Either
    way the response carries a strong ETag, so If-None-Match replays collapse
    to 304s without touching the engine.
    """
    cache: _StateCache = request.app.state.state_cache
    entry = cache.get(key)
    if entry is None:
        body = json.dumps(jsonable_encoder(build())).encode()
        entry = _CacheEntry(body=body, etag=f'"{hashlib.sha256(body).hexdigest()}"')
        cache.put(key, entry)
    headers = {"ETag": entry.etag, "Cache-Control": CACHE_CONTROL, "Vary": "Accept-Encoding"}
    if_none_match = request.headers.get("if-none-match")
    if if_none_match is not None and _etag_matches(if_none_match, entry.etag):
        return Response(status_code=304, headers=headers)
    return Response(content=entry.body, media_type="application/json", headers=headers)
