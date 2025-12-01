"""Pytest configuration and shared fixtures.

Author: Odiseo Team
Created: 2025-10-31
Version: 1.0.0
"""

import asyncio

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "DEMO_MAX_TOKENS": 5000,
        "DEMO_COOLDOWN_HOURS": 24,
        "DEMO_WARNING_THRESHOLD": 85,
        "IP_RATE_LIMIT_REQUESTS": 100,
        "FINGERPRINT_SCORE_THRESHOLD": 0.7,
        "ENABLE_CAPTCHA": True,
        "ENABLE_FINGERPRINT": True,
    }
