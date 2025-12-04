"""Client IP Extraction Service.

Secure extraction of client IP addresses from HTTP requests with support for
proxies, load balancers, and CDNs (Cloudflare, nginx, AWS, etc.).

This service implements security best practices to prevent IP spoofing attacks:
- Validates trusted proxies before accepting forwarded headers
- Supports multiple proxy configurations (Cloudflare, nginx, load balancers)
- Never trusts client-supplied headers without validation
- Implements proper proxy chain traversal

Security Warning:
    Headers like X-Forwarded-For can be spoofed by clients. This service
    ONLY trusts these headers when the request comes from a validated
    trusted proxy. Configure TRUSTED_PROXIES in environment variables.

Author: Odiseo Team
Created: 2025-11-07
Version: 2.0.0
"""

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network

from fastapi import Request

from app.config.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

IPAddressType = IPv4Address | IPv6Address
IPNetworkType = IPv4Network | IPv6Network


class ClientIPExtractor:
    """Extract client IP addresses from HTTP requests with security validation.

    This service implements the Strategy pattern to support different proxy
    configurations and follows security best practices for IP extraction.

    Features:
    - Trusted proxy validation (prevents spoofing)
    - Multiple CDN/proxy support (Cloudflare, nginx, AWS, etc.)
    - Configurable proxy chain depth
    - CIDR range support for trusted proxies
    - Comprehensive logging for security monitoring

    Examples:
        Basic usage:
        >>> extractor = ClientIPExtractor()
        >>> ip = extractor.get_client_ip(request)

        With Cloudflare:
        >>> extractor = ClientIPExtractor(use_cloudflare=True)
        >>> ip = extractor.get_client_ip(request)

    Attributes:
        trusted_proxies: List of trusted proxy IP addresses/networks
        enable_proxy_headers: Whether to trust proxy headers
        proxy_depth: Expected number of proxies in chain
        use_cloudflare: Enable Cloudflare-specific headers
    """

    def __init__(
        self,
        trusted_proxies: list[str] | None = None,
        enable_proxy_headers: bool = True,
        proxy_depth: int = 1,
        use_cloudflare: bool = False,
    ):
        """Initialize the client IP extractor.

        Args:
            trusted_proxies: List of trusted proxy IPs or CIDR ranges.
                           If None, loads from settings.trusted_proxies.
            enable_proxy_headers: Whether to trust proxy headers.
            proxy_depth: Number of proxies in chain (0 = direct, 1 = one proxy).
            use_cloudflare: Enable Cloudflare-specific headers.
        """
        self.enable_proxy_headers = enable_proxy_headers
        self.proxy_depth = proxy_depth
        self.use_cloudflare = use_cloudflare

        # Parse trusted proxies from config or parameter
        if trusted_proxies is None:
            trusted_proxies_str = settings.trusted_proxies.strip()
            if trusted_proxies_str:
                trusted_proxies = [p.strip() for p in trusted_proxies_str.split(",")]
            else:
                trusted_proxies = []

        self.trusted_proxies: list[IPNetworkType] = self._parse_trusted_proxies(trusted_proxies)

        logger.info(
            f"ClientIPExtractor initialized: "
            f"proxy_headers={enable_proxy_headers}, "
            f"cloudflare={use_cloudflare}, "
            f"trusted_proxies={len(self.trusted_proxies)}"
        )

    def _parse_trusted_proxies(self, proxy_list: list[str]) -> list[IPNetworkType]:
        """Parse list of IP addresses and CIDR ranges into network objects.

        Args:
            proxy_list: List of IP addresses or CIDR ranges.

        Returns:
            List of IPv4Network or IPv6Network objects.
        """
        networks: list[IPNetworkType] = []

        for proxy in proxy_list:
            try:
                # Try parsing as network (supports CIDR)
                network = ip_network(proxy, strict=False)
                networks.append(network)
                logger.debug(f"Added trusted proxy network: {network}")
            except ValueError as e:
                logger.warning(f"Invalid proxy address '{proxy}' in TRUSTED_PROXIES: {e}")

        return networks

    def _is_trusted_proxy(self, ip_str: str) -> bool:
        """Check if an IP address is a trusted proxy.

        Args:
            ip_str: IP address as string.

        Returns:
            True if IP is in trusted proxies list.
        """
        if not self.trusted_proxies:
            # No trusted proxies configured - don't trust any proxy headers
            return False

        try:
            ip = ip_address(ip_str)
            for network in self.trusted_proxies:
                if ip in network:
                    return True
            return False
        except ValueError:
            logger.warning(f"Invalid IP address format: {ip_str}")
            return False

    def get_client_ip(self, request: Request) -> str | None:
        """Extract client IP address from request with security validation.

        Extraction order (when proxy headers enabled and proxy is trusted):
        1. CF-Connecting-IP (Cloudflare) - if use_cloudflare=True
        2. True-Client-IP (Cloudflare Enterprise) - if use_cloudflare=True
        3. X-Real-IP (nginx, load balancers)
        4. X-Forwarded-For (generic proxy) - validates proxy chain
        5. X-Envoy-External-Address (Envoy proxy, Railway.app)
        6. request.client.host (direct connection)

        Security:
        - Headers are ONLY trusted if request comes from a trusted proxy
        - X-Forwarded-For is validated against proxy chain depth
        - Cloudflare headers are only used if explicitly enabled
        - All IP addresses are validated for correct format

        Args:
            request: FastAPI Request object.

        Returns:
            Client IP address as string, or None if unable to determine.
        """
        # Get the immediate connection IP
        direct_ip = request.client.host if request.client else None

        # If proxy headers disabled, return direct IP only
        if not self.enable_proxy_headers:
            logger.debug(f"Proxy headers disabled, using direct connection IP: {direct_ip}")
            return direct_ip

        # Check if request comes from trusted proxy
        if direct_ip and not self._is_trusted_proxy(direct_ip):
            logger.warning(
                f"Request from non-trusted proxy {direct_ip}, " f"rejecting forwarded headers"
            )
            return direct_ip

        # Request comes from trusted proxy - check forwarded headers
        logger.debug(f"Request from trusted proxy {direct_ip}, checking headers")

        # 1. Cloudflare CF-Connecting-IP (single IP, most reliable)
        if self.use_cloudflare:
            cf_ip = request.headers.get("CF-Connecting-IP")
            cf_ip = self._sanitize_header_value(cf_ip) if cf_ip else None
            if cf_ip and self._validate_ip(cf_ip):
                logger.debug(f"Using CF-Connecting-IP: {cf_ip}")
                return cf_ip

            # 2. Cloudflare True-Client-IP (Enterprise feature)
            true_client_ip = request.headers.get("True-Client-IP")
            true_client_ip = self._sanitize_header_value(true_client_ip) if true_client_ip else None
            if true_client_ip and self._validate_ip(true_client_ip):
                logger.debug(f"Using True-Client-IP: {true_client_ip}")
                return true_client_ip

        # 3. X-Real-IP (nginx, common reverse proxies)
        real_ip = request.headers.get("X-Real-IP")
        real_ip = self._sanitize_header_value(real_ip) if real_ip else None
        if real_ip and self._validate_ip(real_ip):
            logger.debug(f"Using X-Real-IP: {real_ip}")
            return real_ip

        # 4. X-Forwarded-For (generic, can contain chain)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = self._extract_from_forwarded_for(forwarded_for)
            if client_ip:
                logger.debug(f"Using X-Forwarded-For: {client_ip}")
                return client_ip

        # 5. X-Envoy-External-Address (Envoy proxy, Railway.app)
        envoy_ip = request.headers.get("X-Envoy-External-Address")
        envoy_ip = self._sanitize_header_value(envoy_ip) if envoy_ip else None
        if envoy_ip and self._validate_ip(envoy_ip):
            logger.debug(f"Using X-Envoy-External-Address: {envoy_ip}")
            return envoy_ip

        # 6. Fallback to direct connection
        logger.debug(f"No valid forwarded headers, using direct IP: {direct_ip}")
        return direct_ip

    def _sanitize_header_value(self, header_value: str) -> str | None:
        """Sanitize HTTP header value to prevent header injection attacks.

        SECURITY (CWE-113 fix): Validates header values don't contain
        dangerous characters that could enable HTTP response splitting,
        header injection, or other attacks.

        Rejects headers containing:
        - Newlines (\\r, \\n) - HTTP response splitting
        - Null bytes (\\x00) - String termination attacks
        - Control characters (\\x01-\\x1f) - Protocol manipulation

        Args:
            header_value: Raw header value from HTTP request.

        Returns:
            Sanitized header value or None if contains dangerous characters.
        """
        if not header_value:
            return None

        # Check for dangerous characters
        dangerous_chars = [
            "\r",  # Carriage return (CRLF injection)
            "\n",  # Line feed (CRLF injection)
            "\x00",  # Null byte
        ]

        for char in dangerous_chars:
            if char in header_value:
                logger.warning(f"Header injection attempt detected: contains {repr(char)}")
                return None

        # Check for other control characters (0x01-0x1f except tab)
        for char in header_value:
            if ord(char) < 0x20 and char != "\t":
                logger.warning(
                    f"Header injection attempt detected: contains control character {repr(char)}"
                )
                return None

        # Additional length check to prevent DoS via huge headers
        if len(header_value) > 1000:
            logger.warning(f"Abnormally long header value rejected (len={len(header_value)})")
            return None

        return header_value

    def _extract_from_forwarded_for(self, forwarded_for: str) -> str | None:
        """Extract client IP from X-Forwarded-For header.

        X-Forwarded-For format: client, proxy1, proxy2, ...
        We need to extract the client IP based on proxy_depth.

        SECURITY (CWE-113 fix): Sanitizes header value before parsing
        to prevent header injection attacks.

        Args:
            forwarded_for: X-Forwarded-For header value.

        Returns:
            Client IP address or None if invalid.
        """
        # Sanitize header to prevent injection attacks
        sanitized_forwarded_for = self._sanitize_header_value(forwarded_for)
        if not sanitized_forwarded_for:
            return None

        # Split and clean IPs
        ips = [ip.strip() for ip in sanitized_forwarded_for.split(",")]

        if not ips:
            return None

        # For proxy_depth=1, we want the first IP (original client)
        # For proxy_depth=2, we want the second IP from the end
        # Formula: index = -(proxy_depth + 1) or 0 if out of range
        if self.proxy_depth == 0:
            # Direct connection, shouldn't have X-Forwarded-For
            logger.warning("X-Forwarded-For present but proxy_depth=0, using first IP")
            client_ip = ips[0]
        elif len(ips) > self.proxy_depth:
            # Extract IP based on proxy depth from the right
            # Example: client, proxy1, proxy2 with depth=1 -> we want client (ips[-2])
            client_ip = ips[-(self.proxy_depth + 1)]
        else:
            # Not enough IPs in chain, use the first (leftmost = original client)
            logger.warning(
                f"X-Forwarded-For has {len(ips)} IPs but expected {self.proxy_depth+1}, "
                f"using first IP"
            )
            client_ip = ips[0]

        # Validate IP format
        if self._validate_ip(client_ip):
            return client_ip

        logger.warning(f"Invalid IP in X-Forwarded-For: {client_ip}")
        return None

    def _validate_ip(self, ip_str: str) -> bool:
        """Validate if a string is a valid IP address.

        Args:
            ip_str: IP address as string.

        Returns:
            True if valid IPv4 or IPv6 address.
        """
        try:
            ip_address(ip_str)
            return True
        except ValueError:
            return False


