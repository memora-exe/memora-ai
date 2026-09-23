"""Pytest configuration and test environment setup."""
import os

# Ensure default test environment variables are set before app imports
os.environ.setdefault("MEMORA_INTERNAL_TOKEN", "test-internal-token")

from app.core.config import settings

if not settings.MEMORA_INTERNAL_TOKEN:
    settings.MEMORA_INTERNAL_TOKEN = "test-internal-token"
