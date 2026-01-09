from io import BytesIO
from pypdf import PdfReader


def extract_text_from_pdf_bytes(data: bytes) -> tuple[str, dict]:
    """Extract text content from PDF file bytes.
    
    Args:
        data: Raw bytes of the PDF file.
    
    Returns:
        tuple: A tuple containing:
            - str: Extracted text from all pages.
            - dict: Metadata with page count.
    """
    reader = PdfReader(BytesIO(data))
    texts: list[str] = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        texts.append(page_text)

    full_text = "\n".join(texts).strip()
    meta = {"pages": len(reader.pages)}
    return full_text, meta
