from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from inversa.ingestion import http_retry
from inversa.ingestion.http_retry import get_with_retry


async def test_get_with_retry_succeeds_after_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http_retry, "sleep_for", _noop_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [
        httpx.Response(500),
        httpx.Response(429),
        httpx.Response(200, json={"ok": True}),
    ]
    async with _client(script, captured) as client:
        response = await get_with_retry(client, "https://api.test/locations")

    assert response.status_code == 200
    assert len(captured) == 3


async def test_get_with_retry_honors_retry_after_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(http_retry, "sleep_for", record_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [
        httpx.Response(429, headers={"Retry-After": "3"}),
        httpx.Response(200),
    ]
    async with _client(script, captured) as client:
        await get_with_retry(client, "https://api.test/locations")

    assert slept == [3.0]


async def test_get_with_retry_raises_immediately_on_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http_retry, "sleep_for", _noop_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [httpx.Response(404)]
    async with _client(script, captured) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_with_retry(client, "https://api.test/locations")

    assert len(captured) == 1


async def test_get_with_retry_exhausts_attempts_on_persistent_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http_retry, "sleep_for", _noop_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [httpx.Response(503)] * http_retry.MAX_ATTEMPTS
    async with _client(script, captured) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_with_retry(client, "https://api.test/locations")

    assert len(captured) == http_retry.MAX_ATTEMPTS


async def test_get_with_retry_retries_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http_retry, "sleep_for", _noop_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [
        httpx.ConnectError("connection refused", request=None),
        httpx.Response(200),
    ]
    async with _client(script, captured) as client:
        response = await get_with_retry(client, "https://api.test/locations")

    assert response.status_code == 200
    assert len(captured) == 2


async def test_get_with_retry_honors_x_ratelimit_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(http_retry, "sleep_for", record_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [
        httpx.Response(429, headers={"x-ratelimit-reset": "30"}),
        httpx.Response(200),
    ]
    async with _client(script, captured) as client:
        response = await get_with_retry(client, "https://api.test/locations")

    assert response.status_code == 200
    assert slept == [30.0]


async def test_pacer_spaces_requests_by_min_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"now": 10.0}
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(http_retry, "sleep_for", fake_sleep)
    pacer = http_retry.Pacer(2.0, clock=lambda: state["now"])
    await pacer.acquire()
    await pacer.acquire()
    await pacer.acquire()

    assert slept == [2.0, 2.0]


async def test_pacer_zero_interval_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(http_retry, "sleep_for", fake_sleep)
    pacer = http_retry.Pacer(0.0, clock=lambda: 100.0)
    await pacer.acquire()
    await pacer.acquire()

    assert slept == []


async def test_get_with_retry_honors_retry_after_http_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(http_retry, "sleep_for", record_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [
        httpx.Response(429, headers={"Retry-After": "Wed, 31 Dec 2098 00:00:00 GMT"}),
        httpx.Response(200),
    ]
    async with _client(script, captured) as client:
        response = await get_with_retry(client, "https://api.test/locations")

    assert response.status_code == 200
    assert slept == [http_retry.RATE_LIMIT_MAX_SECONDS]


async def test_get_with_retry_discards_stale_rate_limit_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(http_retry, "sleep_for", record_sleep)
    captured: list[httpx.Request] = []
    script: list[httpx.Response | BaseException] = [
        httpx.Response(429, headers={"x-ratelimit-reset": "30"}),
        httpx.ConnectError(
            "boom", request=httpx.Request("GET", "https://api.test/locations")
        ),
        httpx.Response(200),
    ]
    async with _client(script, captured) as client:
        response = await get_with_retry(client, "https://api.test/locations")

    assert response.status_code == 200
    assert slept[0] == 30.0
    assert 1.0 <= slept[1] <= 1.25


def _scripted(
    script: list[httpx.Response | BaseException], captured: list[httpx.Request]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        step = script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    return handler


def _client(
    script: list[httpx.Response | BaseException], captured: list[httpx.Request]
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_scripted(script, captured)))
