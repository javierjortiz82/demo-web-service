"""Tests for IP limiter with async database operations.

Tests OPTION 4: Validation of completed async IP limiter module.

Tests the following async operations:
- check_rate_limit: async IP rate limit checking
- get_ip_stats: async IP statistics retrieval
- is_ip_suspicious: async suspicious pattern detection
- get_reputation_score: reputation calculation (sync)

Author: Odiseo Team
Created: 2025-11-03
Version: 1.0.0
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from app.security.ip_limiter import IPLimiter

# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def mock_db():
    """Create mock async database."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.execute_one = AsyncMock()
    db.fetch = AsyncMock()
    return db


@pytest_asyncio.fixture
async def ip_limiter(mock_db):
    """Create IPLimiter with mocked database."""
    limiter = IPLimiter(max_requests_per_minute=100)
    limiter.db = mock_db
    return limiter


# ============================================================================
# check_rate_limit Async Tests
# ============================================================================


@pytest.mark.asyncio
async def test_check_rate_limit_allows_request(ip_limiter, mock_db):
    """Test async rate limit check allows normal request."""
    ip_address = "203.0.113.42"

    # Mock database response
    mock_db.execute_one.return_value = {"request_count": 10}

    allowed, count = await ip_limiter.check_rate_limit(ip_address)

    assert allowed is True
    assert count == 10
    # Verify async call was made
    assert mock_db.execute_one.called


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_exceeding_limit(ip_limiter, mock_db):
    """Test async rate limit check blocks when limit exceeded."""
    ip_address = "203.0.113.42"

    # Mock database response with excessive requests
    mock_db.execute_one.return_value = {"request_count": 150}

    allowed, count = await ip_limiter.check_rate_limit(ip_address)

    assert allowed is False
    assert count == 150


@pytest.mark.asyncio
async def test_check_rate_limit_handles_no_result(ip_limiter, mock_db):
    """Test async rate limit check handles missing data."""
    ip_address = "203.0.113.42"

    # Mock database response with None
    mock_db.execute_one.return_value = None

    allowed, count = await ip_limiter.check_rate_limit(ip_address)

    assert allowed is True
    assert count == 0


# ============================================================================
# get_ip_stats Async Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_ip_stats_returns_complete_data(ip_limiter, mock_db):
    """Test async IP stats retrieval returns all fields."""
    ip_address = "203.0.113.42"
    now = datetime.now(timezone.utc)

    # Mock multiple database responses
    mock_responses = [
        {"total_requests": 500},  # Total requests
        {"requests_today": 50},  # Today's requests
        {"requests_per_minute": 5},  # Current rate
        {"unique_users": 3},  # Unique users
        {"avg_abuse_score": 0.3, "max_abuse_score": 0.8},  # Abuse scores
        {"first_seen": now - timedelta(days=7), "last_seen": now},  # Timeline
    ]
    mock_db.execute_one.side_effect = mock_responses

    stats = await ip_limiter.get_ip_stats(ip_address)

    assert stats["ip_address"] == ip_address
    assert stats["total_requests"] == 500
    assert stats["requests_today"] == 50
    assert stats["requests_per_minute"] == 5
    assert stats["unique_users"] == 3
    assert stats["abuse_score_avg"] == 0.3
    assert stats["abuse_score_max"] == 0.8
    assert "first_seen" in stats
    assert "last_seen" in stats
    # Verify 6 async database calls were made
    assert mock_db.execute_one.call_count == 6


@pytest.mark.asyncio
async def test_get_ip_stats_handles_missing_values(ip_limiter, mock_db):
    """Test async IP stats handles None values."""
    ip_address = "203.0.113.42"

    # All None responses
    mock_db.execute_one.return_value = None

    stats = await ip_limiter.get_ip_stats(ip_address)

    assert stats["total_requests"] == 0
    assert stats["requests_today"] == 0
    assert stats["abuse_score_avg"] == 0.0
    assert stats["first_seen"] is None
    assert stats["last_seen"] is None


@pytest.mark.asyncio
async def test_get_ip_stats_handles_db_error(ip_limiter, mock_db):
    """Test async IP stats handles database errors gracefully."""
    ip_address = "203.0.113.42"

    # Mock database error
    mock_db.execute_one.side_effect = Exception("DB connection error")

    stats = await ip_limiter.get_ip_stats(ip_address)

    assert stats["ip_address"] == ip_address
    assert "error" in stats
    assert "DB connection error" in stats["error"]


# ============================================================================
# is_ip_suspicious Async Tests
# ============================================================================


