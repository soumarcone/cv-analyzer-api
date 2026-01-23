"""File validation utilities for upload security."""
from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile
from app.core.config import settings

logger = logging.getLogger(__name__)


async def read_upload_file_limited(file: UploadFile) -> bytes:
    """Read an uploaded file in chunks enforcing the max size limit.

    Validates file size before reading to prevent memory exhaustion attacks.
    Uses file.size if available (multipart headers), falls back to chunked
    reading with enforcement.

    Args:
        file: FastAPI upload file instance.

    Returns:
        File content as bytes if within the allowed size limit.

    Raises:
        HTTPException: If the file exceeds the configured size limit.
    """
    max_bytes = settings.app.max_upload_size_mb * 1024 * 1024

    # Check size from multipart headers if available
    file_size = getattr(file, "size", None)

    if file_size is not None and file_size > max_bytes:
        logger.warning(
            "file_validation.rejected_by_header",
            extra={"file_size": file_size, "max_bytes": max_bytes},
        )
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.app.max_upload_size_mb}MB",
        )

    # Chunked reading with secondary enforcement
    size = 0
    chunks: list[bytes] = []

    while True:
        chunk = await file.read(8192)
        if not chunk:
            break

        size += len(chunk)
        if size > max_bytes:
            logger.warning(
                "file_validation.rejected_by_chunked_read",
                extra={"size": size, "max_bytes": max_bytes},
            )
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {settings.app.max_upload_size_mb}MB",
            )
        chunks.append(chunk)

    return b"".join(chunks)
