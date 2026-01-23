"""CV file parsing service with clear separation of concerns.

This module handles the extraction and validation of CV text from uploaded files.
It delegates format-specific extraction to specialized utilities while coordinating
the overall parsing workflow.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional, Tuple, cast
from fastapi import UploadFile

from app.core.config import settings
from app.utils.docx_extractor import extract_text_from_docx_bytes
from app.utils.pdf_extractor import extract_text_from_pdf_bytes
from app.utils.text_normalizer import normalize_text
from app.utils.file_validators import (
    validate_file_signature,
    get_file_type_from_mime,
    validate_zip_safety,
    FileType,
)

logger = logging.getLogger(__name__)


SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _validate_file_type(content_type: str | None) -> str:
    """Validate uploaded file MIME type.

    Args:
        content_type: MIME type from uploaded file.

    Returns:
        str: Normalized file type ('pdf' or 'docx').

    Raises:
        ValueError: If MIME type is unsupported.
    """
    if content_type not in SUPPORTED_MIME_TYPES:
        supported_formats = ", ".join(sorted(SUPPORTED_MIME_TYPES.values())).upper()
        raise ValueError(f"Unsupported file type. Only {supported_formats} are allowed.")

    return SUPPORTED_MIME_TYPES[content_type]


def _validate_file_signature(raw_bytes: bytes, file_type: str) -> None:
    """Validate file magic numbers to prevent MIME type spoofing.

    Checks that the binary signature matches the declared file type.
    This prevents attacks where malicious executables are renamed as PDFs/DOCXs.

    Args:
        raw_bytes: Raw file content.
        file_type: Expected file type ('pdf' or 'docx').

    Raises:
        ValueError: If file signature doesn't match declared type.
    """
    if not validate_file_signature(raw_bytes, cast(FileType, file_type)):
        logger.warning(
            "parse.invalid_signature",
            extra={"expected_type": file_type},
        )
        raise ValueError(
            f"File signature doesn't match declared type. Expected {file_type.upper()}."
        )

    logger.debug(
        "parse.signature_validated",
        extra={"file_type": file_type},
    )


def _extract_text_by_type(raw_bytes: bytes, file_type: str) -> Tuple[str, dict]:
    """Extract text from file bytes based on type.

    Args:
        raw_bytes: Raw file bytes.
        file_type: File type ('pdf' or 'docx').

    Returns:
        tuple: (extracted_text, metadata_dict)
    """
    if file_type == "pdf":
        return extract_text_from_pdf_bytes(raw_bytes)
    return extract_text_from_docx_bytes(raw_bytes)


def _build_warnings(normalized_text: str) -> list[str]:
    """Build warning messages based on extracted text quality.

    Args:
        normalized_text: Normalized CV text.

    Returns:
        list[str]: Warning messages (empty if no issues detected).
    """
    warnings: list[str] = []

    if len(normalized_text) < settings.app.min_cv_chars:
        warnings.append(
            "Very little text extracted. PDF may be image-based (OCR not supported in MVP)."
        )

    return warnings


async def parse_cv_file(cv_file: UploadFile, file_bytes: Optional[bytes] = None) -> dict:
    """Parse uploaded CV file and extract text content.

    Orchestrates the CV parsing workflow: validation, extraction, normalization,
    and quality checks. Returns structured data ready for analysis.

    Args:
        cv_file: Uploaded file object from FastAPI.

    Returns:
        dict: Parsed CV data containing:
            - file_name (str): Original filename.
            - file_type (str): Detected type (pdf/docx).
            - char_count (int): Number of characters extracted.
            - preview (str): First N characters of normalized text (N from config).
            - text (str): Full normalized extracted text.
            - warnings (list[str]): Any warnings about extraction quality.
            - meta (dict): File-specific metadata (pages/paragraphs).

    Raises:
        ValueError: If file type is unsupported or file is empty.
    """
    file_ext = None
    if cv_file.filename:
        file_ext = f".{cv_file.filename.split('.')[-1].lower()}"
    
    logger.info(
        "parse.start",
        extra={
            "file_name_ext": file_ext,
            "mime_type": cv_file.content_type,
        },
    )

    try:
        # Step 1: Validate file type
        file_type = _validate_file_type(cv_file.content_type)

        # Step 2: Read file bytes (validated in route when provided)
        raw_bytes = file_bytes if file_bytes is not None else await cv_file.read()
        if not raw_bytes:
            logger.error(
                "parse.empty_file",
                extra={"file_name_ext": file_ext},
            )
            raise ValueError("Empty file.")

        file_size = len(raw_bytes)
        logger.debug(
            "parse.bytes_read",
            extra={"size_bytes": file_size, "file_type": file_type},
        )

        # Step 3: Validate file signature (magic numbers)
        _validate_file_signature(raw_bytes, file_type)

        # Step 4: Validate ZIP safety for DOCX files
        if file_type == "docx":
            try:
                validate_zip_safety(raw_bytes)
            except ValueError as exc:
                logger.warning(
                    "parse.zip_validation_failed",
                    extra={"error": str(exc)},
                )
                raise ValueError(f"ZIP validation failed: {str(exc)}") from exc

        # Step 5: Extract text based on file type
        try:
            extracted_text, meta = _extract_text_by_type(raw_bytes, file_type)
        except ValueError as exc:
            # Handle page/paragraph limit errors from extractors
            logger.warning(
                "parse.file_too_complex",
                extra={"error": str(exc), "file_type": file_type},
            )
            raise ValueError(str(exc)) from exc

        # Step 4: Normalize text
        normalized_text = normalize_text(extracted_text)

        # Step 5: Build warnings based on text quality
        warnings = _build_warnings(normalized_text)

        # Step 6: Generate preview
        preview = normalized_text[:settings.app.cv_preview_chars]

        text_hash = hashlib.sha256(normalized_text.encode()).hexdigest()[:16]
        char_count = len(normalized_text)

        logger.info(
            "parse.success",
            extra={
                "file_type": file_type,
                "size_bytes": file_size,
                "char_count": char_count,
                "preview_len": len(preview),
                "cv_text_hash": text_hash,
                "warnings_count": len(warnings),
                "meta": meta,
            },
        )

        return {
            "file_name": cv_file.filename,
            "file_type": file_type,
            "char_count": char_count,
            "preview": preview,
            "text": normalized_text,
            "warnings": warnings,
            "meta": meta,
        }

    except ValueError as e:
        logger.error(
            "parse.validation_error",
            extra={
                "error_msg": str(e),
                "file_type": cv_file.content_type,
            },
        )
        raise