@pytest.mark.asyncio
async def test_is_ip_suspicious_detects_high_rate(ip_limiter, mock_db):
    """Test async suspicion detection catches high request rate."""
    ip_address = "203.0.113.42"

    # Mock stats with high request rate
    mock_db.execute_one.side_effect = [
        {"total_requests": 100},  # Total
        {"requests_today": 50},  # Today
        {"requests_per_minute": 10},  # HIGH RATE
        {"unique_users": 2},
        {"avg_abuse_score": 0.2, "max_abuse_score": 0.3},
        {"first_seen": None, "last_seen": None},
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious(ip_address)

    assert is_suspicious is True
    assert "request rate" in reason.lower()


@pytest.mark.asyncio
async def test_is_ip_suspicious_detects_high_abuse_score(ip_limiter, mock_db):
    """Test async suspicion detection catches high abuse score."""
    ip_address = "203.0.113.42"

    # Mock stats with high abuse score
    mock_db.execute_one.side_effect = [
        {"total_requests": 100},
        {"requests_today": 50},
        {"requests_per_minute": 2},  # Normal rate
        {"unique_users": 2},
        {"avg_abuse_score": 0.8, "max_abuse_score": 0.9},  # HIGH ABUSE
        {"first_seen": None, "last_seen": None},
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious(ip_address)

    assert is_suspicious is True
    assert "abuse score" in reason.lower()


@pytest.mark.asyncio
async def test_is_ip_suspicious_detects_multiple_users(ip_limiter, mock_db):
    """Test async suspicion detection catches requests from many users."""
    ip_address = "203.0.113.42"

    # Mock stats with many unique users (potential account takeover)
    # is_ip_suspicious calls get_ip_stats (6 queries) + 1 blocked_count query
    mock_db.execute_one.side_effect = [
        {"total_requests": 500},
        {"requests_today": 100},
        {"requests_per_minute": 2},  # Normal rate
        {"unique_users": 20},  # MANY USERS
        {"avg_abuse_score": 0.3, "max_abuse_score": 0.4},
        {"first_seen": None, "last_seen": None},
        {"blocked_count": 0},  # Additional call for blocked requests
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious(ip_address)

    assert is_suspicious is True
    assert "different users" in reason.lower()


@pytest.mark.asyncio
async def test_is_ip_suspicious_allows_legitimate_ip(ip_limiter, mock_db):
    """Test async suspicion detection allows legitimate IPs."""
    ip_address = "203.0.113.42"

    # Mock stats of legitimate user
    # is_ip_suspicious calls get_ip_stats (6 queries) + 1 blocked_count query
    mock_db.execute_one.side_effect = [
        {"total_requests": 50},
        {"requests_today": 10},
        {"requests_per_minute": 1},  # Normal rate
        {"unique_users": 1},
        {"avg_abuse_score": 0.1, "max_abuse_score": 0.2},  # Low abuse
        {"first_seen": None, "last_seen": None},
        {"blocked_count": 0},  # Additional call for blocked requests
    ]

    is_suspicious, reason = await ip_limiter.is_ip_suspicious(ip_address)

    assert is_suspicious is False
    assert "no suspicious patterns" in reason.lower()


# ============================================================================
# Async Pattern Validation
# ============================================================================


@pytest.mark.asyncio
async def test_check_rate_limit_is_coroutine(ip_limiter):
    """Validate check_rate_limit is properly async."""
    ip_address = "203.0.113.42"

    # Should return coroutine
    coro = ip_limiter.check_rate_limit(ip_address)
    assert asyncio.iscoroutine(coro)

    # Clean up
    try:
        await asyncio.wait_for(coro, timeout=0.1)
    except (asyncio.TimeoutError, Exception):
        pass


@pytest.mark.asyncio
async def test_get_ip_stats_is_coroutine(ip_limiter):
    """Validate get_ip_stats is properly async."""
    ip_address = "203.0.113.42"

    # Should return coroutine
    coro = ip_limiter.get_ip_stats(ip_address)
    assert asyncio.iscoroutine(coro)

    # Clean up
    try:
        await asyncio.wait_for(coro, timeout=0.1)
    except (asyncio.TimeoutError, Exception):
        pass


@pytest.mark.asyncio
async def test_is_ip_suspicious_is_coroutine(ip_limiter):
    """Validate is_ip_suspicious is properly async."""
    ip_address = "203.0.113.42"

    # Should return coroutine
    coro = ip_limiter.is_ip_suspicious(ip_address)
    assert asyncio.iscoroutine(coro)

    # Clean up
    try:
        await asyncio.wait_for(coro, timeout=0.1)
    except (asyncio.TimeoutError, Exception):
        pass


# ============================================================================
# Concurrent Operations Tests
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_rate_limit_checks(ip_limiter, mock_db):
    """Test concurrent rate limit checks."""
    mock_db.execute_one.return_value = {"request_count": 10}

    # Execute 10 concurrent checks for different IPs
    tasks = [ip_limiter.check_rate_limit(f"203.0.113.{40+i}") for i in range(10)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 10
    assert all(r[0] is True for r in results)  # All allowed


@pytest.mark.asyncio
async def test_concurrent_ip_stats_retrieval(ip_limiter, mock_db):
    """Test concurrent IP stats retrieval."""
    # Mock multiple calls
    mock_db.execute_one.return_value = {"count": 100}

    # Execute 5 concurrent stats calls
    tasks = [ip_limiter.get_ip_stats(f"203.0.113.{40+i}") for i in range(5)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    assert all("ip_address" in r for r in results)


# ============================================================================
# Reputation Score Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_reputation_score_for_clean_ip(ip_limiter):
    """Test reputation score for clean IP."""
    ip_address = "203.0.113.42"
    stats = {
        "requests_per_minute": 2,
        "abuse_score_avg": 0.1,
        "requests_today": 10,
        "total_requests": 100,
        "unique_users": 1,
    }

    score = ip_limiter.get_reputation_score(ip_address, stats)

    assert 0.0 <= score <= 1.0
    assert score < 0.3  # Should be low for clean IP


@pytest.mark.asyncio
async def test_get_reputation_score_for_suspicious_ip(ip_limiter):
    """Test reputation score for suspicious IP."""
    ip_address = "203.0.113.42"
    stats = {
        "requests_per_minute": 150,  # Exceeds 100 limit
        "abuse_score_avg": 0.8,
        "requests_today": 200,
        "total_requests": 300,
        "unique_users": 15,
    }

    score = ip_limiter.get_reputation_score(ip_address, stats)

    assert 0.0 <= score <= 1.0
    assert score > 0.5  # Should be high for suspicious IP


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
