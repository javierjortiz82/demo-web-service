"""Gemini API wrapper for demo agent using Google Gen AI SDK.

Handles all communication with Google Gemini 2.5 via the new Google Gen AI SDK
as required by REQ-1. Includes accurate token counting.

Supports authentication via:
1. Service Account JSON file (GOOGLE_APPLICATION_CREDENTIALS)
2. Application Default Credentials (ADC) as fallback

Concurrency:
- Uses asyncio.run_in_executor() to run blocking SDK calls in ThreadPool
- Prevents blocking the event loop during API calls
- Allows multiple concurrent users per worker

Author: Odiseo Team
Created: 2025-10-31
Updated: 2025-11-30
Version: 3.1.0 (Added concurrency support with run_in_executor)
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
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

    Concurrency:
    - Uses ThreadPoolExecutor for blocking SDK calls
    - run_in_executor prevents blocking the asyncio event loop
    - Multiple users can be served concurrently per worker

    Supports authentication via:
    - Service Account JSON file (recommended for production)
    - Application Default Credentials (ADC) as fallback

    Attributes:
        client: Google Gen AI Client instance
        model_name: Model to use (e.g., gemini-2.5-flash)
        _executor: ThreadPoolExecutor for blocking calls
    """

    # Shared ThreadPoolExecutor for all instances (per worker process)
    # Size configured via MAX_CONCURRENT_REQUESTS environment variable
    _executor: ThreadPoolExecutor | None = None
    _max_workers: int = 0

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

        # Initialize shared ThreadPoolExecutor (once per worker)
        # Size is configurable via MAX_CONCURRENT_REQUESTS env var
        max_workers = settings.max_concurrent_requests
        if GeminiClient._executor is None:
            GeminiClient._executor = ThreadPoolExecutor(
                max_workers=max_workers, thread_name_prefix="gemini_api_"
            )
            GeminiClient._max_workers = max_workers
            logger.info(
                f"ThreadPoolExecutor initialized for Gemini API calls "
                f"(max_workers={max_workers}, configurable via MAX_CONCURRENT_REQUESTS)"
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

    def _sync_count_tokens(self, contents: str) -> int:
        """Synchronous token counting (runs in thread pool).

        Args:
            contents: Text to count tokens for.

        Returns:
            Token count or 0 on error.
        """
        try:
            response = self.client.models.count_tokens(
                model=self.model_name,
                contents=contents,
            )
            return response.total_tokens or 0
        except Exception as e:
            logger.warning(f"Failed to count tokens: {e}")
            return len(contents.split())

    def _sync_generate_content(
        self,
        user_message: str,
        config: GenerateContentConfig,
    ) -> str:
        """Synchronous content generation (runs in thread pool).

        Args:
            user_message: User query.
            config: Generation configuration.

        Returns:
            Generated response text.

        Raises:
            RuntimeError: If response is empty.
        """
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_message,
            config=config,
        )

        response_text = response.text if response.text else ""
        if not response_text:
            raise RuntimeError("Empty response from Gemini API")

        return response_text

    async def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> tuple[str, int]:
        """Generate response using Gemini API via Google Gen AI SDK.

        Uses run_in_executor to prevent blocking the event loop during
        synchronous SDK calls. This allows multiple concurrent requests.

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
            # FIX: Use get_running_loop() instead of deprecated get_event_loop()
            loop = asyncio.get_running_loop()
            temp = temperature if temperature is not None else settings.temperature
            max_tokens = max_output_tokens or settings.max_output_tokens

            # Build generation config
            config = GenerateContentConfig(
                temperature=temp,
                max_output_tokens=max_tokens,
                system_instruction=system_prompt,
            )

            # Count input tokens (non-blocking)
            logger.debug(f"Counting input tokens for {self.model_name}...")
            input_tokens = await loop.run_in_executor(
                self._executor,
                partial(self._sync_count_tokens, user_message),
            )
            logger.debug(f"Input tokens: {input_tokens}")

            # Call Gemini API (non-blocking) - this is the main blocking call
            logger.debug(f"Calling Gemini API ({self.model_name})...")
            response_text = await loop.run_in_executor(
                self._executor,
                partial(self._sync_generate_content, user_message, config),
            )

            # Count output tokens (non-blocking)
            logger.debug(f"Counting output tokens for {self.model_name}...")
            output_tokens = await loop.run_in_executor(
                self._executor,
                partial(self._sync_count_tokens, response_text),
            )
            logger.debug(f"Output tokens: {output_tokens}")

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

        Uses run_in_executor to prevent blocking the event loop.

        Args:
            system_prompt: System instruction.
            user_message: User query.

        Returns:
            Accurate total token count.
        """
        try:
            # FIX: Use get_running_loop() instead of deprecated get_event_loop()
            loop = asyncio.get_running_loop()
            logger.debug(f"Counting tokens for {self.model_name}...")

            # Count both in parallel using executor (non-blocking)
            prompt_tokens, message_tokens = await asyncio.gather(
                loop.run_in_executor(
                    self._executor,
                    partial(self._sync_count_tokens, system_prompt),
                ),
                loop.run_in_executor(
                    self._executor,
                    partial(self._sync_count_tokens, user_message),
                ),
            )

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

    @classmethod
    def shutdown_executor(cls) -> None:
        """Shutdown the ThreadPoolExecutor on application exit.

        CRITICAL: Must be called during app shutdown to prevent resource leaks.
        Threads in the executor will continue running until properly shutdown.
        """
        if cls._executor is not None:
            logger.info("Shutting down Gemini ThreadPoolExecutor...")
            cls._executor.shutdown(wait=True, cancel_futures=False)
            cls._executor = None
            logger.info("ThreadPoolExecutor shutdown complete")
