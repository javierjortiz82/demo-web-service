"""Unit tests for reCAPTCHA v3 verification.

Author: Odiseo Team
Created: 2025-10-31
Version: 1.0.0
"""

from unittest.mock import Mock, patch

import pytest
from demo_agent.security.captcha_handler import CaptchaHandler


@pytest.fixture
def captcha_handler():
    """Create CaptchaHandler instance."""
    return CaptchaHandler()


@pytest.mark.asyncio
async def test_verify_token_disabled(captcha_handler):
    """Test token verification when CAPTCHA is disabled."""
    captcha_handler.enabled = False

    result = await captcha_handler.verify_token("dummy_token")

    assert result["success"] is True
    assert result["score"] == 1.0
    assert result.get("disabled") is True


@pytest.mark.asyncio
async def test_verify_token_no_secret_key(captcha_handler):
    """Test token verification without secret key."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = None

    result = await captcha_handler.verify_token("dummy_token")

    assert result["success"] is False
    assert "missing-input-secret" in result.get("error_codes", [])


@pytest.mark.asyncio
async def test_verify_token_success(captcha_handler):
    """Test successful token verification."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = "secret_key"

    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "score": 0.9,
            "action": "demo_query",
            "challenge_ts": "2025-10-31T12:00:00Z",
            "hostname": "example.com",
            "error-codes": [],
        }
        mock_post.return_value = mock_response

        result = await captcha_handler.verify_token("valid_token")

        assert result["success"] is True
        assert result["score"] == 0.9
        assert result["action"] == "demo_query"


@pytest.mark.asyncio
async def test_verify_token_bot_detected(captcha_handler):
    """Test token verification detecting bot."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = "secret_key"

    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "score": 0.1,  # Low score = likely bot
            "action": "demo_query",
            "challenge_ts": "2025-10-31T12:00:00Z",
            "hostname": "example.com",
            "error-codes": [],
        }
        mock_post.return_value = mock_response

        result = await captcha_handler.verify_token("bot_token")

        assert result["success"] is True
        assert result["score"] == 0.1


@pytest.mark.asyncio
async def test_verify_token_google_error(captcha_handler):
    """Test token verification with Google API error."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = "secret_key"

    with patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection error")

        result = await captcha_handler.verify_token("token")

        assert result["success"] is False
        # Could be either network-error or internal-error depending on exception type
        assert any(
            err in result.get("error_codes", []) for err in ["network-error", "internal-error"]
        )


@pytest.mark.asyncio
async def test_verify_token_google_invalid_response(captcha_handler):
    """Test handling of invalid Google response."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = "secret_key"

    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {"success": False}
        mock_post.return_value = mock_response

        result = await captcha_handler.verify_token("token")

        assert result["success"] is False


@pytest.mark.asyncio
async def test_verify_token_with_remote_ip(captcha_handler):
    """Test token verification with client IP."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = "secret_key"

    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "score": 0.8,
            "action": "demo_query",
            "challenge_ts": "2025-10-31T12:00:00Z",
            "hostname": "example.com",
            "error-codes": [],
        }
        mock_post.return_value = mock_response

        result = await captcha_handler.verify_token("token", remote_ip="203.0.113.42")

        assert result["success"] is True
        # Verify IP was included in request
        call_args = mock_post.call_args
        assert call_args[1]["data"]["remoteip"] == "203.0.113.42"


def test_evaluate_score_low_risk(captcha_handler):
    """Test score evaluation for low-risk user."""
    evaluation = captcha_handler.evaluate_score(0.9)

    assert evaluation["risk_level"] == "low"
    assert evaluation["recommendation"] == "allow"


def test_evaluate_score_medium_risk(captcha_handler):
    """Test score evaluation for medium-risk user."""
    evaluation = captcha_handler.evaluate_score(0.5)

    assert evaluation["risk_level"] == "medium"
    assert evaluation["recommendation"] == "captcha"


def test_evaluate_score_high_risk(captcha_handler):
    """Test score evaluation for high-risk user."""
    evaluation = captcha_handler.evaluate_score(0.1)

    assert evaluation["risk_level"] == "high"
    assert evaluation["recommendation"] == "block"


