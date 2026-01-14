"""Pytest configuration and fixtures shared across all test modules.

This file is automatically loaded by pytest before running any tests.
It ensures that the TESTING environment variable is set to prevent
loading the .env file during tests.
"""

import os

# CRITICAL: Set this before any imports that might load settings
# This prevents Pydantic from loading the .env file in tests
os.environ["TESTING"] = "true"

# Set default env vars that all tests might need
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o")
os.environ.setdefault("LLM_API_KEY", "test-key-123")
os.environ.setdefault("APP_API_KEY_REQUIRED", "true")
os.environ.setdefault("APP_API_KEYS", "test-api-key-123,test-api-key-456")
