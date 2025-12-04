"""IP-based rate limiting for demo agent.

Tracks requests per IP per minute and blocks abusive sources.

Author: Odiseo Team
Created: 2025-10-31
Version: 1.0.0
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.settings import settings
from app.db.connection import get_db
from app.utils.logging import get_logger

logger = get_logger(__name__)


class IPLimiter:
    """Rate limiter based on IP address.

    Tracks requests per IP per minute and detects abuse patterns.
    Uses PostgreSQL to store IP statistics for persistence across restarts.

    Attributes:
        max_requests_per_minute: Maximum requests allowed per IP per minute
        db: Database connection
    """

    def __init__(self, max_requests_per_minute: int | None = None):
        """Initialize IP limiter.

        Args:
            max_requests_per_minute: Max requests per IP per minute
                (uses config if not provided)
        """
        self.max_requests_per_minute = max_requests_per_minute or settings.ip_rate_limit_requests
        self.db = get_db()
        logger.info(f"IPLimiter initialized ({self.max_requests_per_minute} req/min per IP)")

    async def check_rate_limit(self, ip_address: str) -> tuple[bool, int]:
        """Check if IP has exceeded rate limit.

        Args:
            ip_address: Client IP address

        Returns:
            Tuple[allowed, requests_in_window]:
            - allowed: True if request is allowed
            - requests_in_window: Current request count in last minute

        Logic:
        1. Query demo_ip_limits table for IP
        2. Clean old entries (older than 1 minute)
        3. Count requests in last 60 seconds
        4. If count >= limit: return False
        5. If count < limit: increment and return True
        """
        # SECURITY FIX: Fail closed on empty IP - don't allow bypass of rate limiting
        if not ip_address or not ip_address.strip():
            logger.error("check_rate_limit called with empty IP address - denying request")
            return False, 0

        try:
            logger.debug(f"Checking rate limit for IP: {ip_address}")

            # Get current time and 1 minute ago
            now = datetime.now(timezone.utc)
            one_minute_ago = now - timedelta(minutes=1)

            # Query recent requests from this IP
            query = """
                SELECT COUNT(*) as request_count
                FROM (
                    SELECT 1
                    FROM :SCHEMA_NAME.demo_audit_log
                    WHERE ip_address = %s::inet
                    AND created_at >= %s
                    ORDER BY created_at DESC
                    LIMIT %s
                ) AS recent_requests
            """
            result = await self.db.execute_one(
                query, (ip_address, one_minute_ago, self.max_requests_per_minute + 100)
            )

            request_count = result.get("request_count", 0) if result else 0
            allowed = request_count < self.max_requests_per_minute

            logger.debug(
                f"IP {ip_address}: {request_count}/{self.max_requests_per_minute} requests"
            )
            return allowed, request_count

        except Exception as e:
            logger.error(f"Error checking rate limit for {ip_address}: {e}")
            # SECURITY: Fail closed - deny request on database errors
            return False, 0

    async def get_ip_stats(self, ip_address: str) -> dict[str, Any]:
        """Get detailed statistics for an IP address.

        Args:
            ip_address: Client IP address

        Returns:
            dict with IP statistics:
            - total_requests: Total requests from this IP (all time)
            - requests_today: Requests in last 24 hours
            - requests_per_minute: Current rate (last minute)
            - unique_users: Unique user_keys from this IP
            - abuse_score_avg: Average abuse score
            - first_seen: First request timestamp
            - last_seen: Last request timestamp
            - is_blocked: Whether IP is globally blocked
        """
        # Handle None or empty IP address
        if not ip_address or not ip_address.strip():
            logger.warning("get_ip_stats called with empty IP address, returning default stats")
            return {
                "ip_address": ip_address or "unknown",
                "total_requests": 0,
                "requests_today": 0,
                "requests_per_minute": 0,
                "unique_users": 0,
                "abuse_score_avg": 0.0,
                "abuse_score_max": 0.0,
                "first_seen": None,
                "last_seen": None,
                "rate_limit_exceeded": False,
            }

        try:
            now = datetime.now(timezone.utc)
            one_day_ago = now - timedelta(days=1)
            one_minute_ago = now - timedelta(minutes=1)

            # Total requests all time
            query_total = """
                SELECT COUNT(*) as total_requests
                FROM :SCHEMA_NAME.demo_audit_log
                WHERE ip_address = %s::inet
            """
            result_total = await self.db.execute_one(query_total, (ip_address,))
            total_requests = result_total.get("total_requests", 0) if result_total else 0

            # Requests in last 24 hours
            query_today = """
                SELECT COUNT(*) as requests_today
                FROM :SCHEMA_NAME.demo_audit_log
                WHERE ip_address = %s::inet AND created_at >= %s
            """
            result_today = await self.db.execute_one(query_today, (ip_address, one_day_ago))
            requests_today = result_today.get("requests_today", 0) if result_today else 0

            # Requests per minute (current)
            query_rate = """
                SELECT COUNT(*) as requests_per_minute
                FROM :SCHEMA_NAME.demo_audit_log
                WHERE ip_address = %s::inet AND created_at >= %s
            """
            result_rate = await self.db.execute_one(query_rate, (ip_address, one_minute_ago))
            requests_per_minute = result_rate.get("requests_per_minute", 0) if result_rate else 0

            # Unique users from this IP
            query_users = """
                SELECT COUNT(DISTINCT user_key) as unique_users
                FROM :SCHEMA_NAME.demo_audit_log
                WHERE ip_address = %s::inet AND user_key IS NOT NULL
            """
            result_users = await self.db.execute_one(query_users, (ip_address,))
            unique_users = result_users.get("unique_users", 0) if result_users else 0

            # Average abuse score
            query_abuse = """
                SELECT AVG(abuse_score) as avg_abuse_score,
                       MAX(abuse_score) as max_abuse_score
                FROM :SCHEMA_NAME.demo_audit_log
                WHERE ip_address = %s::inet
            """
            result_abuse = await self.db.execute_one(query_abuse, (ip_address,))
            avg_abuse_score = result_abuse.get("avg_abuse_score", 0.0) if result_abuse else 0.0
            max_abuse_score = result_abuse.get("max_abuse_score", 0.0) if result_abuse else 0.0

            # First and last seen
            query_timeline = """
                SELECT MIN(created_at) as first_seen,
                       MAX(created_at) as last_seen
                FROM :SCHEMA_NAME.demo_audit_log
                WHERE ip_address = %s::inet
            """
            result_timeline = await self.db.execute_one(query_timeline, (ip_address,))
            first_seen: str | None = None
            last_seen: str | None = None
            if result_timeline:
                first_seen_val = result_timeline.get("first_seen")
                last_seen_val = result_timeline.get("last_seen")
                if first_seen_val is not None:
                    first_seen = first_seen_val.isoformat()
                if last_seen_val is not None:
                    last_seen = last_seen_val.isoformat()

            return {
                "ip_address": ip_address,
                "total_requests": total_requests,
                "requests_today": requests_today,
                "requests_per_minute": requests_per_minute,
                "unique_users": unique_users,
                "abuse_score_avg": (round(avg_abuse_score, 3) if avg_abuse_score else 0.0),
                "abuse_score_max": (round(max_abuse_score, 3) if max_abuse_score else 0.0),
                "first_seen": first_seen,
                "last_seen": last_seen,
                "rate_limit_exceeded": requests_per_minute >= self.max_requests_per_minute,
            }

        except Exception as e:
            logger.error(f"Error getting IP stats for {ip_address}: {e}")
            return {
                "ip_address": ip_address,
                "error": str(e),
            }

    async def is_ip_suspicious(self, ip_address: str) -> tuple[bool, str]:
        """Determine if IP should be flagged as suspicious.

        Flags:
        - High request rate (>5 req/min)
        - High average abuse score (>0.7)
        - Multiple blocked requests (>5 in last hour)
        - Requests from many different users (>10 unique users)

        Args:
            ip_address: Client IP address

        Returns:
            Tuple[is_suspicious, reason]:
            - is_suspicious: True if IP meets suspicious criteria
            - reason: Description of suspicious pattern
        """
        # Handle None or empty IP address - not suspicious by default
        if not ip_address or not ip_address.strip():
            logger.warning(
                "is_ip_suspicious called with empty IP address, returning not suspicious"
            )
            return False, ""

        try:
            stats = await self.get_ip_stats(ip_address)

            # Check rate limit (configurable via IP_SUSPICIOUS_REQ_PER_MIN)
            if stats["requests_per_minute"] > settings.ip_suspicious_req_per_min:
                return (
                    True,
                    f"High request rate ({stats['requests_per_minute']} req/min)",
                )

            # Check abuse score
            if stats["abuse_score_avg"] > 0.7:
                return (
                    True,
                    f"High average abuse score ({stats['abuse_score_avg']})",
                )

            # Check blocked requests
            now = datetime.now(timezone.utc)
            one_hour_ago = now - timedelta(hours=1)

            query_blocked = """
                SELECT COUNT(*) as blocked_count
                FROM :SCHEMA_NAME.demo_audit_log
                WHERE ip_address = %s::inet
                AND is_blocked = true
                AND created_at >= %s
            """
            result_blocked = await self.db.execute_one(query_blocked, (ip_address, one_hour_ago))
            blocked_count = result_blocked.get("blocked_count", 0) if result_blocked else 0

            if blocked_count > 5:
                return True, f"Multiple blocked requests ({blocked_count} in last hour)"

            # Check unique users (account takeover detection, configurable via IP_SUSPICIOUS_UNIQUE_USERS)
            if stats["unique_users"] > settings.ip_suspicious_unique_users:
                return (
                    True,
                    f"Requests from {stats['unique_users']} different users (possible attack)",
                )

            return False, "No suspicious patterns detected"

        except Exception as e:
            logger.error(f"Error checking IP suspicion for {ip_address}: {e}")
            return False, f"Error: {str(e)}"

    def get_reputation_score(self, ip_address: str, stats: dict[str, Any]) -> float:
        """Calculate IP reputation score (0.0-1.0).

        Lower score = better reputation
        0.0 = trusted, 1.0 = definitely malicious

        Args:
            ip_address: Client IP address
            stats: Stats dictionary from get_ip_stats()

        Returns:
            float: Reputation score 0.0-1.0
        """
        try:
            score = 0.0

            # Factor 1: Request rate (0.0-0.4)
            requests_per_min = stats.get("requests_per_minute", 0)
            if requests_per_min > self.max_requests_per_minute:
                rate_score = min(
                    0.4,
                    (
                        (requests_per_min - self.max_requests_per_minute)
                        / self.max_requests_per_minute
                    ),
                )
                score += rate_score

            # Factor 2: Abuse score (0.0-0.4)
            avg_abuse = stats.get("abuse_score_avg", 0.0)
            score += avg_abuse * 0.4

            # Factor 3: Blocked requests (0.0-0.3)
            total_requests = stats.get("total_requests", 1)
            blocked_ratio = stats.get("requests_today", 0) / max(total_requests, 1)
            score += min(0.3, blocked_ratio * 0.3)

            # Factor 4: Unique users (0.0-0.2)
            unique_users = stats.get("unique_users", 0)
            if unique_users > 10:
                user_score = min(0.2, (unique_users - 10) / 100)
                score += user_score

            return float(min(1.0, score))

        except Exception as e:
            logger.error(f"Error calculating reputation for {ip_address}: {e}")
            return 0.5  # Neutral score on error
