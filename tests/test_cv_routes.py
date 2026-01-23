"""Tests for CV analysis API routes.

This module tests the FastAPI endpoints for CV parsing and analysis,
including request validation, error handling, and integration with
service layer and LLM client.

IMPORTANT: API Key Authentication
- All /v1/cv/* endpoints require X-API-Key header
- Use valid_api_key_headers fixture in tests
- Some legacy tests may need updating to include authentication headers

Configuration:
- Environment variables are loaded from .env.testing via conftest.py
- conftest.py sets APP_ENV=testing before any app imports
- No need to manually set environment variables in this file
"""

import io
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings

from app.main import app
from app.core.errors import ValidationAppError, LLMAppError
from app.schemas.analysis import CVAnalysisResponse


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def valid_api_key_headers() -> dict[str, str]:
    """Create valid API key headers for authenticated requests."""
    return {"X-API-Key": "test-api-key-123"}


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Create minimal valid PDF bytes for testing."""
    # Minimal PDF structure with text content
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Senior Python Developer with 10 years experience) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000214 00000 n
0000000303 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
378
%%EOF
"""
    return pdf_content


@pytest.fixture
def sample_docx_bytes() -> bytes:
    """Create minimal valid DOCX bytes for testing.
    
    A DOCX file is a ZIP archive containing XML files.
    This creates a minimal but valid structure.
    """
    import zipfile
    
    docx_buffer = io.BytesIO()
    with zipfile.ZipFile(docx_buffer, "w", zipfile.ZIP_DEFLATED) as docx:
        # Minimal _rels/.rels
        docx.writestr(
            "_rels/.rels",
            b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        # Minimal word/document.xml with content
        docx.writestr(
            "word/document.xml",
            b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r>
                <w:t>Senior Python Developer with 10 years experience in FastAPI and Django</w:t>
            </w:r>
        </w:p>
        <w:p>
            <w:r>
                <w:t>Skills: Python, FastAPI, PostgreSQL, Docker, AWS</w:t>
            </w:r>
        </w:p>
    </w:body>
</w:document>""",
        )
        # [Content_Types].xml
        docx.writestr(
            "[Content_Types].xml",
            b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
    
    return docx_buffer.getvalue()


@pytest.fixture
def sample_cv_analysis_response() -> dict:
    """Create a sample CV analysis response for mocking."""
    return {
        "summary": "Strong match for senior Python developer role.",
        "fit_score": 85,
        "fit_score_rationale": "Candidate has 10 years Python experience with FastAPI expertise matching job requirements.",
        "strengths": [
            "10 years Python development experience",
            "Expertise in FastAPI and async programming",
            "Strong database design skills (PostgreSQL)",
            "Docker and containerization experience",
        ],
        "gaps": [
            "Limited Kubernetes experience",
            "No mention of GraphQL in CV",
        ],
        "missing_keywords": [
            "Kubernetes",
            "GraphQL",
            "CI/CD",
        ],
        "rewrite_suggestions": [
            "Add metrics and impact to FastAPI project (e.g., 'Reduced API latency by 40%')",
            "Highlight any DevOps/Kubernetes projects or certifications",
            "Include specific tools used in CI/CD pipelines",
        ],
        "ats_notes": [
            "Ensure job title matches keywords from description",
            "Use consistent formatting for dates and locations",
            "Add a skills section with searchable keywords",
        ],
        "red_flags": [],
        "next_steps": [
            "Add quantified metrics to projects",
            "Highlight Kubernetes or related orchestration experience",
            "Include CI/CD tools and practices",
        ],
        "evidence": [
            {
                "claim": "10 years Python development experience",
                "cv_quote": "Senior Python Developer with 10 years experience",
            },
            {
                "claim": "FastAPI expertise",
                "cv_quote": "10 years experience in FastAPI and Django",
            },
        ],
        "confidence": "high",
        "warnings": [],
        "cached": False,
    }


# ======================== Health Check Tests ========================


class TestHealthCheck:
    """Test the health check endpoint."""

    def test_health_check_returns_ok(self, client: TestClient) -> None:
        """Test that health check endpoint returns 200 with status ok."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ======================== Authentication Tests ========================


class TestAPIKeyAuthentication:
    """Test API key authentication on protected endpoints."""

    def test_parse_cv_without_api_key_returns_403(
        self, client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Test that requests without API key are rejected."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        
        response = client.post("/v1/cv/parse", files=files)
        
        assert response.status_code == 403
        assert "Missing API key" in response.json()["detail"]

    def test_parse_cv_with_invalid_api_key_returns_403(
        self, client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Test that requests with invalid API key are rejected."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        headers = {"X-API-Key": "invalid-key-999"}
        
        response = client.post("/v1/cv/parse", files=files, headers=headers)
        
        assert response.status_code == 403
        assert "Invalid" in response.json()["detail"]

    def test_parse_cv_with_valid_api_key_succeeds(
        self, client: TestClient, sample_pdf_bytes: bytes, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test that requests with valid API key are accepted."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        
        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)
        
        assert response.status_code == 200

    def test_analyze_cv_without_api_key_returns_403(
        self, client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Test that analyze endpoint rejects requests without API key."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data)
        
        assert response.status_code == 403
        assert "Missing API key" in response.json()["detail"]


# ======================== Rate Limit Tests ========================


class TestRateLimiting:
    """Test rate limiting on protected endpoints."""

    def test_rate_limit_blocks_after_n_requests(
        self,
        client: TestClient,
        sample_pdf_bytes: bytes,
        valid_api_key_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Blocks with 429 when the global per-key limit is exceeded."""
        from app.adapters.rate_limit.in_memory import InMemoryFixedWindowRateLimiter
        from app.core import rate_limit as rate_limit_module

        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_enabled", True)
        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_include_headers", True)
        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_requests", 2)
        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_window_seconds", 60)

        limiter = InMemoryFixedWindowRateLimiter(limit=2, window_seconds=60, clock=lambda: 1000.0)
        monkeypatch.setattr(rate_limit_module, "get_rate_limiter", lambda: limiter)

        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}

        assert client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers).status_code == 200
        assert client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers).status_code == 200

        blocked = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)
        assert blocked.status_code == 429
        assert "Rate limit exceeded" in blocked.json()["detail"]
        assert "Retry-After" in blocked.headers
        assert "X-RateLimit-Limit" in blocked.headers
        assert "X-RateLimit-Remaining" in blocked.headers
        assert "X-RateLimit-Reset" in blocked.headers

    def test_rate_limit_is_isolated_by_api_key(
        self,
        client: TestClient,
        sample_pdf_bytes: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each API key has an independent quota."""
        from app.adapters.rate_limit.in_memory import InMemoryFixedWindowRateLimiter
        from app.core import rate_limit as rate_limit_module

        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_enabled", True)
        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_include_headers", False)
        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_requests", 1)
        monkeypatch.setattr(rate_limit_module.settings.app, "rate_limit_window_seconds", 60)

        limiter = InMemoryFixedWindowRateLimiter(limit=1, window_seconds=60, clock=lambda: 1000.0)
        monkeypatch.setattr(rate_limit_module, "get_rate_limiter", lambda: limiter)

        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}

        key1 = {"X-API-Key": "test-api-key-123"}
        key2 = {"X-API-Key": "test-api-key-456"}

        assert client.post("/v1/cv/parse", files=files, headers=key1).status_code == 200
        assert client.post("/v1/cv/parse", files=files, headers=key1).status_code == 429

        assert client.post("/v1/cv/parse", files=files, headers=key2).status_code == 200

    def test_analyze_cv_with_invalid_api_key_returns_403(
        self, client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Test that analyze endpoint rejects invalid API keys."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        headers = {"X-API-Key": "wrong-key"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=headers)
        
        assert response.status_code == 403

    def test_multiple_valid_api_keys_accepted(
        self, client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Test that all configured API keys work."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        
        # Test first key
        headers1 = {"X-API-Key": "test-api-key-123"}
        response1 = client.post("/v1/cv/parse", files=files, headers=headers1)
        assert response1.status_code == 200
        
        # Test second key
        headers2 = {"X-API-Key": "test-api-key-456"}
        response2 = client.post("/v1/cv/parse", files=files, headers=headers2)
        assert response2.status_code == 200


# ======================== CV Parse Endpoint Tests ========================


class TestParseCVEndpoint:
    """Test the /cv/parse endpoint.
    
    Note: All tests in this class require authentication via X-API-Key header.
    Tests use the valid_api_key_headers fixture to provide authentication.
    """

    def test_parse_cv_pdf_success(
        self, client: TestClient, sample_pdf_bytes: bytes, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test successful PDF parsing."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        
        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        assert result["file_name"] == "resume.pdf"
        assert result["file_type"] == "pdf"
        assert result["char_count"] > 0
        assert "text" in result
        assert "preview" in result
        assert "meta" in result
        assert isinstance(result["warnings"], list)

    def test_parse_cv_docx_success(
        self, client: TestClient, sample_docx_bytes: bytes, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test successful DOCX parsing."""
        files = {"cv_file": ("resume.docx", io.BytesIO(sample_docx_bytes), 
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        
        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        assert result["file_name"] == "resume.docx"
        assert result["file_type"] == "docx"
        assert result["char_count"] > 0
        assert "text" in result
        assert "meta" in result

    def test_parse_cv_file_too_large(
        self,
        client: TestClient,
        sample_pdf_bytes: bytes,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Reject files exceeding configured size limit with 413.
        
        Note: TestClient has limitations with chunked reading. Real HTTP
        validation is tested in test_file_size_integration.py.
        This test validates the error path when size check is triggered.
        """
        # Create file larger than limit (1MB in .env.testing)
        max_bytes = settings.app.max_upload_size_mb * 1024 * 1024
        oversized_pdf = sample_pdf_bytes + (b" " * (max_bytes + 1))
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(oversized_pdf), "application/pdf")}

        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)

        assert response.status_code == 413
        assert "File too large" in response.json()["detail"]

    def test_parse_cv_file_exactly_max_size(
        self,
        client: TestClient,
        sample_pdf_bytes: bytes,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Accept files exactly at the configured size limit."""
        # File exactly at limit should be accepted
        max_bytes = settings.app.max_upload_size_mb * 1024 * 1024
        sized_pdf = sample_pdf_bytes + (b" " * max(0, max_bytes - len(sample_pdf_bytes)))
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sized_pdf), "application/pdf")}

        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)

        assert response.status_code == 200

    def test_parse_cv_unsupported_file_type(self, client: TestClient, valid_api_key_headers: dict[str, str]) -> None:
        """Test that unsupported file types are rejected."""
        files = {"cv_file": ("resume.txt", io.BytesIO(b"Plain text"), "text/plain")}
        
        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)
        
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_parse_cv_empty_file(self, client: TestClient, valid_api_key_headers: dict[str, str]) -> None:
        """Test that empty files are rejected."""
        files = {"cv_file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
        
        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)
        
        assert response.status_code == 400
        assert "Empty file" in response.json()["detail"]

    def test_parse_cv_no_file_provided(self, client: TestClient, valid_api_key_headers: dict[str, str]) -> None:
        """Test that missing file raises validation error."""
        response = client.post("/v1/cv/parse", headers=valid_api_key_headers)
        
        assert response.status_code == 422  # FastAPI validation error

    def test_parse_cv_preview_truncation(
        self, client: TestClient, sample_pdf_bytes: bytes, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test that preview is truncated to configured limit."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        
        response = client.post("/v1/cv/parse", files=files, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        # Preview should be truncated (default 800 chars from config)
        assert len(result["preview"]) <= 800


# ======================== CV Analyze Endpoint Tests ========================


class TestAnalyzeCVEndpoint:
    """Test the /cv/analyze endpoint.
    
    Note: All tests in this class require authentication via X-API-Key header.
    Tests use the valid_api_key_headers fixture to provide authentication.
    """

    def test_analyze_cv_file_too_large(
        self,
        client: TestClient,
        sample_pdf_bytes: bytes,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Reject oversized files before analysis begins.
        
        Note: TestClient has limitations with chunked reading. Real HTTP
        validation is tested in test_file_size_integration.py.
        This test validates the error path when size check is triggered.
        """
        max_bytes = settings.app.max_upload_size_mb * 1024 * 1024
        oversized_pdf = sample_pdf_bytes + (b" " * (max_bytes + 1))
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(oversized_pdf), "application/pdf")}
        data = {"job_description": "Senior Python developer"}

        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)

        assert response.status_code == 413
        assert "File too large" in response.json()["detail"]

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_file_exactly_max_size(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Accept files exactly at the configured size limit and proceed to analysis."""
        max_bytes = settings.app.max_upload_size_mb * 1024 * 1024
        sized_pdf = sample_pdf_bytes + (b" " * max(0, max_bytes - len(sample_pdf_bytes)))
        
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**sample_cv_analysis_response)
        )

        files = {"cv_file": ("resume.pdf", io.BytesIO(sized_pdf), "application/pdf")}
        data = {"job_description": "Senior Python developer"}

        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)

        assert response.status_code == 200
        assert response.json()["fit_score"] == sample_cv_analysis_response["fit_score"]

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_success(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test successful CV analysis with PDF."""
        # Mock the analysis service
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**sample_cv_analysis_response)
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Looking for senior Python developer with FastAPI expertise"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        assert result["fit_score"] == 85
        assert result["summary"] == "Strong match for senior Python developer role."
        assert len(result["strengths"]) > 0
        assert len(result["gaps"]) > 0
        assert "cached" in result
        assert result["cached"] is False

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_docx_success(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_docx_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test successful CV analysis with DOCX."""
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**sample_cv_analysis_response)
        )
        
        files = {"cv_file": ("resume.docx", io.BytesIO(sample_docx_bytes), 
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        data = {"job_description": "Senior Python developer required"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        assert "fit_score" in result

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_returns_cached_response(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that cached responses are returned with cached=True."""
        cached_response = {**sample_cv_analysis_response, "cached": True}
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**cached_response)
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        assert result["cached"] is True

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_includes_warnings(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that warnings from parsing are included in response."""
        with_warnings = {
            **sample_cv_analysis_response,
            "warnings": ["PDF may be image-based"],
        }
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**with_warnings)
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        assert "PDF may be image-based" in result["warnings"]

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_evidence_items(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that evidence items are properly returned."""
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**sample_cv_analysis_response)
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        assert len(result["evidence"]) > 0
        assert "claim" in result["evidence"][0]
        assert "cv_quote" in result["evidence"][0]

    def test_analyze_cv_missing_file(
        self, client: TestClient, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test that missing CV file raises error."""
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 422

    def test_analyze_cv_missing_job_description(
        self, client: TestClient, sample_pdf_bytes: bytes, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test that missing job description raises error."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        
        response = client.post("/v1/cv/analyze", files=files, headers=valid_api_key_headers)
        
        assert response.status_code == 422

    def test_analyze_cv_unsupported_file_type(
        self, client: TestClient, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test that unsupported file types are rejected."""
        files = {"cv_file": ("resume.txt", io.BytesIO(b"X" * 600), "text/plain")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_analyze_cv_empty_file(
        self, client: TestClient, valid_api_key_headers: dict[str, str]
    ) -> None:
        """Test that empty CV files are rejected."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(b""), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 400
        assert "Empty file" in response.json()["detail"]


# ======================== Error Handling Tests ========================


class TestAnalyzeCVErrorHandling:
    """Test error handling in /cv/analyze endpoint."""

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_validation_error(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that ValidationAppError returns 400."""
        mock_service.analyze = AsyncMock(
            side_effect=ValidationAppError(
                code="cv_text_too_short",
                message="CV text is too short",
            )
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 400
        assert "CV text is too short" in response.json()["detail"]

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_llm_error(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that LLMAppError returns 500."""
        mock_service.analyze = AsyncMock(
            side_effect=LLMAppError(
                code="llm_call_failed",
                message="OpenAI API error: rate limit exceeded",
            )
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 500
        assert "OpenAI API error" in response.json()["detail"]

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_unexpected_error(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that unexpected errors return 500 with generic message."""
        mock_service.analyze = AsyncMock(
            side_effect=RuntimeError("Unexpected database error")
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 500
        assert "Unexpected error during analysis" in response.json()["detail"]


# ======================== Response Schema Validation Tests ========================


class TestAnalyzeCVResponseSchema:
    """Test that response schema is properly validated."""

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_response_contains_all_required_fields(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that response contains all required fields."""
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**sample_cv_analysis_response)
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        result = response.json()
        
        # Required fields from CVAnalysisResponse
        required_fields = [
            "summary",
            "fit_score",
            "fit_score_rationale",
            "strengths",
            "gaps",
            "missing_keywords",
            "rewrite_suggestions",
            "ats_notes",
            "red_flags",
            "next_steps",
            "evidence",
            "confidence",
            "warnings",
            "cached",
        ]
        
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_fit_score_in_valid_range(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that fit_score is in valid range 0-100."""
        # Test with fit_score = 0
        response_0 = {**sample_cv_analysis_response, "fit_score": 0}
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**response_0)
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        assert response.status_code == 200
        assert response.json()["fit_score"] == 0
        
        # Test with fit_score = 100
        response_100 = {**sample_cv_analysis_response, "fit_score": 100}
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**response_100)
        )
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        assert response.status_code == 200
        assert response.json()["fit_score"] == 100

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_confidence_is_valid_literal(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that confidence is one of valid values."""
        for confidence_level in ["low", "medium", "high"]:
            response_data = {**sample_cv_analysis_response, "confidence": confidence_level}
            mock_service.analyze = AsyncMock(
                return_value=CVAnalysisResponse(**response_data)
            )
            
            files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
            data = {"job_description": "Senior Python developer"}
            
            response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
            assert response.status_code == 200
            assert response.json()["confidence"] == confidence_level


# ======================== Integration Tests ========================


class TestAnalyzeCVIntegration:
    """Integration tests for full analyze workflow."""

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_full_workflow(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test full analyze workflow from file upload to response."""
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**sample_cv_analysis_response)
        )
        
        # Upload CV and job description
        files = {"cv_file": ("John_Doe_Resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {
            "job_description": "Looking for senior Python developer with 5+ years experience in FastAPI"
        }
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        # Verify response
        assert response.status_code == 200
        result = response.json()
        assert isinstance(result, dict)
        assert result["fit_score"] > 0
        assert result["summary"] != ""
        
        # Verify service was called with correct args
        mock_service.analyze.assert_called_once()
        call_kwargs = mock_service.analyze.call_args.kwargs
        assert "cv_text" in call_kwargs
        assert "job_text" in call_kwargs
        assert call_kwargs["job_text"] == data["job_description"]

    @patch("app.api.routes.cv._analysis_service")
    def test_analyze_cv_service_receives_parsed_cv_text(
        self,
        mock_service: MagicMock,
        client: TestClient,
        sample_pdf_bytes: bytes,
        sample_cv_analysis_response: dict,
        valid_api_key_headers: dict[str, str],
    ) -> None:
        """Test that service receives extracted CV text from parser."""
        mock_service.analyze = AsyncMock(
            return_value=CVAnalysisResponse(**sample_cv_analysis_response)
        )
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        data = {"job_description": "Senior Python developer"}
        
        response = client.post("/v1/cv/analyze", files=files, data=data, headers=valid_api_key_headers)
        
        assert response.status_code == 200
        
        # Verify cv_text is passed to service
        call_kwargs = mock_service.analyze.call_args.kwargs
        assert "cv_text" in call_kwargs
        # CV text should be non-empty normalized text
        assert len(call_kwargs["cv_text"]) > 0
