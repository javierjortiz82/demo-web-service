"""Demo Agent - FAQ-based AI assistant with token-bucket rate limiting.

Implements a simple FAQ-based agent that uses Gemini API for responses,
with PostgreSQL-backed token-bucket rate limiting and security hardening.

Author: Odiseo Team
Created: 2025-10-31
Version: 2.0.0 (Simplified)
"""

from datetime import datetime, timezone
from typing import Any

from app.config.settings import settings
from app.db.connection import get_db
from app.models.responses import TokenWarning
from app.rate_limiter.token_bucket import TokenBucket
from app.security.fingerprint import FingerprintAnalyzer
from app.security.ip_limiter import IPLimiter
from app.services.gemini_client import GeminiClient
from app.services.prompt_manager import PromptManager
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DemoAgent:
    """FAQ-based AI assistant with token-bucket rate limiting."""

    def __init__(self) -> None:
        """Initialize DemoAgent with required components."""
        self.gemini_client = GeminiClient()
        self.token_bucket = TokenBucket()
        self.prompt_manager = PromptManager()
        self.db = get_db()
        self.fingerprint_analyzer = FingerprintAnalyzer()
        self.ip_limiter = IPLimiter()
        logger.info("DemoAgent initialized")

    async def process_query(
        self,
        user_input: str,
        user_key: str,
        language: str = "es",
        ip_address: str | None = None,
        user_agent: str | None = None,
        client_fingerprint: str | None = None,
        user_timezone: str | None = None,
    ) -> tuple[str | None, int, TokenWarning, str | None]:
        """Process a demo query with rate limiting and token tracking."""
        try:
            logger.info(f"Processing query for user_key={user_key}, lang={language}")

            # Step 1: Check IP rate limiting
            if settings.enable_fingerprint and ip_address:
                ip_allowed, _requests_count = await self.ip_limiter.check_rate_limit(ip_address)
                if not ip_allowed:
                    error_msg = (
                        f"Rate limit exceeded. "
                        f"Max {settings.ip_rate_limit_requests} requests/min."
                    )
                    logger.warning(f"IP rate limit exceeded: {ip_address}")
                    await self._log_audit(
                        user_key=user_key,
                        ip_address=ip_address,
                        fingerprint=client_fingerprint,
                        user_agent=user_agent,
                        request_input=user_input,
                        is_blocked=True,
                        block_reason="rate_limit_ip",
                    )
                    return (
                        None,
                        0,
                        TokenWarning(is_warning=True, message=error_msg),
                        error_msg,
                    )

            # Step 2: Analyze fingerprint and compute abuse score
            abuse_score = 0.0
            if settings.enable_fingerprint:
                if not client_fingerprint and user_agent and ip_address:
                    client_fingerprint = self.fingerprint_analyzer.generate_fingerprint(
                        user_agent=user_agent,
                        ip_address=ip_address,
                    )

                ip_stats = await self.ip_limiter.get_ip_stats(ip_address or "")
                ip_reputation = self.ip_limiter.get_reputation_score(ip_address or "", ip_stats)

                abuse_score = self.fingerprint_analyzer.compute_abuse_score(
                    user_agent=user_agent,
                    ip_address=ip_address,
                    ip_reputation=ip_reputation,
                )

                logger.debug(f"Abuse score: {round(abuse_score, 2)} for {user_key}")

                if abuse_score > settings.abuse_score_block_threshold:
                    error_msg = "Suspicious activity detected. Account blocked."
                    logger.warning(f"Critical abuse score for {user_key}: {abuse_score}")
                    await self._log_audit(
                        user_key=user_key,
                        ip_address=ip_address,
                        fingerprint=client_fingerprint,
                        user_agent=user_agent,
                        request_input=user_input,
                        is_blocked=True,
                        block_reason="suspicious_behavior",
                        abuse_score=abuse_score,
                    )
                    return (
                        None,
                        0,
                        TokenWarning(is_warning=True, message=error_msg),
                        error_msg,
                    )

            # Step 3: Check quota before processing
            can_proceed, tokens_remaining = await self.token_bucket.check_quota(
                user_key,
                tokens_needed=settings.demo_tokens_per_request,
                user_timezone=user_timezone,
            )

            if not can_proceed:
                status = await self.token_bucket.get_quota_status(user_key)
                error_msg = (
                    f"Quota exceeded. Limit: {settings.demo_max_tokens:,} tokens. "
                    f"Reset: {status['next_reset']}."
                )
                logger.warning(f"Quota exceeded for {user_key}")
                await self._log_audit(
                    user_key=user_key,
                    ip_address=ip_address,
                    fingerprint=client_fingerprint,
                    user_agent=user_agent,
                    request_input=user_input,
                    is_blocked=True,
                    block_reason="quota_exceeded",
                )
                return (
                    None,
                    0,
                    TokenWarning(is_warning=True, message=error_msg),
                    error_msg,
                )

            # Step 5: Load system prompt with FAQ context
            system_prompt = self.prompt_manager.get_demo_prompt(
                remaining_tokens=tokens_remaining,
                user_lang=language,
            )

            # Step 6: Call Gemini API
            tokens_used = 0
            try:
                logger.debug(f"Calling Gemini API for {user_key}")
                response_text, tokens_used = await self.gemini_client.generate_response(
                    system_prompt=system_prompt,
                    user_message=user_input,
                    temperature=settings.temperature,
                    max_output_tokens=settings.max_output_tokens,
                )

                # Step 7: Deduct tokens
                tokens_remaining = await self.token_bucket.deduct_tokens(
                    user_key, tokens_used=tokens_used
                )

            except Exception as api_error:
                logger.warning(f"Gemini API failed for {user_key}: {api_error}")
                if tokens_used > 0:
                    tokens_remaining = await self.token_bucket.refund_tokens(
                        user_key, tokens_to_refund=tokens_used
                    )
                    logger.info(f"Tokens refunded: {tokens_used} for {user_key}")
                raise api_error

            # Step 8: Check warning threshold
            status = await self.token_bucket.get_quota_status(user_key)
            percentage_used = status["percentage_used"]
            is_warning = percentage_used >= settings.demo_warning_threshold
            warning_msg = None

            if is_warning:
                warning_msg = f"You've consumed {percentage_used}% of your daily quota"

            warning = TokenWarning(
                is_warning=is_warning,
                message=warning_msg,
                percentage_used=percentage_used,
            )

            # Step 9: Log audit
            await self._log_audit(
                user_key=user_key,
                ip_address=ip_address,
                fingerprint=client_fingerprint,
                user_agent=user_agent,
                request_input=user_input,
                response_length=len(response_text),
                tokens_used=tokens_used,
                is_blocked=False,
                abuse_score=abuse_score,
            )

            logger.info(
                f"Query processed: user={user_key}, tokens={tokens_used}, "
                f"remaining={tokens_remaining}, warning={is_warning}"
            )

            return response_text, tokens_used, warning, None

        except Exception:
            logger.exception(f"Error processing query for {user_key}")
            await self._log_audit(
                user_key=user_key,
                ip_address=ip_address,
                fingerprint=client_fingerprint,
                user_agent=user_agent,
                request_input=user_input,
                is_blocked=True,
                block_reason="internal_error",
            )
            error_msg = "Error processing request. Please try again later."
            return None, 0, TokenWarning(is_warning=True, message=error_msg), error_msg

    async def _log_audit(
        self,
        user_key: str | None,
        ip_address: str | None,
        fingerprint: str | None,
        user_agent: str | None,
        request_input: str | None,
        response_length: int = 0,
        tokens_used: int = 0,
        is_blocked: bool = False,
        block_reason: str | None = None,
        abuse_score: float = 0.0,
    ) -> None:
        """Log request to audit trail."""
        try:
            query = """
                INSERT INTO :SCHEMA_NAME.demo_audit_log
                (user_key, ip_address, client_fingerprint, request_input,
                 response_length, tokens_used, is_blocked, block_reason,
                 action_taken, user_agent, abuse_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            truncated_input = request_input[:1000] if request_input else None
            action = "blocked" if is_blocked else "allowed"

            await self.db.execute(
                query,
                (
                    user_key,
                    ip_address,
                    fingerprint,
                    truncated_input,
                    response_length,
                    tokens_used,
                    is_blocked,
                    block_reason,
                    action,
                    user_agent,
                    abuse_score,
                ),
            )
        except Exception:
            logger.error(f"Failed to log audit for {user_key}")

    async def get_user_status(self, user_key: str) -> dict[str, Any]:
        """Get user's current quota status."""
        try:
            status = await self.token_bucket.get_quota_status(user_key)
            logger.debug(f"Status for {user_key}: {status.get('percentage_used', 0)}%")
            return status
        except Exception:
            logger.exception(f"Error getting status for {user_key}")
            return {
                "tokens_used": 0,
                "tokens_remaining": settings.demo_max_tokens,
                "percentage_used": 0,
                "requests_count": 0,
                "is_blocked": False,
                "blocked_until": None,
                "last_reset": datetime.now(timezone.utc).isoformat(),
                "next_reset": datetime.now(timezone.utc).isoformat(),
            }
