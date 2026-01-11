"""Unit tests for the in-memory SimpleTTLCache."""

import threading
from typing import Any

import pytest

from app.schemas.analysis import CVAnalysisResponse
from app.utils import simple_cache
from app.utils.simple_cache import SimpleTTLCache, build_cache_key


class FakeTime:
    """Deterministic clock used to test expiration logic."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.current = start

    def time(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


def _sample_analysis(**overrides: Any) -> CVAnalysisResponse:
    base: dict[str, Any] = {
        "summary": "Test summary",
        "fit_score": 80,
        "fit_score_rationale": "Solid match",
        "strengths": ["fastapi"],
        "gaps": ["graphql"],
        "missing_keywords": ["kafka"],
        "rewrite_suggestions": ["Add metrics"],
        "ats_notes": ["Keep PDF"],
        "red_flags": ["none"],
        "next_steps": ["tweak resume"],
        "evidence": [],
        "confidence": "medium",
        "warnings": [],
        "cached": False,
    }
    base.update(overrides)
    return CVAnalysisResponse(**base)


def test_build_cache_key_is_stable_and_sensitive_to_changes() -> None:
    cv_bytes = b"file-bytes"
    job_desc = "python dev"

    key1 = build_cache_key(cv_bytes, job_desc)
    key2 = build_cache_key(cv_bytes, job_desc)
    key3 = build_cache_key(cv_bytes, job_desc + " senior")

    assert key1 == key2
    assert key1 != key3


def test_set_and_get_updates_hit_miss_counters() -> None:
    cache = SimpleTTLCache(ttl_seconds=10)

    assert cache.get("missing") is None

    analysis = _sample_analysis()
    cache.set("key", analysis)

    assert cache.get("key") == analysis

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_expired_entry_is_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_time = FakeTime()
    monkeypatch.setattr(simple_cache, "time", fake_time)

    cache = SimpleTTLCache(ttl_seconds=5)
    cache.set("key", {"data": True})

    fake_time.advance(6)

    assert cache.get("key") is None
    stats = cache.stats()
    assert stats["evictions"] == 1


def test_lru_eviction_removes_least_recently_used() -> None:
    cache = SimpleTTLCache(ttl_seconds=100, max_entries=2)
    cache.set("a", {"v": 1})
    cache.set("b", {"v": 2})

    # Access "a" so that "b" becomes least recently used
    assert cache.get("a") == {"v": 1}

    cache.set("c", {"v": 3})

    assert cache.get("a") == {"v": 1}
    assert cache.get("c") == {"v": 3}
    assert cache.get("b") is None


def test_clear_resets_state() -> None:
    cache = SimpleTTLCache(ttl_seconds=10)
    cache.set("a", {"v": 1})
    cache.set("b", {"v": 2})
    cache.get("a")

    cache.clear()

    stats = cache.stats()
    assert stats["entries"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["evictions"] == 0


def test_thread_safety_under_concurrent_sets() -> None:
    cache = SimpleTTLCache(ttl_seconds=30, max_entries=None)
    total_keys = 50

    def _writer(idx: int) -> None:
        cache.set(f"k-{idx}", {"v": idx})

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(total_keys)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert cache.stats()["entries"] == total_keys
    # Ensure a random subset is readable
    assert cache.get("k-0") == {"v": 0}
    assert cache.get("k-25") == {"v": 25}
    assert cache.get("k-49") == {"v": 49}