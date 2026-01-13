"""Integration tests for LLM adapter layer."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import os

# Ensure required env vars exist before importing settings-dependent modules
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o")
os.environ.setdefault("LLM_API_KEY", "test-key")

from app.adapters.llm import OpenAIClient, create_llm_client
from app.core.config import settings, LLMSettings, Settings, AppSettings
from app.core.errors import ValidationAppError


class TestOpenAIClientIntegration:
    """Test OpenAI client integration with mocked API calls."""

    @pytest.mark.asyncio
    async def test_generate_json_success(self) -> None:
        """Test successful JSON generation from OpenAI client.
        
        Validates that the client correctly calls the API and parses JSON response.
        """
        # Mock response data
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"status": "success", "data": {"key": "value"}}'
                )
            )
        ]

        # Create client and patch the API call
        client = OpenAIClient(
            api_key="test-key-123",
            model="gpt-4o",
        )

        with patch.object(
            client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await client.generate_json(
                prompt="Generate test JSON",
                schema={"type": "object"},
                temperature=0.1,
            )

        # Assertions
        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert result["data"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_generate_json_with_schema_enforces_json_mode(self) -> None:
        """Test that providing schema enables JSON response format.
        
        Ensures response_format is set when schema parameter is provided.
        """
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"result": "ok"}'))
        ]

        client = OpenAIClient(api_key="test-key", model="gpt-4o")

        with patch.object(
            client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            await client.generate_json(
                prompt="Test",
                schema={"type": "object"},
            )

            # Verify response_format was set
            call_kwargs = mock_create.call_args.kwargs
            assert "response_format" in call_kwargs
            assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_generate_json_invalid_json_raises_error(self) -> None:
        """Test that invalid JSON response raises RuntimeError.
        
        Validates error handling when LLM returns malformed JSON.
        """
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="This is not JSON"))
        ]

        client = OpenAIClient(api_key="test-key", model="gpt-4o")

        with patch.object(
            client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with pytest.raises(RuntimeError, match="invalid JSON"):
                await client.generate_json(prompt="Test")


class TestLLMFactory:
    """Test LLM client factory pattern."""

    def test_create_llm_client_with_settings(self) -> None:
        """Test factory creates OpenAI client using settings.
        
        Validates that factory correctly instantiates client with provided settings.
        """
        # Patch global settings with desired values
        settings.llm = LLMSettings(
            provider="openai",
            api_key="test-key",
            model="gpt-4o-mini",
            base_url=None,
            timeout_seconds=30.0,
        )

        client = create_llm_client()

        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4o-mini"

    def test_create_llm_client_missing_api_key_raises_error(self) -> None:
        """Test factory raises error when API key is missing.
        
        Ensures proper validation of required credentials.
        """
        settings.llm = LLMSettings(
            provider="openai",
            api_key=None,
            model="gpt-4o",
            base_url=None,
            timeout_seconds=45.0,
        )

        with pytest.raises(ValidationAppError, match="requires LLM_API_KEY") as exc:
            create_llm_client()
        assert exc.value.code == "llm_missing_api_key"

    def test_create_llm_client_unknown_provider_raises_error(self) -> None:
        """Test factory raises error for unknown provider.
        
        Validates that unsupported providers are rejected with clear error.
        """
        settings.llm = LLMSettings(
            provider="unknown-provider",
            api_key="test-key",
            model="gpt-4o",
            base_url=None,
            timeout_seconds=45.0,
        )

        with pytest.raises(ValidationAppError, match="Unknown LLM provider") as exc:
            create_llm_client()
        assert exc.value.code == "llm_unknown_provider"

    def test_create_llm_client_with_new_settings_instance(self) -> None:
        """Test factory using a fresh Settings instance.
        
        Validates that replacing global settings influences factory behavior.
        """
        new_settings = Settings(
            llm=LLMSettings(
                provider="openai",
                api_key="env-key",
                model="gpt-4o",
                base_url=None,
                timeout_seconds=45.0,
            ),
            app=AppSettings(
                debug=False,
                max_upload_size_mb=10,
                max_cv_chars=50000,
                max_job_desc_chars=10000,
                api_key_required=True,
                api_keys="test-key-1,test-key-2",
                min_cv_chars=500,
                cv_preview_chars=800,
            ),
        )
        # Patch the global settings reference
        import app.core.config as cfg
        cfg.settings = new_settings
        import app.adapters.llm.factory as factory_mod
        factory_mod.settings = new_settings

        client = create_llm_client()

        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4o"
