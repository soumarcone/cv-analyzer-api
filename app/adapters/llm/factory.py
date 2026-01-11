"""Factory pattern for creating LLM client instances."""

from app.adapters.llm.base import AbstractLLMClient
from app.adapters.llm.openai_client import OpenAIClient
from app.core.config import settings
from app.core.errors import ValidationAppError


def create_llm_client() -> AbstractLLMClient:
    """Factory function to instantiate LLM clients based on provider.

    Reads configuration from app.core.config.settings (Pydantic Settings).
    Validates provider-specific requirements and routes to appropriate client.

    Returns:
        AbstractLLMClient: Configured LLM client instance.

    Raises:
        ValidationAppError: If provider-specific requirements are not met.
    """
    provider = settings.llm.provider.lower()

    # Route to OpenAI
    if provider == "openai":
        if not settings.llm.api_key:
            raise ValidationAppError(
                code="llm_missing_api_key",
                message="OpenAI provider requires LLM_API_KEY environment variable",
            )
        return OpenAIClient(
            api_key=settings.llm.api_key,
            model=settings.llm.model,
            base_url=settings.llm.base_url,
            timeout_seconds=settings.llm.timeout_seconds,
        )

    # Future providers can be added here
    # elif provider == "anthropic":
    #     if not settings.llm.api_key:
    #         raise ValueError("Anthropic requires LLM_API_KEY")
    #     return AnthropicClient(
    #         api_key=settings.llm.api_key,
    #         model=settings.llm.model,
    #         timeout_seconds=settings.llm.timeout_seconds,
    #     )
    #
    # elif provider == "ollama":
    #     if not settings.llm.base_url:
    #         raise ValueError("Ollama requires LLM_BASE_URL")
    #     return OllamaClient(
    #         base_url=settings.llm.base_url,
    #         model=settings.llm.model,
    #         timeout_seconds=settings.llm.timeout_seconds,
    #     )

    raise ValidationAppError(
        code="llm_unknown_provider",
        message=(
            f"Unknown LLM provider: '{provider}'. Supported providers: openai"
        ),
    )
