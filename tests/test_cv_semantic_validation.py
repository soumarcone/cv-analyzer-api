"""Unit tests for CV semantic content validation."""

import pytest
from unittest.mock import AsyncMock, patch
from app.services.analysis_service import AnalysisService
from app.core.errors import ValidationAppError
from app.adapters.llm.base import AbstractLLMClient
from app.utils.simple_cache import SimpleTTLCache


class TestCVSemanticValidation:
    """Test LLM-based semantic validation of CV content."""

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
    async def test_validate_cv_valid_content(self, service, mock_llm):
        """Valid CV content should pass validation."""
        cv_text = """
        John Doe
        john@example.com | (555) 123-4567

        PROFESSIONAL EXPERIENCE
        Senior Software Engineer at TechCorp (2020-2024)
        - Built REST APIs using FastAPI and Python
        - Led team of 5 developers
        - Improved system performance by 40%

        EDUCATION
        BS Computer Science, University of State (2018)

        SKILLS
        Python, FastAPI, PostgreSQL, AWS, Docker, Git
        """

        mock_llm.generate_json.return_value = {
            "is_valid_cv": True,
            "confidence": 0.95,
            "reason": "Contains professional experience, education, skills, and contact info",
            "detected_elements": ["professional experience", "education", "skills", "contact info"],
        }

        # Should not raise any exception
        await service._validate_cv_semantic_content(cv_text)
        mock_llm.generate_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_cv_invalid_lorem_ipsum(self, service, mock_llm):
        """Lorem ipsum text should fail validation."""
        cv_text = """
        Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
        Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
        Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
        """

        mock_llm.generate_json.return_value = {
            "is_valid_cv": False,
            "confidence": 0.98,
            "reason": "Text is generic filler with no professional content",
            "detected_elements": [],
        }

        with pytest.raises(ValidationAppError) as exc_info:
            await service._validate_cv_semantic_content(cv_text)

        assert exc_info.value.code == "invalid_cv_content"
        assert "doesn't appear to be a valid CV" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_validate_cv_invalid_code_snippet(self, service, mock_llm):
        """Code source should fail validation."""
        cv_text = """
        def fibonacci(n):
            if n <= 1:
                return n
            return fibonacci(n-1) + fibonacci(n-2)

        class DataProcessor:
            def __init__(self, data):
                self.data = data
            
            def process(self):
                return [x * 2 for x in self.data]
        """

        mock_llm.generate_json.return_value = {
            "is_valid_cv": False,
            "confidence": 0.92,
            "reason": "Text contains only code snippets, not professional experience",
            "detected_elements": [],
        }

        with pytest.raises(ValidationAppError) as exc_info:
            await service._validate_cv_semantic_content(cv_text)

        assert exc_info.value.code == "invalid_cv_content"

    @pytest.mark.asyncio
    async def test_validate_cv_low_confidence_fails(self, service, mock_llm):
        """Valid CV detected but with low confidence should fail."""
        cv_text = "Some content about work and education"

        mock_llm.generate_json.return_value = {
            "is_valid_cv": True,
            "confidence": 0.65,  # Below 0.7 threshold
            "reason": "Content might be CV but uncertain",
            "detected_elements": ["work experience"],
        }

        with pytest.raises(ValidationAppError) as exc_info:
            await service._validate_cv_semantic_content(cv_text)

        assert exc_info.value.code == "invalid_cv_content"

    @pytest.mark.asyncio
    async def test_validate_cv_disabled_skips_validation(self, service, mock_llm):
        """When semantic validation disabled, should skip LLM call."""
        cv_text = "Lorem ipsum dolor sit amet"

        with patch("app.services.analysis_service.settings") as mock_settings:
            mock_settings.app.enable_semantic_validation = False
            
            await service._validate_cv_semantic_content(cv_text)
            
            # Should not call LLM at all
            mock_llm.generate_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_cv_llm_error_fails_open(self, service, mock_llm):
        """LLM errors during validation should log but not block."""
        cv_text = "Some CV content"

        # Mock LLM to raise an exception
        mock_llm.generate_json.side_effect = RuntimeError("LLM service error")

        # Should not raise ValidationAppError - fails open
        with patch("app.services.analysis_service.logger") as mock_logger:
            await service._validate_cv_semantic_content(cv_text)
            
            # Should log warning
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_validate_cv_uses_first_2000_chars(self, service, mock_llm):
        """Validation should only use first 2000 characters of CV."""
        long_cv = "John Doe\nEmail: john@example.com\n" + ("x" * 3000)

        mock_llm.generate_json.return_value = {
            "is_valid_cv": True,
            "confidence": 0.85,
            "reason": "Valid CV",
            "detected_elements": ["contact info"],
        }

        await service._validate_cv_semantic_content(long_cv)

        # Verify that only first 2000 chars were used
        call_args = mock_llm.generate_json.call_args
        prompt = call_args[0][0]  # First positional argument is the prompt
        
        # The prompt should contain truncated text
        assert len(prompt) < len(long_cv)
