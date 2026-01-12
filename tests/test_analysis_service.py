"""Unit tests for AnalysisService."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set required env vars before importing settings
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o")
os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.errors import ValidationAppError
from app.schemas.analysis import CVAnalysisResponse
from app.services.analysis_service import (
    AnalysisService,
    _hash_inputs,
    _truncate,
    build_prompt,
)
from app.utils.simple_cache import SimpleTTLCache


class TestHelperFunctions:
    """Test module-level helper functions."""

    def test_truncate_no_truncation_needed(self) -> None:
        """Test that text shorter than limit is returned unchanged."""
        text = "Short text"
        result, was_truncated = _truncate(text, max_chars=100)

        assert result == text
        assert was_truncated is False

    def test_truncate_exact_limit(self) -> None:
        """Test that text exactly at limit is not truncated."""
        text = "X" * 100
        result, was_truncated = _truncate(text, max_chars=100)

        assert result == text
        assert was_truncated is False

    def test_truncate_exceeds_limit(self) -> None:
        """Test that text exceeding limit is truncated."""
        text = "X" * 150
        result, was_truncated = _truncate(text, max_chars=100)

        assert len(result) == 100
        assert result == "X" * 100
        assert was_truncated is True

    def test_hash_inputs_deterministic(self) -> None:
        """Test that same inputs produce same hash."""
        cv = "Sample CV content"
        job = "Sample job description"

        hash1 = _hash_inputs(cv, job)
        hash2 = _hash_inputs(cv, job)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_hash_inputs_different_for_different_content(self) -> None:
        """Test that different inputs produce different hashes."""
        hash1 = _hash_inputs("CV 1", "Job 1")
        hash2 = _hash_inputs("CV 2", "Job 2")

        assert hash1 != hash2

    def test_build_prompt_includes_cv_and_job(self) -> None:
        """Test that prompt includes both CV and job description."""
        cv_text = "Python developer with 5 years experience"
        job_text = "Looking for senior Python developer"

        prompt = build_prompt(cv_text, job_text)

        assert cv_text in prompt
        assert job_text in prompt
        assert "fit_score" in prompt
        assert "evidence" in prompt
        assert "JSON" in prompt


class TestAnalysisServiceValidation:
    """Test input validation methods."""

    def test_validate_inputs_valid(self) -> None:
        """Test that valid inputs pass validation."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 600  # Above MIN_CV_CHARS (500)
        job_text = "Y" * 100  # Above minimum (50)

        # Should not raise
        service._validate_inputs(cv_text, job_text)

    def test_validate_inputs_cv_too_short(self) -> None:
        """Test that short CV raises ValidationAppError."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 100  # Below MIN_CV_CHARS (500)
        job_text = "Y" * 100

        with pytest.raises(ValidationAppError) as exc_info:
            service._validate_inputs(cv_text, job_text)

        assert exc_info.value.code == "cv_text_too_short"
        assert "image-based" in exc_info.value.message

    def test_validate_inputs_cv_empty(self) -> None:
        """Test that empty CV raises ValidationAppError."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        with pytest.raises(ValidationAppError) as exc_info:
            service._validate_inputs("", "Valid job description")

        assert exc_info.value.code == "cv_text_too_short"

    def test_validate_inputs_job_too_short(self) -> None:
        """Test that short job description raises ValidationAppError."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 600
        job_text = "Short"  # Below minimum (50)

        with pytest.raises(ValidationAppError) as exc_info:
            service._validate_inputs(cv_text, job_text)

        assert exc_info.value.code == "job_text_too_short"
        assert "50 characters" in exc_info.value.message

    def test_validate_inputs_job_empty(self) -> None:
        """Test that empty job description raises ValidationAppError."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 600

        with pytest.raises(ValidationAppError) as exc_info:
            service._validate_inputs(cv_text, "")

        assert exc_info.value.code == "job_text_too_short"


class TestAnalysisServicePrepareInputs:
    """Test input preparation and truncation."""

    def test_prepare_inputs_no_truncation(self) -> None:
        """Test that inputs under limit are not truncated."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 1000
        job_text = "Y" * 500
        warnings: list[str] = []

        result_cv, result_job = service._prepare_inputs(cv_text, job_text, warnings)

        assert result_cv == cv_text
        assert result_job == job_text
        assert len(warnings) == 0

    def test_prepare_inputs_cv_truncated(self) -> None:
        """Test that CV exceeding limit is truncated with warning."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 60000  # Exceeds default max_cv_chars (50000)
        job_text = "Y" * 500
        warnings: list[str] = []

        result_cv, result_job = service._prepare_inputs(cv_text, job_text, warnings)

        assert len(result_cv) == 50000
        assert result_job == job_text
        assert "truncated" in warnings[0]

    def test_prepare_inputs_job_truncated(self) -> None:
        """Test that job description exceeding limit is truncated with warning."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 1000
        job_text = "Y" * 15000  # Exceeds default max_job_desc_chars (10000)
        warnings: list[str] = []

        result_cv, result_job = service._prepare_inputs(cv_text, job_text, warnings)

        assert result_cv == cv_text
        assert len(result_job) == 10000
        assert len(warnings) == 1
        assert "truncated" in warnings[0]

    def test_prepare_inputs_both_truncated(self) -> None:
        """Test that both inputs can be truncated with single warning."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 60000
        job_text = "Y" * 15000
        warnings: list[str] = []

        result_cv, result_job = service._prepare_inputs(cv_text, job_text, warnings)

        assert len(result_cv) == 50000
        assert len(result_job) == 10000
        assert len(warnings) == 1


