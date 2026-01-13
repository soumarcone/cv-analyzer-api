"""Unit tests for API key authentication module."""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

# Set required env vars before importing settings
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o")
os.environ.setdefault("LLM_API_KEY", "test-key")

from app.core.auth import parse_api_keys, validate_api_key, verify_api_key
from app.core.errors import AuthenticationAppError


class TestParseAPIKeys:
    """Test API key parsing utility function."""

    def test_parse_single_key(self) -> None:
        """Test parsing a single API key."""
        result = parse_api_keys("my-secret-key")
        assert result == {"my-secret-key"}

    def test_parse_multiple_keys(self) -> None:
        """Test parsing multiple comma-separated keys."""
        result = parse_api_keys("key1,key2,key3")
        assert result == {"key1", "key2", "key3"}

    def test_parse_keys_with_whitespace(self) -> None:
        """Test that whitespace is trimmed from keys."""
        result = parse_api_keys("key1 , key2  ,  key3")
        assert result == {"key1", "key2", "key3"}

    def test_parse_none_returns_empty_set(self) -> None:
        """Test that None input returns empty set."""
        result = parse_api_keys(None)
        assert result == set()

    def test_parse_empty_string_returns_empty_set(self) -> None:
        """Test that empty string returns empty set."""
        result = parse_api_keys("")
        assert result == set()

    def test_parse_whitespace_only_returns_empty_set(self) -> None:
        """Test that whitespace-only string returns empty set."""
        result = parse_api_keys("   ,  ,  ")
        assert result == set()

    def test_parse_removes_duplicate_keys(self) -> None:
        """Test that duplicate keys are deduplicated."""
        result = parse_api_keys("key1,key2,key1,key3,key2")
        assert result == {"key1", "key2", "key3"}


class TestValidateAPIKey:
    """Test core API key validation logic."""

    @patch("app.core.auth.settings")
    def test_validate_bypassed_when_auth_disabled(self, mock_settings) -> None:
        """Test that validation is skipped when API_KEY_REQUIRED=false."""
        mock_settings.app.api_key_required = False

        # Should not raise even with invalid key
        validate_api_key("any-random-key")
        validate_api_key("")

    @patch("app.core.auth.settings")
    def test_validate_raises_when_no_keys_configured(self, mock_settings) -> None:
        """Test error when authentication is required but no keys are configured."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = None

        with pytest.raises(AuthenticationAppError) as exc_info:
            validate_api_key("some-key")

        assert exc_info.value.code == "api_keys_not_configured"
        assert "no valid keys are configured" in exc_info.value.message

    @patch("app.core.auth.settings")
    def test_validate_raises_when_empty_keys_configured(self, mock_settings) -> None:
        """Test error when authentication is required but keys string is empty."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = ""

        with pytest.raises(AuthenticationAppError) as exc_info:
            validate_api_key("some-key")

        assert exc_info.value.code == "api_keys_not_configured"

    @patch("app.core.auth.settings")
    def test_validate_accepts_valid_key(self, mock_settings) -> None:
        """Test that valid API key passes validation."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = "valid-key-1,valid-key-2"

        # Should not raise
        validate_api_key("valid-key-1")
        validate_api_key("valid-key-2")

    @patch("app.core.auth.settings")
    def test_validate_rejects_invalid_key(self, mock_settings) -> None:
        """Test that invalid API key is rejected."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = "valid-key-1,valid-key-2"

        with pytest.raises(AuthenticationAppError) as exc_info:
            validate_api_key("invalid-key")

        assert exc_info.value.code == "invalid_api_key"
        assert "Invalid or missing API key" in exc_info.value.message

    @patch("app.core.auth.settings")
    def test_validate_rejects_empty_key(self, mock_settings) -> None:
        """Test that empty key is rejected."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = "valid-key"

        with pytest.raises(AuthenticationAppError) as exc_info:
            validate_api_key("")

        assert exc_info.value.code == "invalid_api_key"

    @patch("app.core.auth.settings")
    def test_validate_handles_whitespace_in_configured_keys(self, mock_settings) -> None:
        """Test that configured keys with whitespace are handled correctly."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = " key1 , key2 , key3 "

        # Trimmed keys should match
        validate_api_key("key1")
        validate_api_key("key2")

        # Key with spaces should not match (we trim configured keys)
        with pytest.raises(AuthenticationAppError):
            validate_api_key(" key1 ")


class TestVerifyAPIKeyDependency:
    """Test FastAPI dependency for API key verification."""

    @pytest.mark.asyncio
    @patch("app.core.auth.settings")
    async def test_verify_bypassed_when_auth_disabled(self, mock_settings) -> None:
        """Test that dependency allows requests when auth is disabled."""
        mock_settings.app.api_key_required = False

        # Should not raise even without header
        await verify_api_key(x_api_key=None)

    @pytest.mark.asyncio
    @patch("app.core.auth.settings")
    async def test_verify_raises_403_when_header_missing(self, mock_settings) -> None:
        """Test that missing X-API-Key header returns 403."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = "valid-key"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(x_api_key=None)

        assert exc_info.value.status_code == 403
        assert "Missing API key" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.core.auth.settings")
    async def test_verify_raises_403_when_key_invalid(self, mock_settings) -> None:
        """Test that invalid API key returns 403."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = "valid-key"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(x_api_key="wrong-key")

        assert exc_info.value.status_code == 403
        assert "Invalid or missing API key" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.core.auth.settings")
    async def test_verify_accepts_valid_key(self, mock_settings) -> None:
        """Test that valid API key passes verification."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = "my-valid-key,another-key"

        # Should not raise
        await verify_api_key(x_api_key="my-valid-key")
        await verify_api_key(x_api_key="another-key")

    @pytest.mark.asyncio
    @patch("app.core.auth.settings")
    async def test_verify_raises_403_when_keys_not_configured(self, mock_settings) -> None:
        """Test that dependency returns 403 when no keys are configured."""
        mock_settings.app.api_key_required = True
        mock_settings.app.api_keys = None

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(x_api_key="some-key")

        assert exc_info.value.status_code == 403
        assert "no valid keys are configured" in exc_info.value.detail
