from fastapi import UploadFile
from app.utils.docx_extractor import extract_text_from_docx_bytes
from app.utils.pdf_extractor import extract_text_from_pdf_bytes
from app.utils.text_normalizer import normalize_text


SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


async def parse_cv_file(cv_file: UploadFile) -> dict:
    """Parse uploaded CV file and extract text content.
    
    Supports PDF and DOCX formats. Extracts text, normalizes it,
    and returns structured information including warnings for
    low-quality extractions.
    
    Args:
        cv_file: Uploaded file object from FastAPI.
    
    Returns:
        dict: Parsed CV data containing:
            - file_name (str): Original filename.
            - file_type (str): Detected type (pdf/docx).
            - char_count (int): Number of characters extracted.
            - preview (str): First 800 characters of normalized text.
            - warnings (list[str]): Any warnings about extraction quality.
            - meta (dict): File-specific metadata (pages/paragraphs).
    
    Raises:
        ValueError: If file type is unsupported or file is empty.
    """
    if cv_file.content_type not in SUPPORTED_MIME_TYPES:
        supported_formats = ", ".join(sorted(SUPPORTED_MIME_TYPES.values())).upper()
        raise ValueError(f"Unsupported file type. Only {supported_formats} are allowed.")

    raw_bytes = await cv_file.read()
    if not raw_bytes:
        raise ValueError("Empty file.")

    file_type = SUPPORTED_MIME_TYPES[cv_file.content_type]

    if file_type == "pdf":
        extracted_text, meta = extract_text_from_pdf_bytes(raw_bytes)
    else:
        extracted_text, meta = extract_text_from_docx_bytes(raw_bytes)

    normalized = normalize_text(extracted_text)

    warnings: list[str] = []
    if len(normalized) < 500:
        warnings.append("Very little text extracted. PDF may be image-based (OCR not supported in MVP).")

    preview = normalized[:800]

    return {
        "file_name": cv_file.filename,
        "file_type": file_type,
        "char_count": len(normalized),
        "preview": preview,
        "warnings": warnings,
        "meta": meta,
    }
