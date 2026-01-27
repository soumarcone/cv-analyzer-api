from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends

from app.adapters.llm.factory import create_llm_client
from app.core.auth import verify_api_key
from app.core.rate_limit import enforce_rate_limit
from app.core.errors import ValidationAppError, LLMAppError
from app.core.file_validation import read_upload_file_limited
from app.schemas.analysis import CVAnalysisResponse
from app.services.analysis_service import AnalysisService
from app.services.cv_parser_service import parse_cv_file
from app.utils.simple_cache import SimpleTTLCache

router = APIRouter(tags=["CV"])

# Initialize dependencies for analysis endpoint
_llm_client = create_llm_client()
_cache = SimpleTTLCache(ttl_seconds=3600, max_entries=1024)
_analysis_service = AnalysisService(llm=_llm_client, cache=_cache)


from app.schemas.parse import ParseCVResponse


@router.post(
    "/cv/parse",
    response_model=ParseCVResponse,
    dependencies=[Depends(verify_api_key), Depends(enforce_rate_limit)],
)
async def parse_cv(cv_file: UploadFile = File(...)) -> ParseCVResponse:
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
        file_bytes = await read_upload_file_limited(cv_file)
        result = await parse_cv_file(cv_file, file_bytes=file_bytes)
        return ParseCVResponse(**result)
    except ValidationAppError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        # Propagate HTTP errors (e.g., size limit) directly
        raise


@router.post(
    "/cv/analyze",
    response_model=CVAnalysisResponse,
    dependencies=[Depends(verify_api_key), Depends(enforce_rate_limit)],
)
async def analyze_cv(
    cv_file: UploadFile = File(..., description="CV file in PDF or DOCX format"),
    job_description: str = Form(
        ...,
        description="Job description text (supports multi-line). Include responsibilities, requirements, and company info.",
    ),
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
        file_bytes = await read_upload_file_limited(cv_file)
        parsed_cv = await parse_cv_file(cv_file, file_bytes=file_bytes)
    except ValidationAppError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    
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