def test_evaluate_score_boundary_low(captcha_handler):
    """Test score evaluation at low boundary."""
    evaluation = captcha_handler.evaluate_score(0.7)

    assert evaluation["risk_level"] == "low"


def test_evaluate_score_boundary_medium(captcha_handler):
    """Test score evaluation at medium boundary."""
    evaluation = captcha_handler.evaluate_score(0.3)

    assert evaluation["risk_level"] == "medium"


def test_evaluate_score_zero(captcha_handler):
    """Test score evaluation at zero."""
    evaluation = captcha_handler.evaluate_score(0.0)

    assert evaluation["risk_level"] == "high"
    assert evaluation["recommendation"] == "block"


def test_evaluate_score_one(captcha_handler):
    """Test score evaluation at maximum."""
    evaluation = captcha_handler.evaluate_score(1.0)

    assert evaluation["risk_level"] == "low"
    assert evaluation["recommendation"] == "allow"


@pytest.mark.asyncio
async def test_should_require_captcha_high_abuse(captcha_handler):
    """Test CAPTCHA requirement for high abuse score."""
    require, reason = await captcha_handler.should_require_captcha(abuse_score=0.9)

    assert require is True
    assert "abuse" in reason.lower()


@pytest.mark.asyncio
async def test_should_require_captcha_low_captcha_score(captcha_handler):
    """Test CAPTCHA requirement for previous low CAPTCHA score."""
    require, reason = await captcha_handler.should_require_captcha(
        abuse_score=0.4, captcha_score=0.2
    )

    assert require is True


@pytest.mark.asyncio
async def test_should_require_captcha_multiple_blocks(captcha_handler):
    """Test CAPTCHA requirement for multiple previous blocks."""
    require, reason = await captcha_handler.should_require_captcha(
        abuse_score=0.3, previous_blocks=3
    )

    assert require is True


@pytest.mark.asyncio
async def test_should_require_captcha_moderate_abuse(captcha_handler):
    """Test CAPTCHA requirement for moderate abuse score."""
    require, reason = await captcha_handler.should_require_captcha(abuse_score=0.7)

    assert require is True


@pytest.mark.asyncio
async def test_should_require_captcha_not_required(captcha_handler):
    """Test no CAPTCHA requirement for legitimate user."""
    require, reason = await captcha_handler.should_require_captcha(
        abuse_score=0.2, captcha_score=0.8, previous_blocks=0
    )

    assert require is False


@pytest.mark.asyncio
async def test_should_require_captcha_error(captcha_handler):
    """Test error handling in CAPTCHA requirement check."""
    require, reason = await captcha_handler.should_require_captcha(
        abuse_score=None,  # This will cause an error
    )

    # Should fail safe
    assert isinstance(require, bool)


def test_get_recaptcha_status_enabled(captcha_handler):
    """Test reCAPTCHA status when enabled."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = "secret_key"

    status = captcha_handler.get_recaptcha_status()

    assert status["enabled"] is True
    assert status["configured"] is True
    assert status["version"] == "v3"
    assert status["status"] == "ready"


def test_get_recaptcha_status_disabled(captcha_handler):
    """Test reCAPTCHA status when disabled."""
    captcha_handler.enabled = False

    status = captcha_handler.get_recaptcha_status()

    assert status["enabled"] is False
    assert status["status"] == "disabled"


def test_get_recaptcha_status_misconfigured(captcha_handler):
    """Test reCAPTCHA status when misconfigured."""
    captcha_handler.enabled = True
    captcha_handler.secret_key = None

    status = captcha_handler.get_recaptcha_status()

    assert status["enabled"] is True
    assert status["configured"] is False
    assert status["status"] == "misconfigured"


def test_get_recaptcha_status_threshold(captcha_handler):
    """Test reCAPTCHA status includes threshold."""
    captcha_handler.score_threshold = 0.5

    status = captcha_handler.get_recaptcha_status()

    assert status["score_threshold"] == 0.5
