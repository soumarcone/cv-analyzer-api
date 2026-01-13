from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.adapters.llm.factory import create_llm_client
from app.core.errors import ValidationAppError, LLMAppError
from app.schemas.analysis import CVAnalysisResponse
from app.services.analysis_service import AnalysisService
from app.services.cv_parser_service import parse_cv_file
from app.utils.simple_cache import SimpleTTLCache

router = APIRouter()

# Initialize dependencies for analysis endpoint
_llm_client = create_llm_client()
_cache = SimpleTTLCache(ttl_seconds=3600, max_entries=1024)
_analysis_service = AnalysisService(llm=_llm_client, cache=_cache)


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


@router.post("/cv/analyze", response_model=CVAnalysisResponse)
async def analyze_cv(
    cv_file: UploadFile = File(...),
    job_description: str = Form(...),
) -> CVAnalysisResponse:
    """Analyze CV against job description endpoint.
    
    Accepts a CV file (PDF or DOCX) and job description text, then returns
    comprehensive analysis including fit score, strengths, gaps, recommendations,
    and ATS optimization tips.
    
    Args:
        cv_file: Uploaded CV file (PDF or DOCX).
        job_description: Job description text to compare CV against.
    
    Returns:
        CVAnalysisResponse: Structured analysis with fit score, strengths,
            gaps, missing keywords, rewrite suggestions, ATS notes, and more.
    
    Raises:
        HTTPException: 400 for validation errors, 500 for LLM/processing errors.
    """
    # Step 1: Parse CV file and extract text
    try:
        parsed_cv = await parse_cv_file(cv_file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    
    # Step 2: Analyze CV against job description
    try:
        analysis = await _analysis_service.analyze(
            cv_text=parsed_cv["text"],
            job_text=job_description,
            warnings=parsed_cv.get("warnings"),
        )
        return analysis
    except ValidationAppError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except LLMAppError as exc:
        raise HTTPException(status_code=500, detail=exc.message)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during analysis: {str(exc)}",
        )
