"""Token bucket implementation for demo rate limiting.

Implements token-bucket algorithm using PostgreSQL for persistence.
Used to track and limit tokens per user per day.

FIX 3.2: Async database operations
- All db calls converted to async/await
- Non-blocking database I/O
- Part of PHASE 3 async migration

Author: Odiseo Team
Created: 2025-10-31
Version: 1.1.0 (Async)
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.settings import settings
from app.db.connection import get_db
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TokenBucket:
    """Token bucket for demo quota management.

    Implements token-bucket algorithm with PostgreSQL persistence:
    - Tracks tokens consumed per user per day
    - Auto-resets at UTC midnight
    - Blocks user for DEMO_COOLDOWN_HOURS after quota exhaustion
    - Prevents race conditions via atomic PostgreSQL UPDATE

    Implementation Details:
    - Uses demo_usage table for state persistence
    - Atomic PostgreSQL UPDATE for race-condition safety
    - Auto-cleanup of stale records (90+ days old)
    - Metrics: tokens_consumed, requests_count, is_blocked, blocked_until

    Example:
        >>> bucket = TokenBucket()
        >>> can_proceed, remaining = await bucket.check_quota("user_123", tokens_needed=250)
        >>> if can_proceed:
        ...     response = await call_gemini()
        ...     remaining = await bucket.deduct_tokens("user_123", tokens_used=response_tokens)
    """

    def __init__(self) -> None:
        """Initialize token bucket with database connection."""
        self.db = get_db()
        self.max_tokens = settings.demo_max_tokens
        self.cooldown_hours = settings.demo_cooldown_hours
        logger.info(f"TokenBucket initialized: max_tokens={self.max_tokens}")

    async def check_quota(
        self, user_key: str, tokens_needed: int = 1, user_timezone: str | None = None
    ) -> tuple[bool, int]:
        """Check if user has sufficient quota.

        Args:
            user_key: User identifier (user_id | session_id | fingerprint)
            tokens_needed: Tokens required for this request
            user_timezone: IANA timezone identifier (e.g., 'America/Costa_Rica')

        Returns:
            Tuple[bool, int]: (can_proceed, tokens_remaining)
            - can_proceed: True if user has quota and not blocked
            - tokens_remaining: Tokens left after this request

        Logic:
        1. Query demo_usage by user_key
        2. If not exists: create new record with full quota and user timezone
        3. If exists: check needs_reset() and auto-reset if needed
        4. Check is_blocked and if block has expired
        5. Calculate remaining tokens after tokens_needed
        """
        try:
            logger.debug(f"Checking quota: user_key={user_key}, tokens_needed={tokens_needed}")

            # Query user's current quota state
            query = """
                SELECT id, user_key, tokens_consumed, requests_count,
                       last_reset, is_blocked, blocked_until, user_timezone
                FROM :SCHEMA_NAME.demo_usage
                WHERE user_key = %s
            """
            result = await self.db.execute_one(query, (user_key,))

            # Get current UTC time for all operations
            now = datetime.now(timezone.utc)

            # Create new record if user not seen before
            if not result:
                # Use provided timezone or default to UTC
                tz = user_timezone or "UTC"
                insert_query = """
                    INSERT INTO :SCHEMA_NAME.demo_usage
                    (user_key, tokens_consumed, requests_count, is_blocked, user_timezone)
                    VALUES (%s, %s, %s, %s, %s)
                """
                await self.db.execute(insert_query, (user_key, 0, 0, False, tz))
                logger.debug(f"Created new quota record: user_key={user_key}")
                return True, self.max_tokens - tokens_needed

            # Update timezone if provided and different from stored value
            if user_timezone and user_timezone != result.get("user_timezone"):
                update_tz_query = """
                    UPDATE :SCHEMA_NAME.demo_usage
                    SET user_timezone = %s, updated_at = %s
                    WHERE user_key = %s
                """
                await self.db.execute(update_tz_query, (user_timezone, now, user_key))
                logger.debug(f"Updated user timezone: user_key={user_key}")

            # Check if daily reset is needed (midnight in user's timezone passed)
            last_reset = result["last_reset"]
            stored_timezone = result.get("user_timezone", "UTC")

            # Convert current time and last_reset to user's timezone
            try:
                from zoneinfo import ZoneInfo

                user_tz = ZoneInfo(stored_timezone)
                now_user_tz = now.astimezone(user_tz)
                last_reset_user_tz = last_reset.astimezone(user_tz)

                # Check if we've passed midnight in user's timezone
                if last_reset_user_tz.date() < now_user_tz.date():
                    # Reset quota for new day
                    reset_query = """
                        UPDATE :SCHEMA_NAME.demo_usage
                        SET tokens_consumed = 0,
                            requests_count = 0,
                            is_blocked = false,
                            blocked_until = NULL,
                            last_reset = %s
                        WHERE user_key = %s
                    """
                    await self.db.execute(reset_query, (now, user_key))
                    logger.debug(f"Reset daily quota: user_key={user_key}")
                    return True, self.max_tokens - tokens_needed
            except Exception as e:
                # Fallback to UTC if timezone conversion fails
                logger.warning(f"Timezone conversion failed, falling back to UTC: {e}")
                if last_reset.date() < now.date():
                    reset_query = """
                        UPDATE :SCHEMA_NAME.demo_usage
                        SET tokens_consumed = 0,
                            requests_count = 0,
                            is_blocked = false,
                            blocked_until = NULL,
                            last_reset = %s
                        WHERE user_key = %s
                    """
                    await self.db.execute(reset_query, (now, user_key))
                    logger.debug(f"Reset daily quota (UTC fallback): user_key={user_key}")
                    return True, self.max_tokens - tokens_needed

            # Check if user is currently blocked
            if result["is_blocked"]:
                blocked_until = result["blocked_until"]
                if blocked_until and blocked_until > now:
                    # Block is still active
                    tokens_remaining = self.max_tokens - result["tokens_consumed"]
                    logger.warning(f"User blocked: user_key={user_key}")
                    return False, tokens_remaining
                else:
                    # Block has expired, auto-unblock
                    unblock_query = """
                        UPDATE :SCHEMA_NAME.demo_usage
                        SET is_blocked = false, blocked_until = NULL
                        WHERE user_key = %s
                    """
                    await self.db.execute(unblock_query, (user_key,))
                    logger.info(f"Auto-unblocked user: user_key={user_key}")

            # Calculate remaining tokens BEFORE deducting estimated tokens
            # User should be allowed to proceed if they have ANY tokens remaining
            tokens_before_request = self.max_tokens - result["tokens_consumed"]
            can_proceed = tokens_before_request > 0

            # Calculate remaining after deduction for return value
            tokens_remaining = tokens_before_request - tokens_needed

            logger.debug(f"Quota check completed: user_key={user_key}, can_proceed={can_proceed}")

            return can_proceed, max(0, tokens_remaining)

        except Exception:
            logger.exception(f"Error in check_quota: user_key={user_key}")
            # Fail open: allow request but log error for review
            return True, self.max_tokens

    async def deduct_tokens(self, user_key: str, tokens_used: int) -> int:
        """Deduct tokens after request completion.

        Args:
            user_key: User identifier
            tokens_used: Actual tokens consumed by Gemini API

        Returns:
            int: Tokens remaining after deduction

        Logic:
        1. Atomic UPDATE: tokens_consumed += tokens_used, requests_count += 1
        2. Check if quota exceeded (tokens_consumed >= max_tokens)
        3. If exceeded: SET is_blocked = true, blocked_until = NOW() + cooldown_hours
        4. Return remaining tokens
        """
        try:
            logger.debug(f"Deducting tokens: user_key={user_key}, tokens_used={tokens_used}")

            # SECURITY (CWE-362 fix): Atomic update with conditional blocking
            # Single query prevents race condition where multiple concurrent requests
            # could bypass quota limits between check and block operations
            now = datetime.now(timezone.utc)
            blocked_until = now + timedelta(hours=self.cooldown_hours)

            query = """
                UPDATE :SCHEMA_NAME.demo_usage
                SET tokens_consumed = tokens_consumed + %s,
                    requests_count = requests_count + 1,
                    updated_at = %s,
                    is_blocked = CASE
                        WHEN (tokens_consumed + %s) >= %s THEN true
                        ELSE is_blocked
                    END,
                    blocked_until = CASE
                        WHEN (tokens_consumed + %s) >= %s THEN %s
                        ELSE blocked_until
                    END
                WHERE user_key = %s
                RETURNING tokens_consumed, is_blocked, blocked_until
            """
            result = await self.db.execute_one(
                query,
                (
                    tokens_used,  # For tokens_consumed increment
                    now,  # For updated_at
                    tokens_used,  # For CASE condition check (1st)
                    self.max_tokens,  # For CASE condition check (1st)
                    tokens_used,  # For CASE condition check (2nd)
                    self.max_tokens,  # For CASE condition check (2nd)
                    blocked_until,  # For blocked_until value
                    user_key,  # WHERE clause
                ),
            )

            if not result:
                logger.error(f"User not found after deduction: user_key={user_key}")
                return self.max_tokens

            new_tokens_consumed = result["tokens_consumed"]
            tokens_remaining = max(0, self.max_tokens - new_tokens_consumed)
            is_blocked = result["is_blocked"]

            # Log if user was blocked by this operation
            if is_blocked and new_tokens_consumed >= self.max_tokens:
                logger.warning(f"User quota exhausted and blocked: user_key={user_key}")

            logger.debug(f"Tokens deducted: user_key={user_key}, remaining={tokens_remaining}")
            return int(tokens_remaining)

        except Exception:
            logger.exception(f"Error in deduct_tokens: user_key={user_key}")
            return int(self.max_tokens)

    async def get_quota_status(self, user_key: str) -> dict[str, Any]:
        """Get user's current quota status.

        Args:
            user_key: User identifier

        Returns:
            dict with keys:
            - tokens_used: Tokens consumed today
            - tokens_remaining: Tokens left today
            - daily_limit: Maximum tokens allowed per day (from DEMO_MAX_TOKENS)
            - percentage_used: Usage percentage (0-100)
            - requests_count: Number of requests today
            - is_blocked: Whether user is currently blocked
            - blocked_until: Block expiration (ISO 8601) or None
            - last_reset: Last quota reset (ISO 8601)
            - next_reset: Next quota reset (ISO 8601 at UTC midnight)
            - warning: Warning object with is_warning, message, percentage_used
        """
        try:
            logger.debug(f"Getting quota status: user_key={user_key}")

            query = """
                SELECT tokens_consumed, requests_count, is_blocked,
                       blocked_until, last_reset, user_timezone
                FROM :SCHEMA_NAME.demo_usage
                WHERE user_key = %s
            """
            result = await self.db.execute_one(query, (user_key,))

            # Default status if user not found
            if not result:
                now = datetime.now(timezone.utc)
                return {
                    "tokens_used": 0,
                    "tokens_remaining": self.max_tokens,
                    "daily_limit": self.max_tokens,  # Frontend needs this for display
                    "percentage_used": 0,
                    "requests_count": 0,
                    "is_blocked": False,
                    "blocked_until": None,
                    "last_reset": now.isoformat(),
                    "next_reset": self._next_midnight_in_timezone("UTC"),
                    "warning": {
                        "is_warning": False,
                        "message": None,
                        "percentage_used": 0,
                    },
                }

            tokens_consumed = result["tokens_consumed"]
            tokens_remaining = max(0, self.max_tokens - tokens_consumed)
            percentage_used = min(100, int((tokens_consumed / self.max_tokens) * 100))

            # Calculate next reset (next midnight in user's timezone)
            user_tz = result.get("user_timezone", "UTC")
            next_reset = self._next_midnight_in_timezone(user_tz)

            # Generate warning object based on threshold
            is_warning = percentage_used >= settings.demo_warning_threshold
            warning_msg = None
            if is_warning:
                # Generic English message with dynamic percentage
                # Frontend handles i18n translations based on is_warning flag
                warning_msg = f"You've consumed {percentage_used}% of your daily quota"

            logger.debug(
                f"Quota status retrieved: user_key={user_key}, percentage={percentage_used}%"
            )
            return {
                "tokens_used": tokens_consumed,
                "tokens_remaining": tokens_remaining,
                "daily_limit": self.max_tokens,  # Frontend needs this for display
                "percentage_used": percentage_used,
                "requests_count": result["requests_count"],
                "is_blocked": result["is_blocked"],
                "blocked_until": (
                    result["blocked_until"].isoformat() if result["blocked_until"] else None
                ),
                "user_timezone": result.get("user_timezone", "UTC"),  # For frontend display
                "last_reset": result["last_reset"].isoformat(),
                "next_reset": next_reset,
                "warning": {
                    "is_warning": is_warning,
                    "message": warning_msg,
                    "percentage_used": percentage_used,
                },
            }

        except Exception:
            logger.exception(f"Error in get_quota_status: user_key={user_key}")
            return {
                "tokens_used": 0,
                "tokens_remaining": self.max_tokens,
                "percentage_used": 0,
                "requests_count": 0,
                "is_blocked": False,
                "blocked_until": None,
                "last_reset": datetime.now(timezone.utc).isoformat(),
                "next_reset": self._next_midnight_in_timezone("UTC"),
                "warning": {
                    "is_warning": False,
                    "message": None,
                    "percentage_used": 0,
                },
            }

    async def refund_tokens(self, user_key: str, tokens_to_refund: int) -> int:
        """Refund tokens to user (for failed API calls).

        Args:
            user_key: User identifier
            tokens_to_refund: Number of tokens to refund

        Returns:
            int: Tokens remaining after refund

        Logic:
        1. Atomic UPDATE: tokens_consumed -= tokens_to_refund
        2. Check if user was blocked due to quota
        3. If blocked: unblock automatically (they now have tokens again)
        4. Return remaining tokens

        Security:
            - Tokens cannot go negative (minimum 0)
            - Validates tokens_to_refund > 0
            - Logs all refunds for audit trail
            - Atomic operation prevents race conditions

        Use Case:
            When Gemini API call fails after tokens deducted:
            - API returns error before generating response
            - Tokens were already deducted via deduct_tokens()
            - Call refund_tokens() to reverse the deduction
            - User is not penalized for infrastructure errors

        Example:
            # User makes request, tokens deducted
            tokens_used = 250
            remaining = await bucket.deduct_tokens("user_123", tokens_used)

            # API call fails before response
            try:
                response = await gemini_client.generate_response(...)
            except Exception:
                # Refund the tokens
                remaining = await bucket.refund_tokens("user_123", tokens_used)
        """
        try:
            if tokens_to_refund <= 0:
                logger.warning(
                    f"Invalid refund amount: user_key={user_key}, amount={tokens_to_refund}"
                )
                return self.max_tokens

            logger.debug(f"Refunding tokens: user_key={user_key}, amount={tokens_to_refund}")

            # Atomic update: refund tokens
            query = """
                UPDATE :SCHEMA_NAME.demo_usage
                SET tokens_consumed = MAX(0, tokens_consumed - %s),
                    updated_at = %s
                WHERE user_key = %s
                RETURNING tokens_consumed, is_blocked
            """
            now = datetime.now(timezone.utc)
            result = await self.db.execute_one(query, (tokens_to_refund, now, user_key))

            if not result:
                logger.error(f"User not found after refund: user_key={user_key}")
                return self.max_tokens

            new_tokens_consumed = result["tokens_consumed"]
            tokens_remaining = max(0, self.max_tokens - new_tokens_consumed)

            # Check if user was blocked and now has tokens again
            if result["is_blocked"] and new_tokens_consumed < self.max_tokens:
                logger.info(f"Auto-unblocking user after refund: user_key={user_key}")
                unblock_query = """
                    UPDATE :SCHEMA_NAME.demo_usage
                    SET is_blocked = false,
                        blocked_until = NULL,
                        updated_at = %s
                    WHERE user_key = %s
                """
                await self.db.execute(unblock_query, (now, user_key))

            logger.info(f"Tokens refunded: user_key={user_key}, amount={tokens_to_refund}")
            return int(tokens_remaining)

        except Exception:
            logger.exception(f"Error in refund_tokens: user_key={user_key}")
            return int(self.max_tokens)

    async def unblock_user(self, user_key: str) -> bool:
        """Manually unblock user (admin operation).

        Args:
            user_key: User identifier

        Returns:
            bool: True if unblock was successful

        Logic:
        - UPDATE demo_usage SET is_blocked = false, blocked_until = NULL
        - Log unblock action for audit trail
        """
        try:
            logger.debug(f"Unblocking user: user_key={user_key}")

            query = """
                UPDATE :SCHEMA_NAME.demo_usage
                SET is_blocked = false,
                    blocked_until = NULL,
                    updated_at = %s
                WHERE user_key = %s
            """
            now = datetime.now(timezone.utc)
            await self.db.execute(query, (now, user_key))
            logger.info(f"Admin unblocked user: user_key={user_key}")
            return True

        except Exception:
            logger.exception(f"Error in unblock_user: user_key={user_key}")
            return False

    @staticmethod
    def _next_midnight_in_timezone(user_timezone: str = "UTC") -> str:
        """Calculate next midnight in user's timezone.

        Args:
            user_timezone: IANA timezone identifier (e.g., 'America/Costa_Rica')

        Returns:
            ISO 8601 formatted string of next midnight in user's timezone (as UTC)
        """
        try:
            from zoneinfo import ZoneInfo

            user_tz = ZoneInfo(user_timezone)
            now_user_tz = datetime.now(user_tz)

            # Next midnight in user's timezone
            next_midnight_user_tz = now_user_tz.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

            # Convert back to UTC for storage
            next_midnight_utc = next_midnight_user_tz.astimezone(timezone.utc)
            return next_midnight_utc.isoformat()
        except Exception:
            # Fallback to UTC midnight if timezone is invalid
            now = datetime.now(timezone.utc)
            next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
            return next_midnight.isoformat()
