"""Application-level exception types.

This module defines domain errors used across services/adapters, enabling
consistent error handling, logging, and API responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict


class ErrorDetails(TypedDict, total=False):
    """Structured error context for observability and clients.

    Fields are optional to keep backward compatibility while encouraging
    consistent shapes across the codebase.
    """

    code: str
    message: str
    hint: str
    min_value: int
    actual_value: int
    http_status: int
    retry_after: float
    file_type: str
    model: str
    request_id: str
    context: NotRequired[dict[str, Any]]


@dataclass
class AppError(Exception):
    """Base error for application/domain failures.

    Attributes:
        code: Stable, machine-readable error code.
        message: Human-readable error message.
        details: Optional structured details for debugging/observability.
    """

    code: str
    message: str
    details: ErrorDetails | None = None

    def __post_init__(self) -> None:
        # Populate Exception args so str(error) is useful in logs/tracebacks.
        super().__init__(self.message)


class ValidationAppError(AppError):
    """Raised when input/config validation fails."""


class LLMAppError(AppError):
    """Raised when LLM provider/client operations fail."""


class AuthenticationAppError(AppError):
    """Raised when authentication/authorization fails."""
