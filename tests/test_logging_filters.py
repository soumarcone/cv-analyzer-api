"""Tests for sensitive data filtering in logs."""

from __future__ import annotations

import logging
from io import StringIO

from app.core.logging import JsonFormatter, SensitiveDataFilter


def test_sensitive_filter_redacts_api_keys():
    """Ensure SensitiveDataFilter redacts API key fields."""
    
    logger = logging.getLogger("test_redaction")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    
    logger.info(
        "test_event",
        extra={
            "api_key": "sk-secret-123",
            "x-api-key": "another-secret",
            "safe_field": "visible",
        },
    )
    
    output = stream.getvalue()
    
    assert "sk-secret-123" not in output
    assert "another-secret" not in output
    assert "[REDACTED]" in output
    assert "visible" in output


def test_sensitive_filter_redacts_cv_text():
    """Ensure cv_text and job_text are redacted."""
    
    logger = logging.getLogger("test_cv_redaction")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    
    logger.info(
        "parse_event",
        extra={
            "cv_text": "John Doe, Software Engineer, email@example.com",
            "job_text": "Looking for senior developer with 5 years exp",
            "char_count": 100,
        },
    )
    
    output = stream.getvalue()
    
    assert "John Doe" not in output
    assert "email@example.com" not in output
    assert "senior developer" not in output
    assert "[REDACTED]" in output
    assert "char_count" in output


def test_sensitive_filter_allows_safe_fields():
    """Verify safe fields pass through unmodified."""
    
    logger = logging.getLogger("test_safe_fields")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    
    logger.info(
        "safe_event",
        extra={
            "request_id": "req-123",
            "route": "/v1/cv/parse",
            "status": 200,
            "duration_ms": 150.5,
        },
    )
    
    output = stream.getvalue()
    
    assert "req-123" in output
    assert "/v1/cv/parse" in output
    assert "200" in output
    assert "[REDACTED]" not in output


def test_sensitive_filter_redacts_nested_dicts():
    """Ensure nested sensitive fields are redacted."""
    
    logger = logging.getLogger("test_nested")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    
    logger.info(
        "nested_event",
        extra={
            "headers": {
                "x-api-key": "secret-key",
                "user-agent": "pytest",
            },
            "safe_data": {
                "count": 5,
                "type": "test",
            },
        },
    )
    
    output = stream.getvalue()
    
    assert "secret-key" not in output
    assert "[REDACTED]" in output
    assert "pytest" in output
    assert "test" in output
