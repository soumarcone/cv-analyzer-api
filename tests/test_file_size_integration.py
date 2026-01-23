"""Integration tests for file size validation with real HTTP server.

These tests start an actual Uvicorn server to test file upload limits
with real HTTP multipart requests, avoiding TestClient limitations.
"""

import asyncio
import io
import multiprocessing
import os
import tempfile
import time
from typing import Generator

import httpx
import pytest
import uvicorn

from app.core.config import settings


def run_server():
    """Run FastAPI server in a separate process."""
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        log_level="error",
        access_log=False,
    )


@pytest.fixture(scope="module")
def server() -> Generator[str, None, None]:
    """Start server in background process for integration tests."""
    # Start server in separate process
    process = multiprocessing.Process(target=run_server, daemon=True)
    process.start()
    
    # Wait for server to be ready
    base_url = "http://127.0.0.1:8001"
    max_retries = 30
    for _ in range(max_retries):
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(0.1)
    else:
        process.terminate()
        pytest.fail("Server failed to start")
    
    yield base_url
    
    # Cleanup
    process.terminate()
    process.join(timeout=5)


@pytest.fixture
def api_headers() -> dict[str, str]:
    """Valid API key headers for authenticated requests."""
    return {"X-API-Key": "test-api-key-123"}


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Create minimal valid PDF bytes."""
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


class TestFileSizeIntegration:
    """Integration tests for file size validation with real HTTP server."""

    def test_parse_cv_file_too_large(
        self, server: str, api_headers: dict, sample_pdf_bytes: bytes
    ) -> None:
        """Reject files exceeding configured size limit with HTTP 413."""
        # Create file larger than limit (1MB in .env.testing)
        max_bytes = settings.app.max_upload_size_mb * 1024 * 1024
        oversized_pdf = sample_pdf_bytes + (b" " * (max_bytes + 1))

        # Use temporary file to avoid BytesIO pre-loading in httpx
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(oversized_pdf)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                files = {"cv_file": ("resume.pdf", f, "application/pdf")}
                response = httpx.post(
                    f"{server}/v1/cv/parse",
                    headers=api_headers,
                    files=files,
                    timeout=10.0,
                )

            assert response.status_code == 413
            assert "File too large" in response.json()["detail"]
        finally:
            os.unlink(tmp_path)

    def test_parse_cv_file_exactly_max_size(
        self, server: str, api_headers: dict, sample_pdf_bytes: bytes
    ) -> None:
        """Accept files exactly at the configured size limit."""
        max_bytes = settings.app.max_upload_size_mb * 1024 * 1024
        sized_pdf = sample_pdf_bytes + (b" " * max(0, max_bytes - len(sample_pdf_bytes)))
        
        files = {"cv_file": ("resume.pdf", io.BytesIO(sized_pdf), "application/pdf")}
        
        response = httpx.post(
            f"{server}/v1/cv/parse",
            headers=api_headers,
            files=files,
            timeout=10.0,
        )
        
        assert response.status_code == 200

    def test_analyze_cv_file_too_large(
        self, server: str, api_headers: dict, sample_pdf_bytes: bytes
    ) -> None:
        """Reject oversized files before analysis begins."""
        max_bytes = settings.app.max_upload_size_mb * 1024 * 1024
        oversized_pdf = sample_pdf_bytes + (b" " * (max_bytes + 1))

        # Use temporary file to avoid BytesIO pre-loading in httpx
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(oversized_pdf)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                files = {"cv_file": ("resume.pdf", f, "application/pdf")}
                data = {"job_description": "Senior Python developer"}

                response = httpx.post(
                    f"{server}/v1/cv/analyze",
                    headers=api_headers,
                    files=files,
                    data=data,
                    timeout=10.0,
                )

            assert response.status_code == 413
            assert "File too large" in response.json()["detail"]
        finally:
            os.unlink(tmp_path)

    def test_parse_cv_small_file_success(
        self, server: str, api_headers: dict, sample_pdf_bytes: bytes
    ) -> None:
        """Small files should be processed successfully."""
        files = {"cv_file": ("resume.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        
        response = httpx.post(
            f"{server}/v1/cv/parse",
            headers=api_headers,
            files=files,
            timeout=10.0,
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["file_name"] == "resume.pdf"
        assert result["file_type"] == "pdf"
        assert result["char_count"] > 0
