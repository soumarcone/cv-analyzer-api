"""In-memory TTL cache used to avoid repeated LLM calls.

Designed for the MVP: minimal dependencies, thread-safe, and easy to swap
for Redis while keeping the same interface and behaviors.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.schemas.analysis import CVAnalysisResponse

logger = logging.getLogger(__name__)


AnalysisValue = CVAnalysisResponse | dict[str, Any]


@dataclass
class CacheItem:
    """Container for cached values with expiration metadata."""

    value: AnalysisValue
    expires_at: float


class SimpleTTLCache:
    """Thread-safe, in-memory TTL cache with LRU eviction.

    Attributes:
        ttl_seconds: Time-to-live applied to all entries.
        max_entries: Maximum number of cached items (None for unlimited).
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int | None = 1024) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: OrderedDict[str, CacheItem] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def __repr__(self) -> str:  # pragma: no cover - representation only
        return (
            f"SimpleTTLCache(ttl_seconds={self._ttl}, max_entries={self._max_entries}, "
            f"size={len(self._store)}, hits={self._hits}, misses={self._misses}, "
            f"evictions={self._evictions})"
        )

    def get(self, key: str) -> AnalysisValue | None:
        """Retrieve a cached value if it exists and is not expired.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found/expired.
        """

        with self._lock:
            item = self._store.get(key)
            if not item:
                self._misses += 1
                logger.debug(
                    "cache.miss",
                    extra={
                        "cache_key": key[:16],
                        "reason": "not_found",
                    },
                )
                return None

            if self._is_expired(item):
                self._evict_single(key)
                self._misses += 1
                logger.debug(
                    "cache.miss",
                    extra={
                        "cache_key": key[:16],
                        "reason": "expired",
                    },
                )
                return None

            self._hits += 1
            self._store.move_to_end(key)  # mark as recently used
            logger.debug(
                "cache.hit",
                extra={
                    "cache_key": key[:16],
                },
            )
            return item.value

    def set(self, key: str, value: AnalysisValue) -> None:
        """Store a value with TTL, evicting as needed.

        Args:
            key: Cache key.
            value: Value to store (analysis payload or model dump).
        """

        with self._lock:
            self._evict_expired_locked()
            self._store[key] = CacheItem(value=value, expires_at=time.time() + self._ttl)
            self._store.move_to_end(key)
            self._evict_if_over_capacity_locked()

            logger.debug(
                "cache.set",
                extra={
                    "cache_key": key[:16],
                    "size": len(self._store),
                    "ttl_s": self._ttl,
                },
            )

    def clear(self) -> None:
        """Remove all cached entries and reset counters."""

        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def stats(self) -> dict[str, int | float | None]:
        """Return lightweight cache metrics without exposing values."""

        with self._lock:
            return {
                "ttl_seconds": self._ttl,
                "max_entries": self._max_entries,
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
            }

    def _evict_single(self, key: str) -> None:
        if key in self._store:
            self._store.pop(key, None)
            self._evictions += 1

    def _evict_expired_locked(self) -> None:
        now = time.time()
        expired_keys = [k for k, item in self._store.items() if item.expires_at <= now]
        for key in expired_keys:
            self._evict_single(key)

    def _evict_if_over_capacity_locked(self) -> None:
        if self._max_entries is None:
            return

        while len(self._store) > self._max_entries:
            # popitem(last=False) removes the least recently used entry
            key, _ = self._store.popitem(last=False)
            self._evictions += 1

    def _is_expired(self, item: CacheItem) -> bool:
        return time.time() > item.expires_at


def build_cache_key(cv_bytes: bytes, job_description: str, *, salt: str | None = None) -> str:
    """Build a stable cache key from CV bytes and job description.

    Args:
        cv_bytes: Raw CV file bytes (after upload, before parsing).
        job_description: Job description text.
        salt: Optional salt to partition keys by model/provider if needed.

    Returns:
        Hex-encoded SHA-256 digest string.
    """

    hasher = sha256()
    hasher.update(cv_bytes)
    hasher.update(job_description.encode())
    if salt:
        hasher.update(salt.encode())
    return hasher.hexdigest()