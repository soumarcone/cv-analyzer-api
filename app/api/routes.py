from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.cv_parser_service import parse_cv_file

router = APIRouter()


@router.post("/cv/parse")
async def parse_cv(cv_file: UploadFile = File(...)) -> dict:
    """Parse uploaded CV file endpoint.
    
    Accepts PDF or DOCX files, extracts text content, and returns
    structured parsing results.
    
    Args:
        cv_file: Uploaded CV file (PDF or DOCX).
    
    Returns:
        dict: Parsing results with extracted text preview and metadata.
    
    Raises:
        HTTPException: 400 error if file type is invalid or file is empty.
    """
    try:
        result = await parse_cv_file(cv_file)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
