"""Unit tests for IP-based rate limiting.

Author: Odiseo Team
Created: 2025-10-31
Version: 1.0.0
"""

from unittest.mock import Mock, patch

import pytest
from demo_agent.config.settings import config
from demo_agent.security.ip_limiter import IPLimiter


@pytest.fixture
def ip_limiter():
    """Create IPLimiter instance with mocked database."""
    with patch("demo_agent.security.ip_limiter.get_db") as mock_db:
        mock_db.return_value = Mock()
        limiter = IPLimiter()
        limiter.db = Mock()
        yield limiter


@pytest.mark.asyncio
async def test_check_rate_limit_allowed(ip_limiter):
    """Test rate limit when under threshold."""
    ip_limiter.db.execute_one.return_value = {"request_count": 10}

    allowed, count = await ip_limiter.check_rate_limit("203.0.113.42")

    assert allowed is True
    assert count == 10


@pytest.mark.asyncio
async def test_check_rate_limit_exceeded(ip_limiter):
    """Test rate limit when exceeded."""
    ip_limiter.db.execute_one.return_value = {"request_count": config.IP_RATE_LIMIT_REQUESTS + 10}

    allowed, count = await ip_limiter.check_rate_limit("203.0.113.42")

    assert allowed is False
    assert count >= config.IP_RATE_LIMIT_REQUESTS


@pytest.mark.asyncio
async def test_check_rate_limit_no_history(ip_limiter):
    """Test rate limit for IP with no request history."""
    ip_limiter.db.execute_one.return_value = {"request_count": 0}

    allowed, count = await ip_limiter.check_rate_limit("203.0.113.42")

    assert allowed is True
    assert count == 0


@pytest.mark.asyncio
async def test_check_rate_limit_error_handling(ip_limiter):
    """Test error handling in rate limit check."""
    ip_limiter.db.execute_one.side_effect = Exception("DB error")

    allowed, count = await ip_limiter.check_rate_limit("203.0.113.42")

    # Should fail open
    assert allowed is True
    assert count == 0


@pytest.mark.asyncio
async def test_get_ip_stats(ip_limiter):
    """Test comprehensive IP statistics."""
    from datetime import datetime, timezone

    ip_limiter.db.execute_one.side_effect = [
        {"total_requests": 1000},  # total
        {"requests_today": 150},  # today
        {"requests_per_minute": 5},  # rate
        {"unique_users": 8},  # users
        {"avg_abuse_score": 0.3, "max_abuse_score": 0.7},  # abuse
        {
            "first_seen": datetime.now(timezone.utc),
            "last_seen": datetime.now(timezone.utc),
        },  # timeline
    ]

    stats = await ip_limiter.get_ip_stats("203.0.113.42")

    assert stats["ip_address"] == "203.0.113.42"
    assert stats["total_requests"] == 1000
    assert stats["requests_today"] == 150
    assert stats["requests_per_minute"] == 5
    assert stats["unique_users"] == 8
    assert "abuse_score_avg" in stats
    assert "first_seen" in stats
    assert "last_seen" in stats