# ============================================================================
# Singleton Instance (loaded from config)
# ============================================================================

_client_ip_extractor: ClientIPExtractor | None = None


def get_client_ip_extractor() -> ClientIPExtractor:
    """Get singleton instance of ClientIPExtractor.

    Loads configuration from environment variables on first call.

    Returns:
        ClientIPExtractor instance.
    """
    global _client_ip_extractor

    if _client_ip_extractor is None:
        _client_ip_extractor = ClientIPExtractor(
            enable_proxy_headers=settings.enable_proxy_headers,
            proxy_depth=settings.proxy_depth,
            use_cloudflare=settings.use_cloudflare,
        )

    return _client_ip_extractor


def extract_client_ip(request: Request) -> str | None:
    """Convenience function to extract client IP from request.

    This is the recommended way to get client IP in endpoints.

    Args:
        request: FastAPI Request object.

    Returns:
        Client IP address or None.

    Example:
        >>> from app.services.client_ip_service import extract_client_ip
        >>>
        >>> @app.post("/api/endpoint")
        >>> async def endpoint(request: Request):
        >>>     client_ip = extract_client_ip(request)
        >>>     logger.info(f"Request from {client_ip}")
    """
    extractor = get_client_ip_extractor()
    return extractor.get_client_ip(request)
