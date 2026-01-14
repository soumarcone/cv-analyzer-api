"""Rate limiter interfaces.

The API should depend on this abstraction (not the concrete implementation)
so we can swap storage backends later (e.g., Redis) with minimal changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    """Result of a rate limit check/consume operation.

    Attributes:
        allowed: Whether the request is allowed to proceed.
        limit: Max requests per window.
        remaining: Remaining requests in the current window (0 when blocked).
        reset_at: UNIX epoch seconds when the current window resets.
        retry_after_seconds: Suggested wait time in seconds when blocked.
    """

    allowed: bool
    limit: int
    remaining: int
    reset_at: int
    retry_after_seconds: int | None


class AbstractRateLimiter(ABC):
    """Interface for rate limiters."""

    @abstractmethod
    def consume(self, key: str, *, cost: int = 1) -> RateLimitResult:
        """Consume rate limit budget for a given key.

        Args:
            key: Unique identifier (e.g., API key, IP address).
            cost: Units to consume (default 1).

        Returns:
            RateLimitResult describing whether it was allowed.
        """
        raise NotImplementedError
