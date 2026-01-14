"""Application configuration using Pydantic Settings.

Configuration is environment-aware:
- APP_ENV determines which .env file to load
- Supports: development, testing, staging, production
- Each environment has its own .env.{environment} file
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Determine which environment to load (default: development)
APP_ENV = os.getenv("APP_ENV", "development")

# Project root (so .env resolution doesn't depend on current working directory)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Map environments to their respective .env files (relative to PROJECT_ROOT)
ENV_FILE_MAP = {
    "development": ".env.development",
    "testing": ".env.testing",
    "staging": ".env.staging",
    "production": ".env.production",
}

# Select the .env file for the current environment
_env_filename = ENV_FILE_MAP.get(APP_ENV, ".env.development")
_env_path = PROJECT_ROOT / _env_filename

# Only load from file if it exists (production might inject via env vars only)
_env_file = str(_env_path) if _env_path.is_file() else None


# Load .env file early to populate os.environ before creating nested settings
# This is necessary because Pydantic nested BaseSettings don't inherit env_file
if _env_file:
    from dotenv import load_dotenv
    load_dotenv(_env_file, override=True)


def _build_llm_settings() -> "LLMSettings":
    """Build LLM settings from environment.

    Pydantic Settings (v2) can populate values from environment variables.
    However, static type checkers often treat required fields as required
    constructor arguments, which is not how BaseSettings is intended to be used.
    """

    return LLMSettings()  # type: ignore[call-arg]


def _build_app_settings() -> "AppSettings":
    """Build app settings from environment.

    See _build_llm_settings() for rationale about the type ignore.
    """

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
    api_keys: str | None = Field(
        None,
        description="Comma-separated list of valid API keys for authentication",
    )

    rate_limit_enabled: bool = Field(
        True,
        description="Enable global rate limiting per API key",
    )
    rate_limit_requests: int = Field(
        10,
        description="Maximum number of requests allowed per window (per API key)",
        ge=1,
    )
    rate_limit_window_seconds: int = Field(
        60,
        description="Rate limit window size in seconds",
        ge=1,
    )
    rate_limit_include_headers: bool = Field(
        True,
        description="Include X-RateLimit-* and Retry-After headers when throttling",
    )

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        case_sensitive=False,
    )


class Settings(BaseSettings):
    """Main application settings container.
    
    Automatically loads from the appropriate .env.{APP_ENV} file.
    Raises validation errors on startup if required settings are missing.
    
    Environments:
    - development: Local development (DEBUG=true)
    - testing: Automated tests (uses .env.testing)
    - staging: Pre-production (uses .env.staging)
    - production: Production deployment (uses .env.production)
    """

    app_env: str = APP_ENV
    llm: LLMSettings = Field(default_factory=_build_llm_settings)
    app: AppSettings = Field(default_factory=_build_app_settings)

    model_config = SettingsConfigDict(
        case_sensitive=False,
    )


# Global settings instance - composed from domain-specific settings
# Nested settings are created via default_factory so env loading works.
settings = Settings()
