"""HTTP transport helpers: retry with backoff and rate-limit-aware pacing."""
from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Final

import httpx

MAX_ATTEMPTS: Final[int] = 4
BASE_DELAY_SECONDS: Final[float] = 0.5
MAX_DELAY_SECONDS: Final[float] = 8.0
RATE_LIMIT_MAX_SECONDS: Final[float] = 90.0
RETRYABLE_STATUS: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})
RATE_LIMIT_HEADERS: Final[tuple[str, ...]] = ("Retry-After", "x-ratelimit-reset")


async def sleep_for(seconds: float) -> None:
    """Async sleep indirection that tests can stub."""
    await asyncio.sleep(seconds)


class Pacer:
    """Async rate limiter holding a minimum interval between requests."""
    def __init__(self, min_interval: float, *, clock: Callable[[], float] | None = None) -> None:
        self._min_interval = min_interval
        self._clock: Callable[[], float] = time.monotonic if clock is None else clock
        self._next_start = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Reserve the next request slot, sleeping until it opens."""
        if self._min_interval <= 0.0:
            return
        async with self._lock:
            now = self._clock()
            if now < self._next_start:
                await sleep_for(self._next_start - now)
                now = max(self._clock(), self._next_start)
            self._next_start = now + self._min_interval


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
    request_timeout: float | httpx.Timeout = 60.0,
    pacer: Pacer | None = None,
) -> httpx.Response:
    """GET with bounded retries on 429/5xx and transport errors, honoring rate-limit hints."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        last_response: httpx.Response | None = None
        try:
            if pacer is not None:
                await pacer.acquire()
            response = await client.get(
                url, params=params, headers=headers, timeout=request_timeout
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                raise
            last_response = exc.response
        except httpx.TransportError:
            if attempt == MAX_ATTEMPTS:
                raise
        else:
            return response
        await sleep_for(_delay_after_failure(last_response, attempt))
    raise RuntimeError("get_with_retry exhausted attempts without returning a response")


def _hint_seconds(value: str) -> float | None:
    try:
        return max(0.0, min(RATE_LIMIT_MAX_SECONDS, float(value)))
    except ValueError:
        pass
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        return None
    delta = moment.timestamp() - time.time()
    return max(0.0, min(RATE_LIMIT_MAX_SECONDS, delta))


def _rate_limit_hint(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    for header in RATE_LIMIT_HEADERS:
        value: str | None = response.headers.get(header)
        if value is None:
            continue
        seconds = _hint_seconds(value)
        if seconds is not None:
            return seconds
    return None


def _delay_after_failure(response: httpx.Response | None, attempt: int) -> float:
    hint = _rate_limit_hint(response)
    if hint is not None:
        return hint
    bounded: float = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** (attempt - 1))
    return bounded + random.uniform(0.0, 0.25)
