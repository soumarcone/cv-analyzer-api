"""Global exception handlers for consistent error responses.

This module provides FastAPI exception handlers that intercept all errors
(domain and unexpected) and return consistent JSON responses with proper
HTTP status codes and traceability.

Design:
- AppError subclasses → appropriate HTTP status (400, 403, 500)
- Unexpected Exception → generic 500 (safety net)
- All responses include request_id for distributed tracing
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError, ValidationAppError, AuthenticationAppError, LLMAppError
from app.core.logging import get_request_id

logger = logging.getLogger(__name__)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle domain application errors with consistent JSON format.
    
    Routes domain errors to appropriate HTTP status codes:
    - ValidationAppError → 400 Bad Request (client fault)
    - AuthenticationAppError → 403 Forbidden (authorization fault)
    - LLMAppError → 500 Internal Server Error (server fault)
    
    All responses include:
    - error.code: Machine-readable error code
    - error.message: Human-readable message
    - error.request_id: For distributed tracing
    - error.details: Optional structured context
    
    Args:
        request: FastAPI request object.
        exc: AppError instance (or subclass).
    
    Returns:
        JSONResponse with appropriate status code and error details.
    """
    # Determine HTTP status code based on error type
    status_code = 400  # Default: client error
    if isinstance(exc, AuthenticationAppError):
        status_code = 403  # Forbidden (authorization)
    elif isinstance(exc, LLMAppError):
        status_code = 500  # Server error
    
    logger.warning(
        "app_error_handled",
        extra={
            "error_code": exc.code,
            "error_message": exc.message,
            "status_code": status_code,
            "has_details": bool(exc.details),
            "request_id": get_request_id(),
        }
    )
    
    # Build response with consistent structure
    error_content = {
        "code": exc.code,
        "message": exc.message,
        "request_id": get_request_id(),
    }
    
    # Include details only if present (optional structured context)
    if exc.details:
        error_content["details"] = exc.details
    
    return JSONResponse(
        status_code=status_code,
        content={"error": error_content},
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unexpected errors (safety net).
    
    Catches any exception not handled by specific handlers.
    Logs detailed information for debugging while returning generic message.
    Prevents information leakage (no stack traces to client).
    
    Args:
        request: FastAPI request object.
        exc: Exception instance (unexpected).
    
    Returns:
        JSONResponse with generic error (no implementation details leaked).
    """
    logger.error(
        "unhandled_exception",
        extra={
            "error_type": type(exc).__name__,
            "error_msg": str(exc),
            "request_path": request.url.path,
            "request_method": request.method,
            "request_id": get_request_id(),
        }
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected error occurred. Please try again later.",
                "request_id": get_request_id(),
            }
        },
    )


def setup_exception_handlers(app) -> None:
    """Register all exception handlers with FastAPI app.
    
    Must be called during app initialization, before route registration.
    Order matters: specific handlers registered before general fallback.
    
    Args:
        app: FastAPI application instance.
    
    Example:
        >>> from fastapi import FastAPI
        >>> from app.core.exception_handlers import setup_exception_handlers
        >>> app = FastAPI()
        >>> setup_exception_handlers(app)
        >>> # Now all errors are handled consistently
    """
    app.exception_handler(AppError)(app_error_handler)
    app.exception_handler(Exception)(general_exception_handler)
