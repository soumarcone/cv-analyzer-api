"""HTTP middleware for request ID propagation and correlation.

This module provides middleware that ensures every request/response pair
carries a unique request ID for distributed tracing and log correlation.

The middleware:
- Accepts incoming X-Request-ID header or generates a UUID
- Stores request_id in contextvars for access throughout the request lifecycle
- Injects request_id into response headers for client-side tracking
- Measures total request duration and includes it in response headers
- Clears context after request completion to prevent context leaks

Usage:
    app.middleware("http")(request_id_middleware)
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request, Response

from app.core.config import settings
from app.core.logging import clear_request_id, set_request_id


async def request_id_middleware(request: Request, call_next) -> Response:
    """HTTP middleware for request ID generation and propagation.

    Ensures every HTTP request/response pair carries a unique correlation ID
    for distributed tracing and log aggregation. Stores the request_id in
    contextvars so it's accessible throughout the entire request lifecycle,
    including in nested service calls and database queries.

    If the client provides an X-Request-ID header (configurable via
    REQUEST_ID_HEADER env var), that value is used. Otherwise, a new UUID
    is generated. The ID is then propagated back in the response headers
    and stored in contextvars for log correlation.

    Args:
        request: The incoming HTTP request object.
        call_next: The next middleware/route handler in the stack.

    Returns:
        Response: The response from the next handler with request_id and
            duration headers added.

    Side Effects:
        - Sets request_id in contextvars (accessible via get_request_id())
        - Clears request_id from contextvars after request completes
        - Adds X-Request-ID header to response
        - Adds X-Request-Duration-ms header to response

    Example:
        >>> # Request arrives with custom ID
        >>> # Headers: {"X-Request-ID": "req-abc-123"}
        >>> # Response includes:
        >>> # {"X-Request-ID": "req-abc-123", "X-Request-Duration-ms": "45.67"}
    """

    header_name = settings.log.request_id_header
    request_id = request.headers.get(header_name) or str(uuid.uuid4())
    set_request_id(request_id)
    start = time.perf_counter()
    try:
        response: Response = await call_next(request)
    finally:
        clear_request_id()

    duration_ms = (time.perf_counter() - start) * 1000
    response.headers[header_name] = request_id
    response.headers.setdefault("X-Request-Duration-ms", f"{duration_ms:.2f}")
    return response
