"""Clerk Authentication Middleware for FastAPI.

Validates Clerk JWT tokens using public keys (JWKS) and attaches user info to request state.
No secret keys required - all validation uses Clerk's public JWKS endpoint.

Features:
- Bearer token extraction from Authorization header
- JWT validation using Clerk public keys (RS256)
- JIT (Just-In-Time) user provisioning to local database
- User attachment to request.state for protected routes
- Public routes exemption (no auth required)

Note:
- Requires JWT Template in Clerk Dashboard to include email/name claims
- No CLERK_SECRET_KEY needed for token validation

Author: Odiseo Team
Created: 2025-11-03
Version: 2.0.0 (Simplified)
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config.settings import settings
from app.services.clerk_service import get_clerk_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for Clerk JWT authentication.

    Validates Clerk session tokens on protected routes using public JWKS.
    Attaches user information to request.state for downstream handlers.

    Public routes (no auth required):
    - /health, /metrics
    - /docs, /redoc, /openapi.json
    - /v1/contact (public contact form)
    - /v1/booking (public demo booking form)

    Protected routes (auth required):
    - /v1/demo/*
    - Any other /v1/* endpoints

    Request State After Authentication:
    - request.state.user: Dict with user info from JWT claims
      {
          "clerk_user_id": "user_2abc...",
          "email": "user@example.com",
          "email_verified": true,
          "db_user_id": 123,
          "is_authenticated": true
      }
    - request.state.is_authenticated: bool
    """

    # Public routes that don't require authentication
    PUBLIC_PATHS: set[str] = {
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/v1/contact",
        "/v1/booking",
    }

    def __init__(self, app: ASGIApp) -> None:
        """Initialize Clerk authentication middleware.

        Args:
            app: FastAPI application instance
        """
        super().__init__(app)
        self.clerk_service = get_clerk_service()
        logger.info("ClerkAuthMiddleware initialized")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request through Clerk authentication.

        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain

        Returns:
            Response: Either error response (401) or result from next handler

        Process:
        1. Check if route is public (bypass auth)
        2. Extract Authorization header
        3. Validate Bearer token with Clerk
        4. Fetch user from database by clerk_user_id
        5. Attach user to request.state
        6. Call next handler
        """
        # Check if Clerk auth is enabled
        if not settings.enable_clerk_auth:
            logger.debug("Clerk auth disabled, bypassing middleware")
            request.state.is_authenticated = False
            return await call_next(request)

        # Get request path
        path = request.url.path

        # Allow public routes without authentication
        if path in self.PUBLIC_PATHS or path.startswith("/_"):
            logger.debug(f"Public route accessed: {path}")
            request.state.is_authenticated = False
            return await call_next(request)

        # Allow OPTIONS requests without authentication (CORS preflight)
        # OPTIONS requests are sent by browsers before actual requests
        # Let it pass through so CORSMiddleware can add proper headers
        if request.method == "OPTIONS":
            logger.debug(f"OPTIONS request bypassed: {path}")
            request.state.is_authenticated = False
            return await call_next(request)

        # Extract Authorization header
        # NOTE: When using Google Cloud API Gateway with backend authentication,
        # the original Authorization header is moved to X-Forwarded-Authorization
        # and replaced with the API Gateway's service account JWT.
        # We prefer X-Forwarded-Authorization if present (contains original Clerk JWT)

        # Log ALL headers for debugging (temporary)
        all_headers = dict(request.headers)
        # Mask sensitive values but show keys
        safe_headers = {k: f"{v[:30]}..." if len(v) > 30 else v for k, v in all_headers.items()}
        logger.warning(f"DEBUG ALL HEADERS: {safe_headers}")

        # Log all auth-related headers for debugging
        logger.info(
            f"Request headers - X-Forwarded-Authorization present: {bool(request.headers.get('X-Forwarded-Authorization'))}"
        )
        logger.info(
            f"Request headers - Authorization present: {bool(request.headers.get('Authorization'))}"
        )

        auth_header = request.headers.get("X-Forwarded-Authorization")
        if auth_header:
            logger.info("Using X-Forwarded-Authorization header (from API Gateway)")
        else:
            auth_header = request.headers.get("Authorization")
            if auth_header:
                logger.info("Using Authorization header (direct access)")

        if not auth_header:
            logger.warning(f"Missing Authorization header: path={path}")
            # DEBUG: Include header info in error response for troubleshooting
            debug_headers = {
                "x-forwarded-auth": bool(request.headers.get("X-Forwarded-Authorization")),
                "authorization": bool(request.headers.get("Authorization")),
                "all_keys": list(request.headers.keys()),
            }
            return self._unauthorized_response(
                f"Missing Authorization header. Debug: {debug_headers}"
            )

        # Validate Bearer token format
        if not auth_header.startswith("Bearer "):
            logger.warning("Invalid Authorization header format")
            return self._unauthorized_response(
                "Invalid Authorization header format. Expected: Bearer <token>"
            )

        # Extract token
        token = auth_header.split("Bearer ", 1)[1].strip()

        if not token:
            logger.warning("Empty Bearer token")
            return self._unauthorized_response("Empty Bearer token")

        # Verify token with Clerk
        claims, error = await self.clerk_service.verify_token(token)

        if error or not claims:
            logger.warning(f"Token verification failed: {error}")
            # DEBUG: Include token info (first 50 chars) for troubleshooting
            token_preview = token[:50] if token else "empty"
            return self._unauthorized_response(
                f"Authentication failed: {error}. Token starts with: {token_preview}..."
            )

        # Extract user info from JWT claims
        clerk_user_id = claims.get("sub")  # Clerk user ID
        email = claims.get("email")
        email_verified = claims.get("email_verified", False)

        if not clerk_user_id:
            logger.error("Token missing 'sub' claim")
            return self._unauthorized_response("Invalid token: missing user ID")

        # Note: Email should be included in JWT claims via Clerk JWT Template
        # If email is missing, JIT provisioning will be skipped but user can still access
        if not email:
            logger.warning(
                f"Email not in JWT claims for user {clerk_user_id}. "
                "Configure JWT Template in Clerk Dashboard to include email claim."
            )

        # Fetch user from database (optional - may not exist yet)
        # Pass email as fallback in case clerk_user_id changed
        db_user = await self.clerk_service.get_user_by_clerk_id(clerk_user_id, fallback_email=email)

        # JIT (Just-In-Time) Provisioning: Create user if authenticated in Clerk but not in DB
        # This automatically syncs users from Clerk to local database on first access
        if not db_user and email:
            logger.info(
                f"User authenticated in Clerk but not in database, creating user (JIT): {email}"
            )

            # Extract name from claims or use email as fallback
            full_name = claims.get("name", email.split("@")[0])

            # Create clerk_metadata from JWT claims
            clerk_metadata = {
                "public_metadata": claims.get("public_metadata", {}),
                "profile_image_url": claims.get("image_url"),
                "email_verified": email_verified,
            }

            # Sync user to database
            user_id, is_new, error = await self.clerk_service.sync_user_from_clerk(
                clerk_user_id=clerk_user_id,
                email=email,
                full_name=full_name,
                clerk_metadata=clerk_metadata,
            )

            if error:
                logger.error(f"Failed to create user via JIT provisioning: {error}")
                # Continue without DB user - user can still access
            else:
                logger.info(f"User created successfully via JIT provisioning: user_id={user_id}")
                # Fetch the newly created user
                db_user = await self.clerk_service.get_user_by_clerk_id(clerk_user_id)

        # Attach user info to request state
        # Derive full_name safely (email could be None)
        if db_user:
            full_name = db_user["full_name"]
        else:
            full_name = claims.get("name") or (email.split("@")[0] if email else "User")

        request.state.user = {
            "clerk_user_id": clerk_user_id,
            "email": email,
            "email_verified": email_verified,
            "db_user_id": db_user["id"] if db_user else None,
            "full_name": full_name,
            "is_active": db_user["is_active"] if db_user else True,
            "clerk_metadata": db_user.get("clerk_metadata", {}) if db_user else {},
            "preferred_language": db_user.get("preferred_language", "es") if db_user else "es",
            "is_authenticated": True,
        }
        request.state.is_authenticated = True

        logger.debug(
            f"User authenticated: clerk_user_id={clerk_user_id}, email={email}, path={path}"
        )

        # Check if user is active (if exists in DB)
        if db_user and not db_user["is_active"]:
            logger.warning(f"Inactive user attempted access: user_id={db_user['id']}")
            return self._forbidden_response("Account is inactive. Contact support for assistance.")

        # Proceed to next handler
        return await call_next(request)

    def _unauthorized_response(self, detail: str) -> JSONResponse:
        """Generate 401 Unauthorized response.

        Args:
            detail: Error message describing why auth failed.

        Returns:
            JSONResponse: 401 response with error details.
        """
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "success": False,
                "error": "Unauthorized",
                "message": detail,
                "hint": "Include a valid Bearer token in the Authorization header",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _forbidden_response(self, detail: str) -> JSONResponse:
        """Generate 403 Forbidden response.

        Args:
            detail: Error message describing why access is forbidden.

        Returns:
            JSONResponse: 403 response with error details.
        """
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "error": "Forbidden",
                "message": detail,
            },
        )


def get_current_user(request: Request) -> dict[str, Any] | None:
    """Extract current authenticated user from request state.

    Helper function for route handlers to access authenticated user.

    Args:
        request: FastAPI request object

    Returns:
        dict | None: User info if authenticated, None otherwise

    Usage in route handlers:
    ```python
    @app.post("/v1/protected")
    async def protected_route(request: Request):
        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user_id = user["db_user_id"]
        email = user["email"]
        # ... rest of handler
    ```
    """
    if not hasattr(request.state, "user"):
        return None

    if not request.state.is_authenticated:
        return None

    user: dict[str, Any] = request.state.user
    return user
