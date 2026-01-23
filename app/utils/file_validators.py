"""File validation utilities for content security.

Validates file signatures (magic numbers) to prevent MIME type spoofing,
and checks ZIP file safety for DOCX files.
"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from typing import Literal, Optional, cast

logger = logging.getLogger(__name__)

FileType = Literal["pdf", "docx"]


def validate_file_signature(data: bytes, expected_type: FileType) -> bool:
    """Validate file magic numbers to prevent MIME type spoofing.

    Checks the binary signature of the file against the expected file type.
    This prevents attackers from renaming malicious files (e.g., .exe) as
    legitimate documents (.pdf, .docx).

    Args:
        data: File content as bytes.
        expected_type: Expected file type ('pdf' or 'docx').

    Returns:
        True if signature matches the expected type, False otherwise.
    """
    # Magic number signatures for supported formats
    SIGNATURES = {
        "pdf": [b"%PDF-"],  # PDF files start with %PDF-
        "docx": [
            b"PK\x03\x04",  # ZIP signature (DOCX is ZIP-based)
        ],
    }

    signatures = SIGNATURES.get(expected_type, [])
    for sig in signatures:
        if data.startswith(sig):
            return True

    logger.warning(
        "file_signature.invalid",
        extra={
            "expected_type": expected_type,
            "actual_prefix": data[:10] if data else "EMPTY",
        },
    )
    return False


def get_file_type_from_mime(mime_type: str) -> Optional[FileType]:
    """Map MIME type to internal file type.

    Args:
        mime_type: MIME type string (e.g., 'application/pdf').

    Returns:
        FileType ('pdf' or 'docx') or None if unsupported.
    """
    mime_map = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        # Common alternative MIME types for DOCX
        "application/vnd.ms-word.document.macroEnabled.12": "docx",
    }
    return cast(Optional[FileType], mime_map.get(mime_type))


def validate_zip_safety(
    data: bytes,
    max_ratio: float = 100.0,
    max_uncompressed_mb: int = 50,
) -> None:
    """Validate ZIP-based files against zip bomb attacks.

    DOCX files are ZIP archives. This function checks:
    1. Compression ratio (uncompressed/compressed) isn't suspiciously high
    2. Total uncompressed size isn't excessive

    Args:
        data: File content as bytes.
        max_ratio: Maximum allowed compression ratio (default: 100x).
        max_uncompressed_mb: Max uncompressed size in MB (default: 50MB).

    Raises:
        ValueError: If file appears to be a zip bomb.
    """
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            compressed_size = sum(info.compress_size for info in zf.filelist)
            uncompressed_size = sum(info.file_size for info in zf.filelist)

            # Prevent division by zero
            if compressed_size == 0:
                logger.warning("zip_safety.invalid_zip", extra={"reason": "zero_compressed_size"})
                raise ValueError("Invalid ZIP file: compressed size is zero")

            ratio = uncompressed_size / compressed_size
            max_bytes = max_uncompressed_mb * 1024 * 1024

            # Check compression ratio
            if ratio > max_ratio:
                logger.warning(
                    "zip_safety.suspicious_ratio",
                    extra={
                        "ratio": ratio,
                        "max_ratio": max_ratio,
                        "compressed_mb": compressed_size / (1024 * 1024),
                        "uncompressed_mb": uncompressed_size / (1024 * 1024),
                    },
                )
                raise ValueError(
                    f"Suspicious compression ratio: {ratio:.1f}x. "
                    f"Maximum allowed: {max_ratio}x"
                )

            # Check total uncompressed size
            if uncompressed_size > max_bytes:
                logger.warning(
                    "zip_safety.excessive_size",
                    extra={
                        "uncompressed_mb": uncompressed_size / (1024 * 1024),
                        "max_mb": max_uncompressed_mb,
                    },
                )
                raise ValueError(
                    f"Uncompressed size ({uncompressed_size / (1024 * 1024):.1f}MB) "
                    f"exceeds limit ({max_uncompressed_mb}MB)"
                )

            logger.info(
                "zip_safety.validated",
                extra={
                    "ratio": ratio,
                    "compressed_mb": compressed_size / (1024 * 1024),
                    "uncompressed_mb": uncompressed_size / (1024 * 1024),
                },
            )

    except zipfile.BadZipFile as exc:
        logger.warning("zip_safety.bad_zip", extra={"error": str(exc)})
        raise ValueError("Invalid ZIP file structure") from exc
