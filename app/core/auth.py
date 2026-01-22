"""API Key authentication logic.

This module provides simple API key authentication for the MVP.
Keys are validated against a comma-separated list from environment variables.

Design principles:
- Single Responsibility: Only handles API key validation
- Dependency Injection: Used via FastAPI Depends() for loose coupling
- Configuration-driven: Keys managed via env vars, not hardcoded
- Testable: Pure function logic with minimal dependencies
"""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import settings
from app.core.errors import AuthenticationAppError

logger = logging.getLogger(__name__)


def parse_api_keys(keys_string: str | None) -> set[str]:
    """Parse comma-separated API keys into a set.
    
    Args:
        keys_string: Comma-separated string of API keys, or None.
    
    Returns:
        Set of trimmed, non-empty API keys.
    
    Examples:
        >>> parse_api_keys("key1,key2,key3")
        {'key1', 'key2', 'key3'}
        >>> parse_api_keys("key1, key2 , key3 ")
        {'key1', 'key2', 'key3'}
        >>> parse_api_keys(None)
        set()
        >>> parse_api_keys("")
        set()
    """
    if not keys_string:
        return set()
    
    keys = {key.strip() for key in keys_string.split(",") if key.strip()}
    return keys


def validate_api_key(provided_key: str) -> None:
    """Validate that provided API key matches configured keys.
    
    Pure validation logic without FastAPI dependencies for easy testing.
    
    Args:
        provided_key: API key to validate.
    
    Raises:
        AuthenticationAppError: If key is invalid or authentication is required but no keys configured.
    """
    if not settings.app.api_key_required:
        # Authentication disabled - allow all requests
        return
    
    valid_keys = parse_api_keys(settings.app.api_keys)
    
    if not valid_keys:
        logger.error(
            "api_key_validation_failed",
            extra={
                "reason": "api_keys_not_configured",
                "auth_required": settings.app.api_key_required,
            },
        )
        raise AuthenticationAppError(
            code="api_keys_not_configured",
            message="API key authentication is enabled but no valid keys are configured",
            details={"hint": "Set API_KEYS environment variable or disable auth with API_KEY_REQUIRED=false"},
        )
    
    if provided_key not in valid_keys:
        api_key_hash = hashlib.sha256(provided_key.encode()).hexdigest()[:16]
        logger.warning(
            "api_key_validation_failed",
            extra={
                "reason": "invalid_api_key",
                "api_key_hash": api_key_hash,
                "auth_required": settings.app.api_key_required,
            },
        )
        raise AuthenticationAppError(
            code="invalid_api_key",
            message="Invalid or missing API key",
            details={"provided_key_length": len(provided_key) if provided_key else 0},
        )


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """FastAPI dependency for API key authentication.
    
    Validates the X-API-Key header against configured API keys.
    Can be disabled by setting API_KEY_REQUIRED=false in configuration.
    
    Usage:
        @router.post("/protected", dependencies=[Depends(verify_api_key)])
        async def protected_endpoint():
            return {"message": "Authenticated!"}
    
    Args:
        x_api_key: API key from X-API-Key header (injected by FastAPI).
    
    Raises:
        HTTPException: 403 Forbidden if authentication fails.
    """
    if not settings.app.api_key_required:
        # Authentication disabled - early return
        logger.debug(
            "auth.skipped",
            extra={"reason": "auth_required_false"},
        )
        return
    
    if not x_api_key:
        logger.warning(
            "auth.missing_key",
            extra={
                "auth_required": True,
                "api_key_present": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key. Provide X-API-Key header.",
        )
    
    try:
        validate_api_key(x_api_key)
        logger.info(
            "auth.success",
            extra={
                "auth_required": True,
                "api_key_present": True,
                "api_key_hash": hashlib.sha256(x_api_key.encode()).hexdigest()[:16],
            },
        )
    except AuthenticationAppError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.message,
        ) from exc
