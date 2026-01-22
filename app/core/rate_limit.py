"""Rate limiting dependency for FastAPI routes.

This module wires the rate limiting adapter into the HTTP layer.

Design goals:
- Minimal coupling: API routes depend on a dependency function only.
- Swap-friendly: storage backend can be replaced (e.g., Redis) behind an
  abstract interface.
- Safe defaults: disabled unless explicitly enabled via settings.

Rate limiting strategy (MVP):
- Global fixed-window limit per API key.
- If API key is missing (e.g., auth disabled), fall back to client IP.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.adapters.rate_limit.base import AbstractRateLimiter
from app.adapters.rate_limit.in_memory import InMemoryFixedWindowRateLimiter
from app.core.config import settings

logger = logging.getLogger(__name__)


_limiter: AbstractRateLimiter | None = None
_limiter_config: tuple[int, int] | None = None


def get_rate_limiter() -> AbstractRateLimiter:
    """Return a process-wide rate limiter instance.

    The instance is cached in-module to preserve state across requests.
    If configuration changes (primarily in tests), the limiter is rebuilt.

    Returns:
        AbstractRateLimiter: Configured limiter instance.
    """

    global _limiter, _limiter_config

    config = (
        settings.app.rate_limit_requests,
        settings.app.rate_limit_window_seconds,
    )

    if _limiter is None or _limiter_config != config:
        _limiter = InMemoryFixedWindowRateLimiter(
            limit=settings.app.rate_limit_requests,
            window_seconds=settings.app.rate_limit_window_seconds,
        )
        _limiter_config = config

    return _limiter


def _build_rate_limit_key(request: Request, x_api_key: str | None) -> str:
    """Build the limiter key for the current request.

    Args:
        request: FastAPI request.
        x_api_key: API key value from the X-API-Key header.

    Returns:
        str: Namespaced limiter key.
    """

    if x_api_key:
        return f"api_key:{x_api_key}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def _hash_limiter_key(key: str) -> str:
    """Hash the rate limit key for logging without exposing secrets."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def enforce_rate_limit(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """FastAPI dependency enforcing rate limits.

    When enabled, consumes 1 unit from the requester's budget. If the requester
    exceeds the configured rate, raises HTTP 429.

    Args:
        request: FastAPI request.
        x_api_key: API key from X-API-Key header.

    Raises:
        HTTPException: 429 Too Many Requests when rate limit is exceeded.
    """

    if not settings.app.rate_limit_enabled:
        return

    limiter = get_rate_limiter()
    key = _build_rate_limit_key(request, x_api_key)
    key_hash = _hash_limiter_key(key)
    key_type = "api_key" if x_api_key else "ip"

    result = limiter.consume(key)
    if result.allowed:
        logger.info(
            "rate_limit.allowed",
            extra={
                "key_type": key_type,
                "key_hash": key_hash,
                "limit": result.limit,
                "remaining": result.remaining,
                "window_s": settings.app.rate_limit_window_seconds,
            },
        )
        return

    retry_after = result.retry_after_seconds or 0
    logger.warning(
        "rate_limit.exceeded",
        extra={
            "key_type": key_type,
            "key_hash": key_hash,
            "limit": result.limit,
            "remaining": result.remaining,
            "window_s": settings.app.rate_limit_window_seconds,
            "retry_after_s": retry_after,
        },
    )

    headers: dict[str, str] = {}
    if settings.app.rate_limit_include_headers:
        headers["Retry-After"] = str(retry_after)
        headers["X-RateLimit-Limit"] = str(result.limit)
        headers["X-RateLimit-Remaining"] = str(result.remaining)
        headers["X-RateLimit-Reset"] = str(result.reset_at)

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Try again later.",
        headers=headers or None,
    )
