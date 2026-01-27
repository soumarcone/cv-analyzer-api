"""Pydantic schemas for CV parsing responses."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ParseCVResponse(BaseModel):
    """Structured response for parsed CV content."""

    file_name: str | None = Field(
        default=None,
        description="Original filename of the uploaded CV (if provided by client).",
    )
    file_type: str = Field(
        ..., description="Detected file type: 'pdf' or 'docx'."
    )
    char_count: int = Field(
        ..., description="Number of characters extracted after normalization."
    )
    preview: str = Field(
        ..., description="First N characters of normalized text (N from config)."
    )
    text: str = Field(
        ..., description="Full extracted and normalized CV text."
    )
    warnings: List[str] = Field(
        default_factory=list,
        description=(
            "Warnings about extraction quality (e.g., very little text → possible OCR-needed PDF)."
        ),
    )
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Format-specific metadata (e.g., pages for PDF, paragraphs for DOCX).",
    )
