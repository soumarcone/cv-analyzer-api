"""Unit tests for job description semantic content validation."""

import pytest
from unittest.mock import AsyncMock, patch
from app.services.analysis_service import AnalysisService
from app.core.errors import ValidationAppError
from app.adapters.llm.base import AbstractLLMClient
from app.utils.simple_cache import SimpleTTLCache


class TestJobSemanticValidation:
    """Test LLM-based semantic validation of job description content."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""
        return AsyncMock(spec=AbstractLLMClient)

    @pytest.fixture
    def mock_cache(self):
        """Create mock cache."""
        return SimpleTTLCache(ttl_seconds=3600, max_entries=10)

    @pytest.fixture
    def service(self, mock_llm, mock_cache):
        """Create analysis service with mocked dependencies."""
        return AnalysisService(mock_llm, mock_cache)

    @pytest.mark.asyncio
    async def test_validate_job_valid_content(self, service, mock_llm):
        """Valid job description should pass validation."""
        job_text = """
        Senior Backend Engineer - Remote
        
        About the Role:
        We're seeking an experienced Backend Engineer to join our growing team.
        
        Responsibilities:
        - Design and develop scalable REST APIs using Python and FastAPI
        - Collaborate with frontend team on API specifications
        - Implement database schemas and optimize queries
        - Write comprehensive tests and documentation
        
        Requirements:
        - 5+ years of Python development experience
        - Strong knowledge of FastAPI, PostgreSQL, and AWS
        - Experience with Docker and CI/CD pipelines
        - Excellent problem-solving skills
        
        Benefits:
        - Competitive salary ($120k-$160k)
        - Remote-first culture
        - Health insurance and 401k matching
        """

        mock_llm.generate_json.return_value = {
            "is_valid_job": True,
            "confidence": 0.98,
            "reason": "Contains clear responsibilities, requirements, and role details",
            "detected_elements": ["responsibilities", "requirements", "role information", "company benefits"],
        }

        # Should not raise any exception
        await service._validate_job_semantic_content(job_text)
        mock_llm.generate_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_job_invalid_lorem_ipsum(self, service, mock_llm):
        """Lorem ipsum text should fail validation."""
        job_text = """
        Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
        Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
        Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
        """

        mock_llm.generate_json.return_value = {
            "is_valid_job": False,
            "confidence": 0.99,
            "reason": "Text is generic filler with no job-related content",
            "detected_elements": [],
        }

        with pytest.raises(ValidationAppError) as exc_info:
            await service._validate_job_semantic_content(job_text)

        assert exc_info.value.code == "invalid_job_content"
        assert "doesn't appear to be a valid job description" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_validate_job_invalid_random_text(self, service, mock_llm):
        """Random non-job text should fail validation."""
        job_text = """
        This is a story about a cat named Whiskers.
        He liked to climb trees and chase mice.
        One day he found a hidden treasure in the garden.
        """

        mock_llm.generate_json.return_value = {
            "is_valid_job": False,
            "confidence": 0.95,
            "reason": "Text is a narrative story, not a job posting",
            "detected_elements": [],
        }

        with pytest.raises(ValidationAppError) as exc_info:
            await service._validate_job_semantic_content(job_text)

        assert exc_info.value.code == "invalid_job_content"

    @pytest.mark.asyncio
    async def test_validate_job_rejects_malicious_code(self, service, mock_llm):
        """Job description with executable code should fail validation."""
        job_text = """
        Senior Engineer Position
        
        Requirements: Python, SQL
        
        # Malicious payload
        import os
        os.system('rm -rf /')
        
        SELECT * FROM users WHERE '1'='1'; DROP TABLE users;--
        """

        mock_llm.generate_json.return_value = {
            "is_valid_job": False,
            "confidence": 0.97,
            "reason": "Text contains executable code and potential SQL injection attempts",
            "detected_elements": [],
        }

        with pytest.raises(ValidationAppError) as exc_info:
            await service._validate_job_semantic_content(job_text)

        assert exc_info.value.code == "invalid_job_content"
        assert "doesn't appear to be a valid job description" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_validate_job_accepts_legitimate_urls(self, service, mock_llm):
        """Job description with legitimate URLs (LinkedIn, company sites) should pass."""
        job_text = """
        Senior Backend Engineer
        
        About Us:
        Learn more: https://www.linkedin.com/company/techcorp
        Careers: https://techcorp.com/careers
        
        Responsibilities:
        - Build scalable APIs
        - Collaborate with team
        
        Requirements:
        - 5+ years Python experience
        - Strong problem-solving skills
        """

        mock_llm.generate_json.return_value = {
            "is_valid_job": True,
            "confidence": 0.92,
            "reason": "Valid job description with legitimate company URLs",
            "detected_elements": ["responsibilities", "requirements", "company info"],
        }

        # Should not raise - legitimate URLs are acceptable
        await service._validate_job_semantic_content(job_text)
        mock_llm.generate_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_job_low_confidence_fails(self, service, mock_llm):
        """Valid job detected but with low confidence should fail."""
        job_text = "Looking for someone to help with work stuff"

        mock_llm.generate_json.return_value = {
            "is_valid_job": True,
            "confidence": 0.55,  # Below 0.7 threshold
            "reason": "Vague job reference but lacks structure",
            "detected_elements": ["vague role mention"],
        }

        with pytest.raises(ValidationAppError) as exc_info:
            await service._validate_job_semantic_content(job_text)

        assert exc_info.value.code == "invalid_job_content"

    @pytest.mark.asyncio
    async def test_validate_job_disabled_skips_validation(self, service, mock_llm):
        """When semantic validation disabled, should skip LLM call."""
        job_text = "Lorem ipsum dolor sit amet"

        with patch("app.services.analysis_service.settings") as mock_settings:
            mock_settings.app.enable_semantic_validation = False
            
            await service._validate_job_semantic_content(job_text)
            
            # Should not call LLM at all
            mock_llm.generate_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_job_llm_error_fails_open(self, service, mock_llm):
        """LLM errors during validation should log but not block."""
        job_text = "Some job description content"

        # Mock LLM to raise an exception
        mock_llm.generate_json.side_effect = RuntimeError("LLM service error")

        # Should not raise ValidationAppError - fails open
        with patch("app.services.analysis_service.logger") as mock_logger:
            await service._validate_job_semantic_content(job_text)
            
            # Should log warning
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_validate_job_uses_first_2000_chars(self, service, mock_llm):
        """Validation should only use first 2000 characters of job description."""
        long_job = "Senior Engineer\nRequirements: Python, FastAPI\n" + ("x" * 3000)

        mock_llm.generate_json.return_value = {
            "is_valid_job": True,
            "confidence": 0.88,
            "reason": "Valid job description",
            "detected_elements": ["requirements", "role title"],
        }

        await service._validate_job_semantic_content(long_job)

        # Verify that only first 2000 chars were used
        call_args = mock_llm.generate_json.call_args
        prompt = call_args[0][0]  # First positional argument is the prompt
        
        # The prompt should contain truncated text
        assert len(prompt) < len(long_job)

    @pytest.mark.asyncio
    async def test_validate_job_incomplete_response_fails_open(self, service, mock_llm):
        """Incomplete LLM response should fail open."""
        job_text = "Valid job description"

        # Mock incomplete response (missing required fields)
        mock_llm.generate_json.return_value = {
            "is_valid_job": True,
            # Missing confidence and reason
        }

        # Should not raise - fails open
        with patch("app.services.analysis_service.logger") as mock_logger:
            await service._validate_job_semantic_content(job_text)
            
            # Should log incomplete response warning
            assert any(
                "job_validation_incomplete" in str(call)
                for call in mock_logger.warning.call_args_list
            )

    @pytest.mark.asyncio
    async def test_validate_job_unexpected_types_fails_open(self, service, mock_llm):
        """Unexpected field types in LLM response should fail open."""
        job_text = "Valid job description"

        # Mock response with wrong types
        mock_llm.generate_json.return_value = {
            "is_valid_job": "yes",  # Should be boolean
            "confidence": "high",   # Should be float
            "reason": "Valid",
        }

        # Should not raise - fails open
        with patch("app.services.analysis_service.logger") as mock_logger:
            await service._validate_job_semantic_content(job_text)
            
            # Should log type mismatch warning
            assert any(
                "job_validation_unexpected_types" in str(call)
                for call in mock_logger.warning.call_args_list
            )
