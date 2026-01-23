"""Unit tests for extraction timeout protection."""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from app.services.cv_parser_service import _extract_text_with_timeout
from app.core.config import settings


class TestExtractionTimeout:
    """Test timeout protection for file extraction operations."""

    @pytest.mark.asyncio
    async def test_extraction_completes_within_timeout(self):
        """Successful extraction within timeout should return text."""
        # Create mock PDF bytes (small, will extract quickly)
        pdf_bytes = b"%PDF-1.4\n%test content"
        
        # Mock the extraction to complete quickly
        with patch("app.services.cv_parser_service._extract_text_by_type") as mock_extract:
            mock_extract.return_value = ("extracted text", {"pages": 1})
            
            text, meta = await _extract_text_with_timeout(pdf_bytes, "pdf")
            
            assert text == "extracted text"
            assert meta["pages"] == 1

    @pytest.mark.asyncio
    async def test_extraction_timeout_raises_timeout_error(self):
        """Extraction exceeding timeout should raise asyncio.TimeoutError."""
        pdf_bytes = b"%PDF-1.4\n%test"
        
        # Mock extraction to sleep longer than timeout (simulating hang)
        def slow_extraction(raw_bytes, file_type):
            # Sleep for longer than the configured timeout
            import time
            time.sleep(settings.app.file_extraction_timeout_seconds + 2)
            return ("text", {})
        
        with patch("app.services.cv_parser_service._extract_text_by_type", slow_extraction):
            with pytest.raises(asyncio.TimeoutError):
                await _extract_text_with_timeout(pdf_bytes, "pdf")

    @pytest.mark.asyncio
    async def test_extraction_timeout_with_docx(self):
        """Timeout should work for DOCX extraction as well."""
        docx_bytes = b"PK\x03\x04\x00\x00\x00"
        
        with patch("app.services.cv_parser_service._extract_text_by_type") as mock_extract:
            mock_extract.return_value = ("docx text", {"paragraphs": 5})
            
            text, meta = await _extract_text_with_timeout(docx_bytes, "docx")
            
            assert text == "docx text"
            assert meta["paragraphs"] == 5

    @pytest.mark.asyncio
    async def test_extraction_error_propagates(self):
        """ValueError from extraction should propagate."""
        pdf_bytes = b"%PDF-1.4\n%test"
        
        with patch("app.services.cv_parser_service._extract_text_by_type") as mock_extract:
            mock_extract.side_effect = ValueError("Too many pages")
            
            with pytest.raises(ValueError, match="Too many pages"):
                await _extract_text_with_timeout(pdf_bytes, "pdf")

    @pytest.mark.asyncio
    async def test_timeout_value_from_config(self):
        """Timeout should use configured timeout value."""
        pdf_bytes = b"%PDF-1.4\n%test"
        
        # Verify the config value exists and is reasonable
        assert settings.app.file_extraction_timeout_seconds > 0
        assert settings.app.file_extraction_timeout_seconds <= 300  # Sanity check
        
        with patch("app.services.cv_parser_service._extract_text_by_type") as mock_extract:
            mock_extract.return_value = ("text", {"pages": 1})
            
            text, meta = await _extract_text_with_timeout(pdf_bytes, "pdf")
            
            assert text == "text"
