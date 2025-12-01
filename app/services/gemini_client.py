"""Gemini API wrapper for demo agent using Google Gen AI SDK.

Handles all communication with Google Gemini 2.5 via the new Google Gen AI SDK
as required by REQ-1. Includes accurate token counting.

Supports authentication via:
1. Service Account JSON file (GOOGLE_APPLICATION_CREDENTIALS)
2. Application Default Credentials (ADC) as fallback

Author: Odiseo Team
Created: 2025-10-31
Updated: 2025-11-29
Version: 3.0.0 (Migrated to google-genai SDK)
"""

from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig

from app.config.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API via Google Gen AI SDK.

    Uses the new Google Gen AI SDK (replacing deprecated vertexai.generative_models).
    Handles API calls, token counting, and error handling.

    Supports authentication via:
    - Service Account JSON file (recommended for production)
    - Application Default Credentials (ADC) as fallback

    Attributes:
        client: Google Gen AI Client instance
        model_name: Model to use (e.g., gemini-2.5-flash)
    """

    def __init__(self) -> None:
        """Initialize Gemini client via Google Gen AI SDK.

        Authentication priority:
        1. Service Account JSON file (GOOGLE_APPLICATION_CREDENTIALS)
        2. Application Default Credentials (ADC) as fallback

        Raises:
            ValueError: If GCP_PROJECT_ID is not configured.
            FileNotFoundError: If service account file doesn't exist.
            RuntimeError: If client cannot be initialized.
        """
        if not settings.gcp_project_id:
            raise ValueError(
                "GCP_PROJECT_ID is required for Vertex AI. "
                "Set GCP_PROJECT_ID in your environment."
            )

        # Validate credentials file if configured
        self._validate_credentials()

        # Initialize Google Gen AI Client with Vertex AI backend
        try:
            self.client = genai.Client(
                vertexai=True,
                project=settings.gcp_project_id,
                location=settings.gcp_location,
            )
            self.model_name = settings.model

            auth_method = "service account" if settings.google_application_credentials else "ADC"
            logger.info(
                f"Gemini client initialized via Google Gen AI SDK "
                f"(project: {settings.gcp_project_id}, "
                f"location: {settings.gcp_location}, "
                f"model: {self.model_name}, "
                f"auth: {auth_method})"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Google Gen AI client: {e}") from e

    def _validate_credentials(self) -> None:
        """Validate Google Cloud credentials file exists if configured.

        Raises:
            FileNotFoundError: If configured service account file doesn't exist.
            ValueError: If path is not a file.
        """
        credentials_path = settings.google_application_credentials

        if not credentials_path:
            logger.info(
                "No GOOGLE_APPLICATION_CREDENTIALS configured, "
                "using Application Default Credentials (ADC)"
            )
            return

        path = Path(credentials_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Service account file not found: {credentials_path}. "
                f"Please provide a valid path to GOOGLE_APPLICATION_CREDENTIALS."
            )

        if not path.is_file():
            raise ValueError(f"GOOGLE_APPLICATION_CREDENTIALS is not a file: {credentials_path}")

        logger.info(f"Using service account credentials from: {credentials_path}")

    async def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> tuple[str, int]:
        """Generate response using Gemini API via Google Gen AI SDK.

        Args:
            system_prompt: System instruction for the model.
            user_message: User query/message.
            temperature: Model temperature (optional, uses config default).
            max_output_tokens: Max tokens to generate (optional, uses config default).

        Returns:
            Tuple of (response_text, tokens_used).

        Raises:
            RuntimeError: If API call fails.
        """
        try:
            temp = temperature if temperature is not None else settings.temperature
            max_tokens = max_output_tokens or settings.max_output_tokens

            # Build generation config
            config = GenerateContentConfig(
                temperature=temp,
                max_output_tokens=max_tokens,
                system_instruction=system_prompt,
            )

            # Count input tokens
            logger.debug(f"Counting input tokens for {self.model_name}...")
            input_tokens: int = 0
            try:
                token_count_response = self.client.models.count_tokens(
                    model=self.model_name,
                    contents=user_message,
                )
                input_tokens = token_count_response.total_tokens or 0
                logger.debug(f"Input tokens: {input_tokens}")
            except Exception as e:
                logger.warning(f"Failed to count input tokens: {e}. Using fallback.")
                input_tokens = len(user_message.split())

            # Call Gemini API
            logger.debug(f"Calling Gemini API ({self.model_name})...")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_message,
                config=config,
            )

            # Extract response text
            response_text = ""
            if response.text:
                response_text = response.text

            if not response_text:
                raise RuntimeError("Empty response from Gemini API")

            # Count output tokens
            logger.debug(f"Counting output tokens for {self.model_name}...")
            output_tokens: int = 0
            try:
                output_count_response = self.client.models.count_tokens(
                    model=self.model_name,
                    contents=response_text,
                )
                output_tokens = output_count_response.total_tokens or 0
                logger.debug(f"Output tokens: {output_tokens}")
            except Exception as e:
                logger.warning(f"Failed to count output tokens: {e}. Using fallback.")
                output_tokens = len(response_text.split())

            total_tokens = input_tokens + output_tokens

            logger.info(
                f"Gemini response generated "
                f"(input={input_tokens}, output={output_tokens}, "
                f"total={total_tokens} tokens, {len(response_text)} chars)"
            )

            return response_text, total_tokens

        except Exception as e:
            logger.exception(f"Error calling Gemini API: {e}")
            raise RuntimeError(f"Gemini API call failed: {e}") from e

    async def count_tokens(
        self,
        system_prompt: str,
        user_message: str,
    ) -> int:
        """Count tokens for a request using Google Gen AI SDK.

        Args:
            system_prompt: System instruction.
            user_message: User query.

        Returns:
            Accurate total token count.
        """
        try:
            logger.debug(f"Counting tokens for {self.model_name}...")

            # Count system prompt tokens
            prompt_tokens: int = 0
            try:
                prompt_response = self.client.models.count_tokens(
                    model=self.model_name,
                    contents=system_prompt,
                )
                prompt_tokens = prompt_response.total_tokens or 0
            except Exception as e:
                logger.warning(f"Failed to count system prompt tokens: {e}")
                prompt_tokens = len(system_prompt.split())

            # Count user message tokens
            message_tokens: int = 0
            try:
                message_response = self.client.models.count_tokens(
                    model=self.model_name,
                    contents=user_message,
                )
                message_tokens = message_response.total_tokens or 0
            except Exception as e:
                logger.warning(f"Failed to count user message tokens: {e}")
                message_tokens = len(user_message.split())

            total_tokens = prompt_tokens + message_tokens
            logger.debug(
                f"Token count: prompt={prompt_tokens}, message={message_tokens}, "
                f"total={total_tokens}"
            )

            return total_tokens

        except Exception as e:
            logger.exception(f"Error counting tokens: {e}")
            # Fallback: word count estimation
            fallback_count = len(system_prompt.split()) + len(user_message.split())
            logger.warning(f"Using fallback token count: {fallback_count}")
            return fallback_count
