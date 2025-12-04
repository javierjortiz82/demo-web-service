"""Client fingerprinting for abuse detection.

Detects VPN/proxy rotation, suspicious patterns, and inconsistent behavior.
Generates fingerprint hashes and computes abuse scores.

Author: Odiseo Team
Created: 2025-10-31
Version: 1.0.0
"""

import hashlib
import json

from app.utils.logging import get_logger

logger = get_logger(__name__)


class FingerprintAnalyzer:
    """Analyzes client characteristics for abuse detection.

    Detects:
    - VPN/proxy usage (inconsistent IP/user-agent patterns)
    - Browser automation (Selenium, Puppeteer indicators)
    - Spoofed user agents
    - Suspicious geographic patterns
    - Device fingerprint inconsistencies

    Attributes:
        suspicious_ua_keywords: User-Agent keywords indicating automation
        suspicious_ip_patterns: IP ranges known for proxies/VPNs
    """

    # User-Agent keywords indicating automation/bots
    SUSPICIOUS_UA_KEYWORDS = [
        "headless",
        "phantom",
        "selenium",
        "puppeteer",
        "playwright",
        "webdriver",
        "bot",
        "crawler",
        "spider",
        "scraper",
    ]

    # Common proxy/VPN service indicators (case-insensitive)
    SUSPICIOUS_UA_SERVICES = [
        "torproject",
        "vpn",
        "proxy",
        "anonymous",
        "hide",
        "unblocker",
    ]

    def __init__(self) -> None:
        """Initialize fingerprint analyzer."""
        logger.info("FingerprintAnalyzer initialized")

    def generate_fingerprint(
        self,
        user_agent: str | None,
        ip_address: str | None,
        language: str | None = None,
        timezone: str | None = None,
        canvas_hash: str | None = None,
    ) -> str:
        """Generate device fingerprint hash from client characteristics.

        Args:
            user_agent: HTTP User-Agent header
            ip_address: Client IP address
            language: Browser language preference
            timezone: Client timezone
            canvas_hash: HTML5 canvas fingerprint

        Returns:
            SHA256 hash of combined characteristics (64 chars)

        Example:
            >>> analyzer = FingerprintAnalyzer()
            >>> fp = analyzer.generate_fingerprint(
            ...     user_agent="Mozilla/5.0...",
            ...     ip_address="203.0.113.42"
            ... )
            >>> print(fp)  # "a1b2c3d4e5f6..."
        """
        try:
            # Combine characteristics into dict
            fingerprint_data = {
                "ua": (user_agent or "").lower().strip(),
                "ip": ip_address or "",
                "lang": language or "",
                "tz": timezone or "",
                "canvas": canvas_hash or "",
            }

            # Convert to JSON and hash
            fingerprint_json = json.dumps(fingerprint_data, sort_keys=True)
            fingerprint_hash = hashlib.sha256(fingerprint_json.encode()).hexdigest()

            return fingerprint_hash

        except Exception as e:
            logger.error(f"Error generating fingerprint: {e}")
            return ""

    def compute_abuse_score(
        self,
        user_agent: str | None,
        ip_address: str | None,
        request_rate: float = 0.0,
        previous_ips: list[str] | None = None,
        previous_fingerprints: list[str] | None = None,
        ip_reputation: float = 0.0,
        tokens_consumed: int = 0,
        max_tokens: int = 5000,
    ) -> float:
        """Compute abuse likelihood score (0.0-1.0).

        Factors considered:
        - Automated/bot user agents (0.0-0.3)
        - VPN/proxy indicators (0.0-0.4)
        - Request rate (0.0-0.5)
        - IP reputation (0.0-0.6)
        - IP rotation patterns (0.0-0.5)
        - Rapid token consumption (0.0-0.4)
        - Behavior inconsistencies (0.0-0.3)

        Args:
            user_agent: HTTP User-Agent header
            ip_address: Client IP address
            request_rate: Requests per minute (0.0-∞)
            previous_ips: List of IPs used by this user (for rotation detection)
            previous_fingerprints: List of fingerprints (for consistency check)
            ip_reputation: IP abuse score from external service (0.0-1.0)
            tokens_consumed: Tokens consumed by user
            max_tokens: Maximum tokens per day

        Returns:
            float: Abuse score 0.0 (legitimate) to 1.0 (certain attack)
        """
        try:
            score = 0.0

            # Factor 1: User-Agent analysis (0.0-0.3)
            ua_score = self._analyze_user_agent(user_agent or "")
            score += ua_score * 0.25

            # Factor 2: Request rate analysis (0.0-0.5)
            rate_score = self._analyze_request_rate(request_rate)
            score += rate_score * 0.30

            # Factor 3: IP reputation (0.0-0.6)
            score += ip_reputation * 0.25

            # Factor 4: IP rotation pattern (0.0-0.5)
            if previous_ips and ip_address:
                rotation_score = self._analyze_ip_rotation(ip_address, previous_ips)
                score += rotation_score * 0.15

            # Factor 5: Rapid token consumption (0.0-0.4)
            if tokens_consumed > 0 and max_tokens > 0:
                consumption_score = min(1.0, (tokens_consumed / max_tokens) * 2.0)  # Max at 50%
                score += consumption_score * 0.10

            # Factor 6: Fingerprint inconsistency (0.0-0.3)
            if previous_fingerprints:
                consistency_score = self._analyze_fingerprint_consistency(
                    self.generate_fingerprint(user_agent, ip_address),
                    previous_fingerprints,
                )
                score += consistency_score * 0.10

            # Cap score at 1.0
            final_score = min(1.0, score)

            logger.debug(
                f"Abuse score computed: {final_score:.2f} "
                f"(ua={ua_score:.2f}, rate={rate_score:.2f}, "
                f"rep={ip_reputation:.2f})"
            )
            return final_score

        except Exception as e:
            logger.error(f"Error computing abuse score: {e}")
            return 0.0

    def _analyze_user_agent(self, user_agent: str) -> float:
        """Analyze User-Agent for suspicious indicators.

        Args:
            user_agent: HTTP User-Agent header

        Returns:
            float: Suspicion score 0.0-1.0
        """
        if not user_agent:
            return 0.1  # Missing UA is slightly suspicious

        ua_lower = user_agent.lower()

        # Check for known automation tools
        for keyword in self.SUSPICIOUS_UA_KEYWORDS:
            if keyword in ua_lower:
                return 0.7  # Strong indicator of automation

        # Check for VPN/proxy services
        for service in self.SUSPICIOUS_UA_SERVICES:
            if service in ua_lower:
                return 0.5  # VPN/proxy indicator

        # Check for common legitimate browsers
        legitimate_browsers = ["chrome", "firefox", "safari", "edge", "opera"]
        for browser in legitimate_browsers:
            if browser in ua_lower:
                return 0.0  # Legitimate browser

        # Unknown or uncommon UA
        return 0.2

    def _analyze_request_rate(self, requests_per_minute: float) -> float:
        """Analyze request rate for abuse patterns.

        Normal human rate: 0-1 request per minute
        Suspicious: 10+ requests per minute
        Abusive: 50+ requests per minute

        Args:
            requests_per_minute: Request rate (req/min)

        Returns:
            float: Suspicion score 0.0-1.0
        """
        if requests_per_minute <= 0.5:
            return 0.0  # Normal human rate

        if requests_per_minute <= 2:
            return 0.1  # Slightly fast

        if requests_per_minute <= 5:
            return 0.3  # Suspicious

        if requests_per_minute <= 10:
            return 0.6  # Very suspicious

        # 10+ requests per minute
        return min(1.0, requests_per_minute / 50.0)

    def _analyze_ip_rotation(self, current_ip: str, previous_ips: list[str]) -> float:
        """Analyze IP rotation patterns for VPN/proxy detection.

        Legitimate users: Same IP in 95%+ of requests
        VPN users: Different IP in 20-50% of requests
        Attackers: Random IP every request

        Args:
            current_ip: Current request IP
            previous_ips: List of previous IPs from same user

        Returns:
            float: Suspicion score 0.0-1.0
        """
        if not previous_ips:
            return 0.0  # No history to compare

        # Count how many previous IPs are different from current
        different_ips = sum(1 for ip in previous_ips if ip != current_ip)
        rotation_rate = different_ips / len(previous_ips)

        if rotation_rate <= 0.05:
            return 0.0  # Consistent IP (legitimate)

        if rotation_rate <= 0.2:
            return 0.2  # Minor variation (acceptable)

        if rotation_rate <= 0.5:
            return 0.6  # Significant rotation (suspicious - likely VPN)

        # Rotation in every request
        return 0.9

    def _analyze_fingerprint_consistency(
        self, current_fingerprint: str, previous_fingerprints: list[str]
    ) -> float:
        """Analyze device fingerprint consistency.

        Legitimate users: Same fingerprint in 90%+ of requests
        VPN users: Fingerprint changes with IP changes
        Attackers: Random fingerprint every request

        Args:
            current_fingerprint: Current device fingerprint
            previous_fingerprints: List of previous fingerprints

        Returns:
            float: Inconsistency score 0.0-1.0
        """
        if not previous_fingerprints or not current_fingerprint:
            return 0.1  # Missing data is slightly suspicious

        # Count matching fingerprints
        matching = sum(1 for fp in previous_fingerprints if fp == current_fingerprint)
        consistency_rate = matching / len(previous_fingerprints)

        if consistency_rate >= 0.9:
            return 0.0  # Highly consistent (legitimate)

        if consistency_rate >= 0.7:
            return 0.1  # Mostly consistent

        if consistency_rate >= 0.5:
            return 0.3  # Somewhat consistent (suspicious)

        # Mostly different fingerprints
        return 0.6
