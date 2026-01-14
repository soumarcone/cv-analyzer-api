"""In-memory fixed-window rate limiter (MVP).

Notes:
- Per-process only: running multiple workers multiplies the effective limit.
- Thread-safe: uses a lock around shared state.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.adapters.rate_limit.base import AbstractRateLimiter, RateLimitResult


@dataclass
class _WindowState:
    window_start: int
    count: int


class InMemoryFixedWindowRateLimiter(AbstractRateLimiter):
    """Rate limiter using a fixed time window per key.

    This implementation is intentionally simple for the MVP. It limits requests
    per key within a fixed window of time (e.g., 60 requests per 60 seconds).

    Important:
        This limiter is per-process only. If the API runs with multiple workers
        (e.g., multiple Uvicorn/Gunicorn workers), each worker will enforce its
        own independent limits.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialize the in-memory rate limiter.

        Args:
            limit: Maximum number of allowed units per window.
            window_seconds: Size of the fixed window in seconds.
            clock: Time source function returning UNIX time in seconds.

        Raises:
            ValueError: If limit or window_seconds are invalid.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")

        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._state_by_key: dict[str, _WindowState] = {}

    def _get_window_bounds(self, now: float) -> tuple[int, int]:
        """Compute fixed-window boundaries for a given timestamp.

        Args:
            now: UNIX time in seconds.

        Returns:
            Tuple of (window_start_epoch_seconds, reset_at_epoch_seconds).
        """
        window_start = int(now // self._window_seconds) * self._window_seconds
        reset_at = window_start + self._window_seconds
        return window_start, reset_at

    def _get_or_reset_state(self, key: str, window_start: int) -> _WindowState:
        """Get the current state for key or reset it when window changes.

        Args:
            key: Rate limit key (e.g., API key).
            window_start: Current window start epoch seconds.

        Returns:
            The current window state for this key.
        """
        state = self._state_by_key.get(key)
        if state is None or state.window_start != window_start:
            state = _WindowState(window_start=window_start, count=0)
            self._state_by_key[key] = state
        return state

    def _build_allowed_result(self, *, remaining: int, reset_at: int) -> RateLimitResult:
        """Build a RateLimitResult for an allowed request."""
        return RateLimitResult(
            allowed=True,
            limit=self._limit,
            remaining=remaining,
            reset_at=int(reset_at),
            retry_after_seconds=None,
        )

    def _build_blocked_result(self, *, now: float, remaining: int, reset_at: int) -> RateLimitResult:
        """Build a RateLimitResult for a blocked request."""
        retry_after = max(0, int(math.ceil(reset_at - now)))
        return RateLimitResult(
            allowed=False,
            limit=self._limit,
            remaining=remaining,
            reset_at=int(reset_at),
            retry_after_seconds=retry_after,
        )

    def consume(self, key: str, *, cost: int = 1) -> RateLimitResult:
        """Consume rate limit budget for the provided key.

        This method both checks the current window usage and mutates the state
        if the request is allowed.

        Args:
            key: Unique identifier for rate limiting (e.g., API key).
            cost: Units to consume (default 1).

        Returns:
            RateLimitResult with allowance decision and metadata.

        Raises:
            ValueError: If key is empty or cost is invalid.
        """
        if cost < 1:
            raise ValueError("cost must be >= 1")
        if not key:
            raise ValueError("key must be a non-empty string")

        now = self._clock()
        window_start, reset_at = self._get_window_bounds(now)

        with self._lock:
            state = self._get_or_reset_state(key, window_start)

            if state.count + cost <= self._limit:
                state.count += cost
                remaining = max(0, self._limit - state.count)
                return self._build_allowed_result(remaining=remaining, reset_at=reset_at)

            remaining = max(0, self._limit - state.count)
            return self._build_blocked_result(now=now, remaining=remaining, reset_at=reset_at)
