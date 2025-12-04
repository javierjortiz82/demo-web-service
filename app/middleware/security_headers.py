"""Security Headers Middleware.

Adds security-related HTTP headers to all responses to protect against
common web vulnerabilities.

SECURITY (CWE-1021 fix): Implements OWASP recommended security headers
to prevent XSS, clickjacking, MIME sniffing, and other attacks.

Author: Odiseo Team
Created: 2025-11-07
Version: 1.0.0 (Security-Hardened)
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.utils.logging import get_logger

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all HTTP responses.

    SECURITY (CWE-1021 mitigation): Implements defense-in-depth by adding
    multiple security headers that protect against various attack vectors:

    Headers Applied:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking attacks
    - X-XSS-Protection: Enables browser XSS filter
    - Strict-Transport-Security (HSTS): Enforces HTTPS
    - Content-Security-Policy (CSP): Prevents XSS and data injection
    - Referrer-Policy: Controls referrer information leakage
    - Permissions-Policy: Restricts browser features
    - X-Permitted-Cross-Domain-Policies: Restricts Adobe Flash/PDF policies

    References:
    - OWASP Secure Headers Project
    - Mozilla Observatory recommendations
    - NIST SP 800-95 (Web Security)
    """

    def __init__(
        self,
        app: ASGIApp,
        enable_hsts: bool = True,
        hsts_max_age: int = 31536000,  # 1 year
        enable_csp: bool = True,
        csp_report_only: bool = False,
    ):
        """Initialize security headers middleware.

        Args:
            app: ASGI application.
            enable_hsts: Enable Strict-Transport-Security header.
            hsts_max_age: HSTS max-age in seconds (default: 1 year).
            enable_csp: Enable Content-Security-Policy header.
            csp_report_only: Use CSP in report-only mode (logs violations without blocking).
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.enable_csp = enable_csp
        self.csp_report_only = csp_report_only

        logger.info(
            f"SecurityHeadersMiddleware initialized: "
            f"HSTS={enable_hsts}, CSP={enable_csp}, CSP_report_only={csp_report_only}"
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request and add security headers to response.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware in chain.

        Returns:
            Response with security headers added.
        """
        # Call next middleware/endpoint
        response: Response = await call_next(request)

        # ====================================================================
        # OWASP Recommended Security Headers
        # ====================================================================

        # 1. X-Content-Type-Options: Prevent MIME type sniffing
        # Prevents browsers from interpreting files as a different MIME type
        # Mitigates: Drive-by downloads, XSS via content type confusion
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 2. X-Frame-Options: Prevent clickjacking
        # Prevents page from being loaded in iframe/frame
        # Mitigates: Clickjacking, UI redressing attacks
        response.headers["X-Frame-Options"] = "DENY"

        # 3. X-XSS-Protection: Enable browser XSS filter
        # Modern browsers have this enabled by default, but explicit is better
        # mode=block: Block page rendering if XSS detected
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 4. Strict-Transport-Security (HSTS): Enforce HTTPS
        # Forces browsers to use HTTPS for all future requests
        # includeSubDomains: Apply to all subdomains
        # preload: Allow inclusion in browser HSTS preload lists
        # Mitigates: Man-in-the-middle, SSL stripping attacks
        if self.enable_hsts and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={self.hsts_max_age}; includeSubDomains; preload"
            )

        # 5. Content-Security-Policy (CSP): Prevent XSS and data injection
        # Defines allowed sources for scripts, styles, images, etc.
        # Mitigates: XSS, data injection, malicious resource loading
        if self.enable_csp:
            csp_directives = [
                "default-src 'self'",  # Only allow resources from same origin
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Scripts (relaxed for compatibility)
                "style-src 'self' 'unsafe-inline'",  # Styles (inline allowed for convenience)
                "img-src 'self' data: https:",  # Images from same origin, data URLs, HTTPS
                "font-src 'self' data:",  # Fonts from same origin or data URLs
                "connect-src 'self'",  # AJAX/fetch/websocket to same origin only
                "frame-ancestors 'none'",  # Don't allow embedding (same as X-Frame-Options)
                "base-uri 'self'",  # Restrict <base> tag to same origin
                "form-action 'self'",  # Forms can only submit to same origin
                "upgrade-insecure-requests",  # Auto-upgrade HTTP to HTTPS
            ]

            csp_policy = "; ".join(csp_directives)

            if self.csp_report_only:
                # Report violations but don't block (useful for testing)
                response.headers["Content-Security-Policy-Report-Only"] = csp_policy
            else:
                # Block violations (production mode)
                response.headers["Content-Security-Policy"] = csp_policy

        # 6. Referrer-Policy: Control referrer information
        # Prevents leaking sensitive URLs to third parties
        # strict-origin-when-cross-origin: Only send origin on cross-origin requests
        # Mitigates: Information disclosure via Referer header
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 7. Permissions-Policy (formerly Feature-Policy): Restrict browser features
        # Disables potentially dangerous browser features
        # Mitigates: Unauthorized camera/microphone access, geolocation tracking
        permissions = [
            "camera=()",  # Disable camera
            "microphone=()",  # Disable microphone
            "geolocation=()",  # Disable geolocation
            "interest-cohort=()",  # Disable FLoC tracking
            "payment=()",  # Disable payment API
            "usb=()",  # Disable USB API
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions)

        # 8. X-Permitted-Cross-Domain-Policies: Restrict Adobe Flash/PDF policies
        # Prevents Flash/PDF from loading cross-domain policy files
        # Mitigates: Cross-domain data theft via Flash/PDF
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # 9. Server header removal (optional)
        # Don't advertise server technology (reduce attack surface)
        # Note: FastAPI/Starlette sets this automatically, we remove it
        if "Server" in response.headers:
            del response.headers["Server"]

        # 10. X-Powered-By removal (if present)
        # Don't advertise framework/technology
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

        return response
