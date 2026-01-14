"""Unit tests for in-memory rate limiter adapter."""

from unittest.mock import Mock

import pytest

from app.adapters.rate_limit.in_memory import InMemoryFixedWindowRateLimiter


def test_allows_up_to_limit_in_same_window() -> None:
    clock = Mock(return_value=1000.0)
    limiter = InMemoryFixedWindowRateLimiter(limit=3, window_seconds=60, clock=clock)

    assert limiter.consume("k").allowed is True
    assert limiter.consume("k").allowed is True
    result = limiter.consume("k")
    assert result.allowed is True
    assert result.remaining == 0


def test_blocks_when_over_limit() -> None:
    clock = Mock(return_value=1000.0)
    limiter = InMemoryFixedWindowRateLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.consume("k").allowed is True
    assert limiter.consume("k").allowed is True

    blocked = limiter.consume("k")
    assert blocked.allowed is False
    assert blocked.remaining == 0
    assert blocked.retry_after_seconds is not None
    assert blocked.retry_after_seconds > 0


def test_resets_on_new_window() -> None:
    clock = Mock(return_value=1000.0)
    limiter = InMemoryFixedWindowRateLimiter(limit=1, window_seconds=10, clock=clock)

    assert limiter.consume("k").allowed is True
    assert limiter.consume("k").allowed is False

    clock.return_value = 1010.0
    assert limiter.consume("k").allowed is True


def test_isolated_by_key() -> None:
    clock = Mock(return_value=1000.0)
    limiter = InMemoryFixedWindowRateLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.consume("k1").allowed is True
    assert limiter.consume("k1").allowed is False

    assert limiter.consume("k2").allowed is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0, "window_seconds": 60},
        {"limit": 1, "window_seconds": 0},
    ],
)
def test_invalid_constructor_args(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        InMemoryFixedWindowRateLimiter(**kwargs)


def test_invalid_consume_args() -> None:
    limiter = InMemoryFixedWindowRateLimiter(limit=1, window_seconds=60)

    with pytest.raises(ValueError):
        limiter.consume("")

    with pytest.raises(ValueError):
        limiter.consume("k", cost=0)
