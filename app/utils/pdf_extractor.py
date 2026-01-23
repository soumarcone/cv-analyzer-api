from io import BytesIO
from pypdf import PdfReader
from app.core.config import settings


def extract_text_from_pdf_bytes(data: bytes) -> tuple[str, dict]:
    """Extract text content from PDF file bytes.
    
    Args:
        data: Raw bytes of the PDF file.
    
    Returns:
        tuple: A tuple containing:
            - str: Extracted text from all pages.
            - dict: Metadata with page count.
    
    Raises:
        ValueError: If PDF has too many pages.
    """
    reader = PdfReader(BytesIO(data))
    
    # Validate page count
    page_count = len(reader.pages)
    max_pages = settings.app.max_pdf_pages
    
    if page_count > max_pages:
        raise ValueError(
            f"PDF has too many pages: {page_count} (max allowed: {max_pages})"
        )
    
    texts: list[str] = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        texts.append(page_text)

    full_text = "\n".join(texts).strip()
    meta = {"pages": page_count}
    return full_text, meta