class TestAnalysisServiceCache:
    """Test cache retrieval logic."""

    def test_get_from_cache_miss(self) -> None:
        """Test that cache miss returns None."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        service = AnalysisService(llm=mock_llm, cache=mock_cache)
        result = service._get_from_cache("test_key")

        assert result is None
        mock_cache.get.assert_called_once_with("test_key")

    def test_get_from_cache_hit_with_dict(self) -> None:
        """Test that cache hit with dict returns CVAnalysisResponse."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()

        cached_dict = {
            "summary": "Good fit",
            "fit_score": 75,
            "fit_score_rationale": "Strong match",
            "strengths": ["Python", "FastAPI"],
            "gaps": ["Cloud experience"],
            "missing_keywords": ["AWS"],
            "rewrite_suggestions": ["Add metrics"],
            "ats_notes": ["Use bullet points"],
            "red_flags": [],
            "next_steps": ["Apply now"],
            "evidence": [],
            "confidence": "medium",
            "warnings": [],
            "cached": False,
        }
        mock_cache.get.return_value = cached_dict

        service = AnalysisService(llm=mock_llm, cache=mock_cache)
        result = service._get_from_cache("test_key")

        assert isinstance(result, CVAnalysisResponse)
        assert result.cached is True
        assert result.summary == "Good fit"
        assert result.fit_score == 75

    def test_get_from_cache_hit_with_response_instance(self) -> None:
        """Test that cache hit with CVAnalysisResponse returns marked as cached."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()

        cached_response = CVAnalysisResponse(
            summary="Good fit",
            fit_score=75,
            fit_score_rationale="Strong match",
            strengths=["Python"],
            gaps=["Cloud"],
            missing_keywords=["AWS"],
            rewrite_suggestions=["Add metrics"],
            ats_notes=["Use bullets"],
            red_flags=[],
            next_steps=["Apply"],
            cached=False,
        )
        mock_cache.get.return_value = cached_response

        service = AnalysisService(llm=mock_llm, cache=mock_cache)
        result = service._get_from_cache("test_key")

        assert isinstance(result, CVAnalysisResponse)
        assert result.cached is True


class TestAnalysisServiceGeneration:
    """Test LLM analysis generation."""

    @pytest.mark.asyncio
    async def test_generate_analysis_success(self) -> None:
        """Test successful analysis generation from LLM."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()

        # Mock LLM response
        llm_response = {
            "summary": "Strong Python developer",
            "fit_score": 85,
            "fit_score_rationale": "Excellent match for backend role",
            "strengths": ["Python", "FastAPI", "PostgreSQL"],
            "gaps": ["Kubernetes experience"],
            "missing_keywords": ["K8s", "Docker"],
            "rewrite_suggestions": ["Add containerization projects"],
            "ats_notes": ["Include keywords in skills section"],
            "red_flags": [],
            "next_steps": ["Highlight cloud projects"],
            "evidence": [
                {"claim": "Has FastAPI experience", "cv_quote": "Built APIs with FastAPI"}
            ],
            "confidence": "high",
        }

        mock_llm.generate_json = AsyncMock(return_value=llm_response)

        service = AnalysisService(llm=mock_llm, cache=mock_cache)
        warnings = ["Test warning"]

        result = await service._generate_analysis(
            cv_text="Sample CV",
            job_text="Sample job",
            warnings=warnings,
        )

        assert isinstance(result, CVAnalysisResponse)
        assert result.cached is False
        assert result.fit_score == 85
        assert "Test warning" in result.warnings
        assert len(result.evidence) == 1

        # Verify LLM was called with schema
        mock_llm.generate_json.assert_called_once()
        call_args = mock_llm.generate_json.call_args
        assert "schema" in call_args.kwargs
        assert call_args.kwargs["schema"] is not None


