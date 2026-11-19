"""Unit tests for the TTL cache backing the state REST endpoints."""

from __future__ import annotations

import time

import pytest
from inversa.api import rest as api_rest
from inversa.api.rest import _CacheEntry, _StateCache


def _entry(tag: str) -> _CacheEntry:
    return _CacheEntry(body=f'{{"v":"{tag}"}}'.encode(), etag=f'"{tag}"')


def test_put_then_get_returns_entry() -> None:
    cache = _StateCache(ttl_ms=60_000)
    cache.put("k", _entry("a"))
    assert cache.get("k") == _entry("a")


def test_expired_entry_reads_as_miss() -> None:
    cache = _StateCache(ttl_ms=10)
    cache.put("k", _entry("a"))
    time.sleep(0.03)
    assert cache.get("k") is None


def test_expired_entry_is_evicted_on_read() -> None:
    cache = _StateCache(ttl_ms=10)
    cache.put("k", _entry("a"))
    time.sleep(0.03)
    assert cache.get("k") is None
    assert not cache._entries


def test_put_sweeps_oldest_entries_past_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_rest, "_MAX_ENTRIES", 2)
    cache = _StateCache(ttl_ms=60_000)
    for tag in ("1", "2", "3"):
        cache.put(tag, _entry(tag))
    assert set(cache._entries) == {"2", "3"}


def test_unknown_key_reads_as_miss() -> None:
    cache = _StateCache(ttl_ms=60_000)
    assert cache.get("k") is None


def test_zero_ttl_disables_cache_entirely() -> None:
    cache = _StateCache(ttl_ms=0)
    cache.put("k", _entry("a"))
    assert cache.get("k") is None


def test_keys_are_cached_independently() -> None:
    cache = _StateCache(ttl_ms=60_000)
    cache.put("a", _entry("1"))
    cache.put("b", _entry("2"))
    assert cache.get("a") == _entry("1")
    assert cache.get("b") == _entry("2")
    assert cache.get("c") is None
