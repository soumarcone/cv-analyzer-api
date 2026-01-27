"""Tests for global exception handlers.

Validates that all exception types are handled consistently with
proper HTTP status codes, error format, and no information leakage.
"""

import asyncio
import json
import os
from unittest.mock import patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Set required env vars before importing settings
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o")
os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.errors import (
    AppError,
    ValidationAppError,
    AuthenticationAppError,
    LLMAppError,
)
from app.core.exception_handlers import setup_exception_handlers


@pytest.fixture
def app_with_handlers() -> FastAPI:
    """Create FastAPI app with exception handlers registered."""
    app = FastAPI()
    setup_exception_handlers(app)
    return app


@pytest.fixture
def client(app_with_handlers: FastAPI) -> TestClient:
    """Create test client with handlers enabled."""
    return TestClient(app_with_handlers)


class TestAppErrorHandler:
    """Test handler for AppError and subclasses."""

    def test_validation_error_returns_400(self, client: TestClient, app_with_handlers: FastAPI):
        """Verify ValidationAppError returns HTTP 400."""
        @app_with_handlers.get("/test-validation")
        async def test_endpoint():
            raise ValidationAppError(
                code="test_validation",
                message="Test validation error"
            )
        
        response = client.get("/test-validation")
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "test_validation"
        assert data["error"]["message"] == "Test validation error"
        assert "request_id" in data["error"]

    def test_validation_error_includes_details(self, client: TestClient, app_with_handlers: FastAPI):
        """Verify ValidationAppError includes details when provided."""
        @app_with_handlers.get("/test-validation-details")
        async def test_endpoint():
            raise ValidationAppError(
                code="file_too_large",
                message="File exceeds maximum size",
                details={
                    "actual_size": 5000000,
                    "max_size": 1000000,
                    "file_type": "pdf"
                }
            )
        
        response = client.get("/test-validation-details")
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["details"]["actual_size"] == 5000000
        assert data["error"]["details"]["max_size"] == 1000000

    def test_authentication_error_returns_403(self, client: TestClient, app_with_handlers: FastAPI):
        """Verify AuthenticationAppError returns HTTP 403 Forbidden."""
        @app_with_handlers.get("/test-auth")
        async def test_endpoint():
            raise AuthenticationAppError(
                code="invalid_api_key",
                message="Invalid or missing API key"
            )
        
        response = client.get("/test-auth")
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "invalid_api_key"

    def test_llm_error_returns_500(self, client: TestClient, app_with_handlers: FastAPI):
        """Verify LLMAppError returns HTTP 500."""
        @app_with_handlers.get("/test-llm")
        async def test_endpoint():
            raise LLMAppError(
                code="api_error",
                message="LLM service returned an error"
            )
        
        response = client.get("/test-llm")
        
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "api_error"

    def test_error_response_format_is_consistent(self, client: TestClient, app_with_handlers: FastAPI):
        """Verify error responses have consistent JSON structure."""
        @app_with_handlers.get("/test-format")
        async def test_endpoint():
            raise ValidationAppError(code="test", message="test")
        
        response = client.get("/test-format")
        data = response.json()
        
        # Required fields always present
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "request_id" in data["error"]


class TestGeneralExceptionHandler:
    """Test fallback handler for unexpected exceptions."""

    def test_unexpected_exception_handler_registered(self, app_with_handlers: FastAPI):
        """Verify fallback exception handler is registered."""
        assert Exception in app_with_handlers.exception_handlers

    def test_general_exception_handler_logic(self):
        """Verify general_exception_handler returns correct structure."""
        from app.core.exception_handlers import general_exception_handler
        
        request = AsyncMock()
        request.url.path = "/test"
        request.method = "GET"
        
        exc = RuntimeError("Unexpected error: database connection failed")
        response = asyncio.run(general_exception_handler(request, exc))
        
        # Verify response structure
        response_body = response.body if isinstance(response.body, bytes) else bytes(response.body)
        data = json.loads(response_body.decode())
        assert response.status_code == 500
        assert data["error"]["code"] == "internal_server_error"
        # Original error message should NOT be in response
        assert "database connection" not in data["error"]["message"]
        assert "request_id" in data["error"]

    def test_general_exception_handler_never_leaks_stack_trace(self):
        """Verify stack traces are never included in response."""
        from app.core.exception_handlers import general_exception_handler
        
        request = AsyncMock()
        request.url.path = "/test"
        request.method = "GET"
        
        exc = ValueError("Test error with details")
        response = asyncio.run(general_exception_handler(request, exc))
        
        response_body = response.body if isinstance(response.body, bytes) else bytes(response.body)
        response_text = response_body.decode()
        # No traceback indicators
        assert "Traceback" not in response_text
        assert "File \"" not in response_text
        assert "ValueError" not in response_text


class TestErrorHandlerIntegration:
    """Integration tests for exception handler setup."""

    def test_setup_exception_handlers_registers_handlers(self, app_with_handlers: FastAPI):
        """Verify setup_exception_handlers properly registers handlers."""
        # Check that handlers are registered
        assert AppError in app_with_handlers.exception_handlers
        assert Exception in app_with_handlers.exception_handlers

    def test_multiple_handler_setups_does_not_fail(self):
        """Verify calling setup_exception_handlers multiple times is safe."""
        app = FastAPI()
        
        # Should not raise or fail
        setup_exception_handlers(app)
        setup_exception_handlers(app)  # Second call should override safely
        
        assert AppError in app.exception_handlers