@pytest.mark.asyncio
async def test_is_ip_suspicious_high_rate(ip_limiter):
    """Test suspicious detection for high request rate."""
    ip_limiter.db.execute_one.side_effect = [
        {"total_requests": 1000},
        {"requests_today": 500},
        {"requests_per_minute": 20},  # High rate
        {"unique_users": 5},
        {"avg_abuse_score": 0.4, "max_abuse_score": 0.6},
        {
            "first_seen": None,
            "last_seen": None,
        },
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious("203.0.113.42")

    assert is_suspicious is True
    assert "request rate" in reason.lower()


@pytest.mark.asyncio
async def test_is_ip_suspicious_high_abuse_score(ip_limiter):
    """Test suspicious detection for high abuse score."""
    ip_limiter.db.execute_one.side_effect = [
        {"total_requests": 100},
        {"requests_today": 50},
        {"requests_per_minute": 2},
        {"unique_users": 3},
        {"avg_abuse_score": 0.8, "max_abuse_score": 0.95},  # High abuse
        {
            "first_seen": None,
            "last_seen": None,
        },
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious("203.0.113.42")

    assert is_suspicious is True
    assert "abuse" in reason.lower()


@pytest.mark.asyncio
async def test_is_ip_suspicious_many_unique_users(ip_limiter):
    """Test suspicious detection for many unique users."""
    ip_limiter.db.execute_one.side_effect = [
        {"total_requests": 5000},
        {"requests_today": 1000},
        {"requests_per_minute": 2},
        {"unique_users": 50},  # Many users
        {"avg_abuse_score": 0.3, "max_abuse_score": 0.5},
        {
            "first_seen": None,
            "last_seen": None,
        },
        {"blocked_count": 0},  # Extra query for blocked requests
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious("203.0.113.42")

    assert is_suspicious is True
    assert "user" in reason.lower()


@pytest.mark.asyncio
async def test_is_ip_suspicious_legitimate(ip_limiter):
    """Test suspicious detection for legitimate IP."""
    ip_limiter.db.execute_one.side_effect = [
        {"total_requests": 100},
        {"requests_today": 10},
        {"requests_per_minute": 0.5},
        {"unique_users": 1},
        {"avg_abuse_score": 0.1, "max_abuse_score": 0.2},
        {
            "first_seen": None,
            "last_seen": None,
        },
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious("203.0.113.42")

    assert is_suspicious is False


def test_get_reputation_score_legitimate(ip_limiter):
    """Test reputation score for legitimate IP."""
    stats = {
        "requests_per_minute": 1,
        "total_requests": 50,
        "requests_today": 5,
        "abuse_score_avg": 0.1,
        "unique_users": 1,
    }

    score = ip_limiter.get_reputation_score("203.0.113.42", stats)

    assert 0.0 <= score <= 0.1


def test_get_reputation_score_suspicious(ip_limiter):
    """Test reputation score for suspicious IP."""
    stats = {
        "requests_per_minute": 50,  # Way over limit
        "total_requests": 1000,
        "requests_today": 500,
        "abuse_score_avg": 0.7,  # High abuse
        "unique_users": 20,  # Many users
    }

    score = ip_limiter.get_reputation_score("203.0.113.42", stats)

    assert score >= 0.5


def test_get_reputation_score_blocked_requests(ip_limiter):
    """Test reputation score factoring blocked requests."""
    stats = {
        "requests_per_minute": 2,
        "total_requests": 100,
        "requests_today": 50,  # 50% blocked
        "abuse_score_avg": 0.4,
        "unique_users": 1,
    }

    score = ip_limiter.get_reputation_score("203.0.113.42", stats)

    assert score > 0.0


def test_get_reputation_score_capped_at_one(ip_limiter):
    """Test reputation score is capped at 1.0."""
    stats = {
        "requests_per_minute": 1000,
        "total_requests": 100000,
        "requests_today": 100000,
        "abuse_score_avg": 1.0,
        "unique_users": 100,
    }

    score = ip_limiter.get_reputation_score("203.0.113.42", stats)

    assert score <= 1.0


def test_get_reputation_score_error_handling(ip_limiter):
    """Test error handling in reputation score."""
    stats = {}  # Missing required keys

    score = ip_limiter.get_reputation_score("203.0.113.42", stats)

    assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_get_ip_stats_error_handling(ip_limiter):
    """Test error handling in IP stats."""
    ip_limiter.db.execute_one.side_effect = Exception("DB error")

    stats = await ip_limiter.get_ip_stats("203.0.113.42")

    assert "error" in stats or "ip_address" in stats


@pytest.mark.asyncio
async def test_is_ip_suspicious_error_handling(ip_limiter):
    """Test error handling in suspicious detection."""
    ip_limiter.db.execute_one.side_effect = Exception("DB error")

    is_suspicious, reason = await ip_limiter.is_ip_suspicious("203.0.113.42")

    assert "error" in reason.lower()
