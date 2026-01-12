"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _build_llm_settings() -> "LLMSettings":
    """Build LLM settings from env.

    Pydantic's generated __init__ signature marks required fields as required
    for static type checkers, even though BaseSettings can populate them from
    environment variables.
    """

    return LLMSettings()  # type: ignore[call-arg]


def _build_app_settings() -> "AppSettings":
    """Build application settings from env with sane defaults."""

    return AppSettings()  # type: ignore[call-arg]


class LLMSettings(BaseSettings):
    """LLM provider configuration.
    
    Supports multiple providers (OpenAI, Anthropic, Ollama, etc.).
    Validation of provider-specific requirements happens in the factory.
    """

    provider: str = Field(
        ...,
        description="LLM provider name (e.g., openai, anthropic, ollama)",
    )
    model: str = Field(
        ...,
        description="Model name (e.g., gpt-4o, claude-3-5-sonnet, llama2)",
    )
    api_key: str | None = Field(
        None,
        description="API key for cloud providers (required for OpenAI, Anthropic)",
    )
    base_url: str | None = Field(
        None,
        description="Custom API endpoint (required for local providers like Ollama)",
    )
    timeout_seconds: float = Field(
        45.0,
        description="Request timeout in seconds",
    )

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        case_sensitive=False,
    )


class AppSettings(BaseSettings):
    """Application-wide configuration."""

    debug: bool = Field(
        False,
        description="Enable debug mode with verbose logging",
    )
    max_upload_size_mb: int = Field(
        10,
        description="Maximum file upload size in megabytes",
    )
    max_cv_chars: int = Field(
        50000,
        description="Maximum CV text length in characters",
    )
    max_job_desc_chars: int = Field(
        10000,
        description="Maximum job description text length in characters",
    )
    min_cv_chars: int = Field(
        500,
        description="Minimum CV text length to avoid image-based PDFs without OCR",
    )
    cv_preview_chars: int = Field(
        800,
        description="Number of characters to include in CV preview",
    )
    api_key_required: bool = Field(
        True,
        description="Whether API key authentication is required",
    )

    model_config = SettingsConfigDict(
        case_sensitive=False,
    )


class Settings(BaseSettings):
    """Main application settings container.
    
    Automatically loads from .env file and validates all configuration.
    Raises validation errors on startup if required settings are missing.
    """

    llm: LLMSettings = Field(default_factory=_build_llm_settings)
    app: AppSettings = Field(default_factory=_build_app_settings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
    )


# Global settings instance - composed from domain-specific settings
# Nested settings are created via default_factory so env loading works.
settings = Settings()
