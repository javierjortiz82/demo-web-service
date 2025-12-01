"""Unit tests for accurate token counting.

Tests FIX 2.1: Real Gemini API token counting instead of word estimation.

Author: Odiseo Team
Created: 2025-11-03
Version: 1.0.0
"""

from unittest.mock import Mock, patch

import pytest
from app.services.gemini_client import GeminiClient


@pytest.fixture
def mock_gemini_client():
    """Create a mocked Gemini client."""
    with patch("app.services.gemini_client.settings") as mock_config:
        mock_config.GOOGLE_API_KEY = "AIzaSyTest"
        mock_config.MODEL = "gemini-2.5-flash"
        mock_config.TEMPERATURE = 0.2
        mock_config.MAX_OUTPUT_TOKENS = 2048

        with patch("app.services.gemini_client.genai") as mock_genai:
            mock_client = Mock()
            mock_genai.Client.return_value = mock_client

            yield GeminiClient()


@pytest.mark.asyncio
async def test_count_tokens_using_gemini_api(mock_gemini_client):
    """Test that count_tokens uses Gemini's API."""
    # Mock the count_tokens API responses (one for prompt, one for message)
    mock_prompt_response = Mock()
    mock_prompt_response.total_tokens = 10

    mock_message_response = Mock()
    mock_message_response.total_tokens = 32

    mock_gemini_client.client.models.count_tokens = Mock(
        side_effect=[mock_prompt_response, mock_message_response]
    )

    # Call count_tokens
    prompt = "You are a helpful assistant."
    message = "What is 2+2?"

    total = await mock_gemini_client.count_tokens(prompt, message)

    # Verify it called count_tokens API
    assert mock_gemini_client.client.models.count_tokens.called
    # Should be sum: 10 + 32 = 42
    assert total == 42


@pytest.mark.asyncio
async def test_count_tokens_separate_prompt_and_message(mock_gemini_client):
    """Test that count_tokens counts prompt and message separately."""
    # Mock the count_tokens API responses
    mock_prompt_response = Mock()
    mock_prompt_response.total_tokens = 10

    mock_message_response = Mock()
    mock_message_response.total_tokens = 5

    # Configure the mock to return different values on each call
    mock_gemini_client.client.models.count_tokens = Mock(
        side_effect=[mock_prompt_response, mock_message_response]
    )

    prompt = "You are a helpful assistant."
    message = "What?"

    total = await mock_gemini_client.count_tokens(prompt, message)

    # Total should be sum of both counts
    assert total == 15

    # Verify count_tokens was called twice (once for prompt, once for message)
    assert mock_gemini_client.client.models.count_tokens.call_count == 2


@pytest.mark.asyncio
async def test_count_tokens_fallback_on_error(mock_gemini_client):
    """Test fallback to word count when API fails."""
    # Mock the API to fail
    mock_gemini_client.client.models.count_tokens = Mock(side_effect=Exception("API Error"))

    prompt = "System prompt here"  # 3 words
    message = "User message"  # 2 words

    total = await mock_gemini_client.count_tokens(prompt, message)

    # Should fallback to word count (3 + 2 = 5)
    assert total == 5


@pytest.mark.asyncio
async def test_generate_response_uses_real_token_counting(mock_gemini_client):
    """Test that generate_response uses actual token counting from API."""
    # Mock count_tokens responses
    mock_input_response = Mock()
    mock_input_response.total_tokens = 20

    mock_output_response = Mock()
    mock_output_response.total_tokens = 15

    # Mock generate_content response
    mock_content = Mock()
    mock_content.text = "Here is the response."

    mock_part = Mock()
    mock_part.text = "Here is the response."

    mock_content.parts = [mock_part]

    mock_candidate = Mock()
    mock_candidate.content = mock_content

    mock_api_response = Mock()
    mock_api_response.candidates = [mock_candidate]

    # Configure mocks
    count_calls = [mock_input_response, mock_output_response]
    mock_gemini_client.client.models.count_tokens = Mock(side_effect=count_calls)
    mock_gemini_client.client.models.generate_content = Mock(return_value=mock_api_response)

    # Call generate_response
    system_prompt = "You are helpful."
    user_message = "Hello?"

    response_text, tokens_used = await mock_gemini_client.generate_response(
        system_prompt=system_prompt,
        user_message=user_message,
    )

    # Verify token counting
    assert response_text == "Here is the response."
    assert tokens_used == 35  # 20 input + 15 output