class TestAnalysisServiceIntegration:
    """Integration tests for the full analyze workflow."""

    @pytest.mark.asyncio
    async def test_analyze_cache_hit(self) -> None:
        """Test that cached results are returned without calling LLM."""
        mock_llm = MagicMock()
        mock_cache = SimpleTTLCache(ttl_seconds=3600)

        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 600
        job_text = "Y" * 100

        # Pre-populate cache
        cached_response = {
            "summary": "Cached result",
            "fit_score": 90,
            "fit_score_rationale": "From cache",
            "strengths": ["Cached"],
            "gaps": [],
            "missing_keywords": [],
            "rewrite_suggestions": [],
            "ats_notes": [],
            "red_flags": [],
            "next_steps": [],
            "evidence": [],
            "confidence": "high",
            "warnings": [],
            "cached": False,
        }

        cache_key = _hash_inputs(cv_text, job_text)
        mock_cache.set(cache_key, cached_response)

        # Call analyze
        result = await service.analyze(cv_text, job_text)

        assert result.cached is True
        assert result.summary == "Cached result"
        # LLM should not be called
        assert not hasattr(mock_llm, "generate_json") or not mock_llm.generate_json.called

    @pytest.mark.asyncio
    async def test_analyze_cache_miss_generates_fresh(self) -> None:
        """Test that cache miss triggers fresh LLM generation."""
        mock_llm = MagicMock()
        mock_cache = SimpleTTLCache(ttl_seconds=3600)

        llm_response = {
            "summary": "Fresh analysis",
            "fit_score": 70,
            "fit_score_rationale": "Newly generated",
            "strengths": ["Python"],
            "gaps": ["DevOps"],
            "missing_keywords": ["CI/CD"],
            "rewrite_suggestions": ["Add pipeline experience"],
            "ats_notes": ["Format improvements"],
            "red_flags": [],
            "next_steps": ["Update resume"],
            "evidence": [],
            "confidence": "medium",
        }
        mock_llm.generate_json = AsyncMock(return_value=llm_response)

        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 600
        job_text = "Y" * 100

        result = await service.analyze(cv_text, job_text)

        assert result.cached is False
        assert result.summary == "Fresh analysis"
        assert result.fit_score == 70

        # Verify LLM was called
        mock_llm.generate_json.assert_called_once()

        # Verify result was cached
        cache_key = _hash_inputs(cv_text, job_text)
        cached = mock_cache.get(cache_key)
        assert cached is not None

    @pytest.mark.asyncio
    async def test_analyze_with_warnings_propagation(self) -> None:
        """Test that warnings from parsing are propagated to final result."""
        mock_llm = MagicMock()
        mock_cache = SimpleTTLCache(ttl_seconds=3600)

        llm_response = {
            "summary": "Test",
            "fit_score": 50,
            "fit_score_rationale": "Test",
            "strengths": [],
            "gaps": [],
            "missing_keywords": [],
            "rewrite_suggestions": [],
            "ats_notes": [],
            "red_flags": [],
            "next_steps": [],
            "evidence": [],
            "confidence": "low",
        }
        mock_llm.generate_json = AsyncMock(return_value=llm_response)

        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 600
        job_text = "Y" * 100
        initial_warnings = ["PDF extraction warning", "Low quality scan"]

        result = await service.analyze(cv_text, job_text, warnings=initial_warnings)

        assert "PDF extraction warning" in result.warnings
        assert "Low quality scan" in result.warnings

    @pytest.mark.asyncio
    async def test_analyze_adds_truncation_warning(self) -> None:
        """Test that truncation adds warning to result."""
        mock_llm = MagicMock()
        mock_cache = SimpleTTLCache(ttl_seconds=3600)

        llm_response = {
            "summary": "Test",
            "fit_score": 50,
            "fit_score_rationale": "Test",
            "strengths": [],
            "gaps": [],
            "missing_keywords": [],
            "rewrite_suggestions": [],
            "ats_notes": [],
            "red_flags": [],
            "next_steps": [],
            "evidence": [],
            "confidence": "low",
        }
        mock_llm.generate_json = AsyncMock(return_value=llm_response)

        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 60000  # Will be truncated
        job_text = "Y" * 100

        result = await service.analyze(cv_text, job_text)

        assert any("truncated" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_analyze_validation_failure_cv(self) -> None:
        """Test that analyze fails fast on invalid CV."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()

        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        with pytest.raises(ValidationAppError) as exc_info:
            await service.analyze(cv_text="Too short", job_text="Valid job description")

        assert exc_info.value.code == "cv_text_too_short"

    @pytest.mark.asyncio
    async def test_analyze_validation_failure_job(self) -> None:
        """Test that analyze fails fast on invalid job description."""
        mock_llm = MagicMock()
        mock_cache = MagicMock()

        service = AnalysisService(llm=mock_llm, cache=mock_cache)

        cv_text = "X" * 600

        with pytest.raises(ValidationAppError) as exc_info:
            await service.analyze(cv_text=cv_text, job_text="Bad")

        assert exc_info.value.code == "job_text_too_short"
