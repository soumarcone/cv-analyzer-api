"""CV analysis service orchestrating LLM calls, caching, and validation.

This service is the core business logic that transforms raw CV and job description
text into structured, validated analysis results. It handles:
- Input validation and normalization
- Prompt engineering and schema enforcement
- LLM orchestration with retry/fallback capability
- Response caching by content hash
- Output validation and error handling
"""

import hashlib
from typing import Any

from app.adapters.llm.base import AbstractLLMClient
from app.core.config import settings
from app.core.errors import ValidationAppError
from app.schemas.analysis import CVAnalysisResponse
from app.utils.simple_cache import SimpleTTLCache

# Prompt version for cache invalidation when prompt changes
PROMPT_VERSION = "v1"


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate text to max_chars if needed.

    Args:
        text: Input text to potentially truncate.
        max_chars: Maximum allowed character count.

    Returns:
        Tuple of (truncated_text, was_truncated).
    """
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _hash_inputs(cv_text: str, job_text: str) -> str:
    """Generate deterministic hash for cache key.

    Includes prompt version to invalidate cache when prompt logic changes.

    Args:
        cv_text: Normalized CV text.
        job_text: Normalized job description text.

    Returns:
        SHA256 hex digest string.
    """
    raw = f"{PROMPT_VERSION}::{cv_text}::{job_text}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def build_prompt(cv_text: str, job_text: str) -> str:
    """Build structured prompt for CV analysis.

    Enforces JSON-only output with all required fields and evidence-based claims.

    Args:
        cv_text: Candidate's resume text.
        job_text: Job description text.

    Returns:
        Formatted prompt string for LLM.
    """
    return f"""
You are an expert career advisor and ATS specialist. Analyze the provided CV against the job description and return a structured JSON response.

CRITICAL RULES:
- Return ONLY valid JSON matching the exact schema below
- Do NOT invent or hallucinate experience not present in the CV
- Support all claims with short verbatim quotes from the CV in the evidence array
- Be specific and actionable in all recommendations
- Focus on alignment with the actual job requirements

REQUIRED JSON STRUCTURE:
{{
  "summary": "Brief narrative summary of candidate's fit (2-3 sentences)",
  "fit_score": <integer 0-100>,
  "fit_score_rationale": "Detailed explanation for the score citing key strengths and gaps",
  "strengths": ["strength 1", "strength 2", ...],
  "gaps": ["gap 1", "gap 2", ...],
  "missing_keywords": ["keyword1", "keyword2", ...],
  "rewrite_suggestions": ["specific rewrite suggestion 1", ...],
  "ats_notes": ["ATS optimization tip 1", ...],
  "red_flags": ["potential concern 1", ...],
  "next_steps": ["actionable step 1", ...],
  "evidence": [
    {{"claim": "Has FastAPI experience", "cv_quote": "Built REST APIs using FastAPI"}},
    ...
  ],
  "confidence": "low" | "medium" | "high"
}}

FIELD GUIDANCE:
- summary: Focus on overall alignment and unique value proposition
- fit_score: 0-30 = poor fit, 31-60 = partial fit, 61-85 = good fit, 86-100 = excellent fit
- fit_score_rationale: Reference specific requirements from job vs CV experience
- strengths: Highlight matching skills, experience, and achievements
- gaps: Identify missing required skills or experience from job description
- missing_keywords: Important terms from job description absent or weak in CV
- rewrite_suggestions: Specific content improvements (e.g., "Add metrics to project X")
- ats_notes: Formatting, section organization, keyword density tips
- red_flags: Date gaps, vague claims, inconsistencies (empty if none)
- next_steps: Prioritized actions (e.g., "1. Add certifications section")
- evidence: Link 3-5 key claims to direct CV quotes to reduce hallucination
- confidence: low = poor CV quality, medium = good analysis, high = excellent match

CV TEXT:
{cv_text}

JOB DESCRIPTION:
{job_text}