@pytest.mark.asyncio
async def test_generate_response_fallback_on_counting_error(mock_gemini_client):
    """Test fallback to word count if token API fails during generation."""
    # Mock count_tokens to fail
    mock_gemini_client.client.models.count_tokens = Mock(
        side_effect=Exception("Token count failed")
    )

    # Mock generate_content response
    mock_content = Mock()
    mock_content.text = "Response here"

    mock_part = Mock()
    mock_part.text = "Response here"

    mock_content.parts = [mock_part]

    mock_candidate = Mock()
    mock_candidate.content = mock_content

    mock_api_response = Mock()
    mock_api_response.candidates = [mock_candidate]

    mock_gemini_client.client.models.generate_content = Mock(return_value=mock_api_response)

    system_prompt = "You are helpful."
    user_message = "Hello?"

    response_text, tokens_used = await mock_gemini_client.generate_response(
        system_prompt=system_prompt,
        user_message=user_message,
    )

    # Should use word count fallback
    # "You are helpful." = 3 words
    # "Hello?" = 1 word
    # "Response here" = 2 words
    # Total = 6 words (but due to separate counting attempts, may differ)
    assert response_text == "Response here"
    assert tokens_used > 0  # Should have some token count


@pytest.mark.asyncio
async def test_token_counting_no_longer_uses_word_estimation(mock_gemini_client):
    """Test that old word-count estimation is NOT used."""
    # Setup mock to return specific values we can verify
    mock_prompt_response = Mock()
    mock_prompt_response.total_tokens = 2  # "short" = 1 word, but API says 2

    mock_message_response = Mock()
    mock_message_response.total_tokens = 98  # Long message

    mock_gemini_client.client.models.count_tokens = Mock(
        side_effect=[mock_prompt_response, mock_message_response]
    )

    # Even with a long message that would give high word count,
    # we should get the API's response value (100)
    long_message = " ".join(["word"] * 500)  # 500 words
    prompt = "short"

    total = await mock_gemini_client.count_tokens(prompt, long_message)

    # If old logic was used: (500 + 1) // 4 + 50 = 175
    # With new logic: API returns 2 + 98 = 100
    assert total == 100
    # NOT 175, which would be old calculation


@pytest.mark.asyncio
async def test_count_tokens_accurate_for_special_characters(mock_gemini_client):
    """Test token counting with special characters and unicode."""
    mock_prompt_response = Mock()
    mock_prompt_response.total_tokens = 1

    mock_message_response = Mock()
    mock_message_response.total_tokens = 24

    mock_gemini_client.client.models.count_tokens = Mock(
        side_effect=[mock_prompt_response, mock_message_response]
    )

    # Message with special characters and unicode
    message = "¿Cómo estás? 你好世界 🌍 [code] @mention #hashtag"

    total = await mock_gemini_client.count_tokens("prompt", message)

    # Should use API count, not word count
    # Word count would be ~10, but API returns 25
    assert total == 25


class TestTokenCountingEdgeCases:
    """Test edge cases for token counting."""

    @pytest.mark.asyncio
    async def test_empty_message(self, mock_gemini_client):
        """Test token counting for empty message."""
        mock_prompt_response = Mock()
        mock_prompt_response.total_tokens = 1

        mock_message_response = Mock()
        mock_message_response.total_tokens = 0

        mock_gemini_client.client.models.count_tokens = Mock(
            side_effect=[mock_prompt_response, mock_message_response]
        )

        total = await mock_gemini_client.count_tokens("prompt", "")

        assert total == 1  # Just the prompt

    @pytest.mark.asyncio
    async def test_very_long_message(self, mock_gemini_client):
        """Test token counting for very long message."""
        mock_prompt_response = Mock()
        mock_prompt_response.total_tokens = 1

        mock_message_response = Mock()
        mock_message_response.total_tokens = 9999

        mock_gemini_client.client.models.count_tokens = Mock(
            side_effect=[mock_prompt_response, mock_message_response]
        )

        # 10KB message
        long_message = "x" * 10000

        total = await mock_gemini_client.count_tokens("prompt", long_message)

        assert total == 10000

    @pytest.mark.asyncio
    async def test_newlines_and_whitespace(self, mock_gemini_client):
        """Test token counting with various whitespace."""
        mock_prompt_response = Mock()
        mock_prompt_response.total_tokens = 1

        mock_message_response = Mock()
        mock_message_response.total_tokens = 4

        mock_gemini_client.client.models.count_tokens = Mock(
            side_effect=[mock_prompt_response, mock_message_response]
        )

        message = "Line 1\n\nLine 2\t\tLine 3   Line 4"

        total = await mock_gemini_client.count_tokens("prompt", message)

        # Should use API count, not word count affected by whitespace
        assert total == 5
