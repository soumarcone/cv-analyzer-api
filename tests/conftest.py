"""Pytest configuration and fixtures shared across all test modules.

This file is automatically loaded by pytest before running any tests.
With APP_ENV=testing, the correct .env.testing file is loaded automatically.
"""

import os

# Ensure testing environment is set before any app imports
# Force APP_ENV to testing (not setdefault, to override any existing value)
os.environ["APP_ENV"] = "testing"