Return only the JSON object, no additional text.
""".strip()


class AnalysisService:
    """Service for analyzing CVs against job descriptions using LLM.

    Orchestrates the full analysis pipeline: validation, prompt construction,
    LLM invocation with schema enforcement, caching, and response validation.

    Attributes:
        llm: LLM client adapter for generating structured JSON.
        cache: TTL cache for storing analysis results by content hash.
    """

    def __init__(self, llm: AbstractLLMClient, cache: SimpleTTLCache) -> None:
        """Initialize analysis service with dependencies.

        Args:
            llm: Configured LLM client instance.
            cache: Cache instance for storing results.
        """
        self.llm = llm
        self.cache = cache

    def _validate_inputs(self, cv_text: str, job_text: str) -> None:
        """Validate that inputs meet minimum requirements.

        Args:
            cv_text: CV text to validate.
            job_text: Job description text to validate.

        Raises:
            ValidationAppError: If inputs are too short or empty.
        """
        if not cv_text or len(cv_text.strip()) < settings.app.min_cv_chars:
            raise ValidationAppError(
                code="cv_text_too_short",
                message="CV text is too short. PDF may be image-based (OCR not supported in MVP).",
                details={
                    "min_chars": settings.app.min_cv_chars,
                    "actual": len(cv_text.strip()) if cv_text else 0,
                },
            )

        if not job_text or len(job_text.strip()) < 50:
            raise ValidationAppError(
                code="job_text_too_short",
                message="Job description is too short (minimum 50 characters).",
                details={"actual": len(job_text.strip()) if job_text else 0},
            )

    def _prepare_inputs(
        self,
        cv_text: str,
        job_text: str,
        warnings: list[str],
    ) -> tuple[str, str]:
        """Prepare inputs by truncating to model limits.

        Args:
            cv_text: Raw CV text.
            job_text: Raw job description text.
            warnings: List to append truncation warnings to.

        Returns:
            Tuple of (truncated_cv_text, truncated_job_text).
        """
        cv_text, cv_truncated = _truncate(cv_text, settings.app.max_cv_chars)
        job_text, job_truncated = _truncate(job_text, settings.app.max_job_desc_chars)

        if cv_truncated or job_truncated:
            warnings.append("Input was truncated to fit model limits.")

        return cv_text, job_text

    def _get_from_cache(self, cache_key: str) -> CVAnalysisResponse | None:
        """Retrieve analysis from cache if available.

        Args:
            cache_key: Hash key for cache lookup.

        Returns:
            Cached CVAnalysisResponse with cached=True, or None if not found.
        """
        cached_result = self.cache.get(cache_key)

        if not cached_result:
            return None

        # Handle both dict and CVAnalysisResponse instances
        if isinstance(cached_result, dict):
            return CVAnalysisResponse.model_validate({**cached_result, "cached": True})

        cached_dict = cached_result.model_dump()
        cached_dict["cached"] = True
        return CVAnalysisResponse.model_validate(cached_dict)

    async def _generate_analysis(
        self,
        cv_text: str,
        job_text: str,
        warnings: list[str],
    ) -> CVAnalysisResponse:
        """Generate fresh analysis using LLM.

        Args:
            cv_text: Prepared CV text.
            job_text: Prepared job description text.
            warnings: Accumulated warnings to include in response.

        Returns:
            Validated CVAnalysisResponse from LLM.

        Raises:
            LLMAppError: If LLM call fails or returns invalid JSON.
        """
        prompt = build_prompt(cv_text, job_text)
        schema: dict[str, Any] = CVAnalysisResponse.model_json_schema()

        raw_response = await self.llm.generate_json(prompt, schema=schema)

        return CVAnalysisResponse.model_validate({
            **raw_response,
            "warnings": warnings,
            "cached": False,
        })

    async def analyze(
        self,
        cv_text: str,
        job_text: str,
        warnings: list[str] | None = None,
    ) -> CVAnalysisResponse:
        """Analyze CV against job description and return structured insights.

        High-level orchestrator that coordinates validation, caching, and LLM calls.

        Args:
            cv_text: Normalized CV text content.
            job_text: Job description text.
            warnings: Optional list of warnings from parsing/extraction stage.

        Returns:
            Validated CVAnalysisResponse with analysis results.

        Raises:
            ValidationAppError: If inputs are too short or invalid.
            LLMAppError: If LLM call fails or returns invalid JSON.
        """
        warnings = warnings or []

        # Step 1: Validate inputs
        self._validate_inputs(cv_text, job_text)

        # Step 2: Prepare inputs (truncate if needed)
        cv_text, job_text = self._prepare_inputs(cv_text, job_text, warnings)

        # Step 3: Check cache
        cache_key = _hash_inputs(cv_text, job_text)
        cached_analysis = self._get_from_cache(cache_key)

        if cached_analysis:
            return cached_analysis

        # Step 4: Generate fresh analysis via LLM
        analysis = await self._generate_analysis(cv_text, job_text, warnings)

        # Step 5: Cache the result
        self.cache.set(cache_key, analysis.model_dump())

        return analysis
