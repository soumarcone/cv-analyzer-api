from io import BytesIO
from docx import Document


def extract_text_from_docx_bytes(data: bytes) -> tuple[str, dict]:
    """Extract text content from DOCX file bytes.
    
    Args:
        data: Raw bytes of the DOCX file.
    
    Returns:
        tuple: A tuple containing:
            - str: Extracted text from all paragraphs.
            - dict: Metadata with paragraph count.
    """
    doc = Document(BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    full_text = "\n".join(paragraphs).strip()
    meta = {"paragraphs": len(paragraphs)}
    return full_text, meta