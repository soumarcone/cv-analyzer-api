"""Unit tests for PDF extractor with page limit validation."""

import io
import pytest
from pypdf import PdfWriter
from app.utils.pdf_extractor import extract_text_from_pdf_bytes
from app.core.config import settings


class TestPDFExtractorPageLimits:
    """Test PDF page limit enforcement."""

    def _create_pdf_with_pages(self, num_pages: int) -> bytes:
        """Create a PDF with specified number of pages.
        
        Args:
            num_pages: Number of pages to create.
            
        Returns:
            bytes: PDF file content.
        """
        writer = PdfWriter()
        
        for i in range(num_pages):
            writer.add_blank_page(width=612, height=792)  # US Letter size
            
        buffer = io.BytesIO()
        writer.write(buffer)
        buffer.seek(0)
        return buffer.read()

    def test_extract_pdf_within_limit(self):
        """PDF with pages within limit should extract successfully."""
        # Create PDF with 10 pages (well below default limit of 50)
        pdf_data = self._create_pdf_with_pages(10)
        
        text, meta = extract_text_from_pdf_bytes(pdf_data)
        
        assert isinstance(text, str)
        assert meta["pages"] == 10

    def test_extract_pdf_at_exact_limit(self):
        """PDF with exactly max pages should extract successfully."""
        max_pages = settings.app.max_pdf_pages
        pdf_data = self._create_pdf_with_pages(max_pages)
        
        text, meta = extract_text_from_pdf_bytes(pdf_data)
        
        assert isinstance(text, str)
        assert meta["pages"] == max_pages

    def test_extract_pdf_exceeds_limit(self):
        """PDF exceeding page limit should raise ValueError."""
        max_pages = settings.app.max_pdf_pages
        pdf_data = self._create_pdf_with_pages(max_pages + 1)
        
        with pytest.raises(ValueError) as exc_info:
            extract_text_from_pdf_bytes(pdf_data)
        
        error_msg = str(exc_info.value)
        assert "too many pages" in error_msg.lower()
        assert str(max_pages + 1) in error_msg
        assert str(max_pages) in error_msg

    def test_extract_pdf_far_exceeds_limit(self):
        """PDF with many pages over limit should be rejected."""
        max_pages = settings.app.max_pdf_pages
        # Create PDF with double the limit
        pdf_data = self._create_pdf_with_pages(max_pages * 2)
        
        with pytest.raises(ValueError) as exc_info:
            extract_text_from_pdf_bytes(pdf_data)
        
        error_msg = str(exc_info.value)
        assert "too many pages" in error_msg.lower()
