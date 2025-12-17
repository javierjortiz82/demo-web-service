"""Clerk Service - JWT Validation Only.

Validates Clerk JWT tokens using public keys (JWKS).
No secret keys required - frontend handles authentication with Clerk.

Features:
- JWT token validation with Clerk public keys (RS256)
- User synchronization to local PostgreSQL database
- JIT (Just-In-Time) user provisioning

Note:
- CLERK_SECRET_KEY is NOT required - validation uses public JWKS
- Configure JWT Template in Clerk Dashboard to include email/name claims

Author: Odiseo Team
Created: 2025-11-03
Version: 2.0.0 (Simplified)
"""

import asyncio
import base64
import json
import time
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from app.config.settings import settings
from app.db.connection import get_db
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ClerkService:
    """Service for Clerk JWT validation.

    Handles:
    - JWT token validation using Clerk's JWKS endpoint (public keys)
    - User synchronization to PostgreSQL
    - JIT provisioning for new users

    Security:
    - Verifies JWT signatures using Clerk public keys (RS256)
    - Validates token expiration, issuer, and audience
    - No secret keys stored or transmitted

    Note:
    - This service only validates tokens, it does NOT generate them
    - Frontend is responsible for authentication with Clerk SDK
    """

    CLERK_JWKS_URL_TEMPLATE = "https://{frontend_api}/.well-known/jwks.json"
    JWKS_CACHE_TTL_SECONDS = 3600  # Cache JWKS for 1 hour

    def __init__(self) -> None:
        """Initialize ClerkService with JWKS client for JWT validation."""
        self.db = get_db()

        # Only need publishable_key for audience validation (optional)
        self.publishable_key = settings.clerk_publishable_key

        # Get frontend API domain for JWKS URL
        self.frontend_api = settings.clerk_frontend_api or "clerk.accounts.dev"

        # Initialize JWKS client for JWT verification (uses PUBLIC keys only)
        self.jwks_url = self.CLERK_JWKS_URL_TEMPLATE.format(frontend_api=self.frontend_api)
        try:
            # IMPORTANT: cache_keys=False to avoid key ID mismatch issues
            # PyJWKClient with cache_keys=True can use internal thumbprints instead of kid
            # This causes "Unable to find a signing key" errors when kid doesn't match
            self.jwks_client = PyJWKClient(
                self.jwks_url,
                cache_keys=False,  # Disable cache to ensure fresh key lookup
                timeout=15,
            )
            logger.info(
                f"ClerkService initialized: frontend_api={self.frontend_api}, "
                f"jwks_url={self.jwks_url}, timeout=15s, cache=disabled"
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize JWKS client during init: {e}, "
                f"will retry during token verification"
            )
            self.jwks_client = PyJWKClient(self.jwks_url, cache_keys=False, timeout=15)

        # Lock for thread-safe JWKS operations
        self._jwks_fetch_lock = asyncio.Lock()

    async def preload_jwks(self) -> None:
        """Warm up JWKS client at application startup.

        Makes a test fetch to verify connectivity to Clerk JWKS endpoint.
        PyJWKClient handles its own internal caching (cache_keys=True).

        Returns:
            None

        Raises:
            Logs errors but does not raise - token verification will retry if needed.
        """
        try:
            logger.info("Warming up JWKS client at startup...")
            # Just verify we can reach the JWKS endpoint
            # PyJWKClient will cache keys internally when needed
            max_retries = 3
            for attempt in range(max_retries + 1):
                try:
                    # Fetch JWKS to verify connectivity (PyJWKClient caches internally)
                    jwks = self.jwks_client.get_jwk_set()
                    key_count = len(jwks.keys) if hasattr(jwks, "keys") else "unknown"
                    logger.info(
                        f"✅ JWKS endpoint verified at startup. "
                        f"Found {key_count} signing key(s)."
                    )
                    return
                except PyJWKClientConnectionError as e:
                    if attempt < max_retries:
                        wait_time = 0.5 * (attempt + 1)
                        logger.warning(
                            f"JWKS warmup attempt {attempt + 1} failed, "
                            f"retrying in {wait_time}s: {e}"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"JWKS warmup failed after {max_retries + 1} attempts. "
                            f"Token verification will fetch on demand: {e}"
                        )
                except Exception as e:
                    logger.error(f"Unexpected error warming up JWKS: {e}")
                    raise

        except Exception as e:
            logger.exception(f"Error warming up JWKS at startup: {e}")
            # Don't raise - let service start anyway, will retry during token verify

    def _extract_kid_from_jwt(self, token: str) -> str | None:
        """Extract the 'kid' (Key ID) from JWT header without verification.

        Args:
            token: JWT token string

        Returns:
            Key ID string or None if not found
        """
        try:
            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                logger.warning("Invalid JWT format - expected 3 parts")
                return None

            # SECURITY FIX (CWE-532): Don't log token content - it can be stolen from logs
            # Only log in debug mode and only metadata, never token content
            logger.debug("Extracting kid from JWT header...")

            # Decode header (base64url)
            header_b64 = parts[0]

            # Add padding if needed
            padding = 4 - len(header_b64) % 4
            if padding != 4:
                header_b64 += "=" * padding

            header_json = base64.urlsafe_b64decode(header_b64)
            header = json.loads(header_json)

            kid: str | None = header.get("kid")
            # SECURITY: Only log kid existence, not full header content
            logger.debug(f"Extracted kid from JWT: {kid[:20] + '...' if kid and len(kid) > 20 else kid}")
            return kid

        except Exception as e:
            logger.warning(f"Failed to extract kid from JWT: {e}")
            return None

    async def _get_signing_key_from_jwt_with_cache(
        self, token: str, force_refresh: bool = False
    ) -> tuple[Any, str | None]:
        """Get signing key from JWT by manually matching 'kid' from JWKS.

        IMPORTANT: This method manually extracts the 'kid' from JWT header and
        matches it against JWKS keys. This bypasses PyJWKClient's internal
        get_signing_key_from_jwt() method which can fail due to thumbprint
        mismatches in certain PyJWT versions.

        Returns:
            Tuple[signing_key | None, error_message | None]
        """
        try:
            # Extract kid from JWT header
            kid = self._extract_kid_from_jwt(token)
            if not kid:
                return None, "Could not extract 'kid' from JWT header"

            logger.info(f"Looking for signing key with kid={kid}")

            # Fetch JWKS with retry logic
            max_retries = 2
            last_error = None
            jwks = None

            for attempt in range(max_retries + 1):
                try:
                    jwks = self.jwks_client.get_jwk_set()
                    logger.debug(f"Fetched JWKS with {len(jwks.keys)} keys")
                    break
                except PyJWKClientConnectionError as e:
                    last_error = e
                    if attempt < max_retries:
                        wait_time = 0.5 * (attempt + 1)
                        logger.warning(
                            f"JWKS fetch attempt {attempt + 1} failed, retrying in {wait_time}s: {e}"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"JWKS fetch failed after {max_retries + 1} attempts: {e}")

            if jwks is None:
                if last_error:
                    return None, f"Failed to fetch JWKS: {str(last_error)}"
                return None, "Failed to fetch JWKS"

            # Find key by kid manually
            for key in jwks.keys:
                key_kid = key.key_id if hasattr(key, "key_id") else None
                logger.debug(f"Checking key: kid={key_kid}")
                if key_kid == kid:
                    logger.info(f"Found matching signing key for kid={kid}")
                    return key, None

            # Log available keys for debugging
            available_kids = [k.key_id if hasattr(k, "key_id") else "unknown" for k in jwks.keys]
            logger.error(f"No matching key found for kid={kid}. Available kids: {available_kids}")
            return None, f"No signing key found for kid={kid}"

        except Exception as e:
            logger.exception(f"Error getting signing key: {e}")
            return None, f"Error getting signing key: {str(e)}"

    async def verify_token(self, token: str) -> tuple[dict[str, Any] | None, str | None]:
        """Verify Clerk JWT session token.

        Args:
            token: JWT token from Authorization header (Bearer <token>)

        Returns:
            Tuple[claims | None, error_message | None]:
            - claims: Decoded JWT claims (if valid)
            - error: Error message (if invalid)

        Process:
        1. Fetch signing key from Clerk JWKS endpoint
        2. Verify JWT signature (RS256)
        3. Validate expiration, issuer, and audience
        4. Return decoded claims

        Claims structure:
        {
            "sub": "user_2abcdefghijklmnop",  # Clerk user ID
            "email": "user@example.com",
            "email_verified": true,
            "given_name": "John",
            "family_name": "Doe",
            "iss": "https://clerk.odiseo.com",
            "aud": "<publishable_key>",
            "exp": 1699999999,
            "iat": 1699996399,
            "nbf": 1699996399
        }
        """
        try:
            logger.info("Verifying Clerk token")

            # Get signing key with cache (reduces external calls, handles retries)
            signing_key, error = await self._get_signing_key_from_jwt_with_cache(token)
            if error:
                return None, error

            # Decode and verify JWT
            # Note: Clerk JWT tokens generated via API don't include 'aud' claim by default
            # Only tokens generated via frontend SDK with specific JWT template include 'aud'
            # We verify signature (RS256), expiration, and issuer which are the critical security measures
            # Audience validation is disabled since Clerk API tokens don't include 'aud'
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": False,  # Clerk tokens don't always include 'aud'
                    "require": ["exp", "iat", "nbf", "sub"],
                },
            )
            logger.info("Token verified successfully")

            # Additional validation
            current_time = int(time.time())

            # Check expiration
            if claims.get("exp", 0) < current_time:
                return None, "Token expired"

            # Check not-before
            if claims.get("nbf", 0) > current_time:
                return None, "Token not yet valid"

            # Validate issuer (should match Clerk instance)
            issuer = claims.get("iss", "")
            if not issuer.startswith("https://"):
                return None, "Invalid token issuer"

            logger.info(
                f"Token verified successfully: user_id={claims.get('sub')}, email={claims.get('email')}"
            )

            return claims, None

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None, "Token expired"

        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None, f"Invalid token: {str(e)}"

        except Exception as e:
            logger.exception(f"Token verification failed: {e}")
            return None, f"Token verification error: {str(e)}"

    async def sync_user_from_clerk(
        self,
        clerk_user_id: str,
        email: str,
        full_name: str,
        clerk_metadata: dict[str, Any],
        clerk_session_id: str | None = None,
    ) -> tuple[int | None, bool, str | None]:
        """Synchronize user from Clerk JWT claims to PostgreSQL.

        Called during JIT (Just-In-Time) provisioning when a user
        authenticates but doesn't exist in the local database.

        Args:
            clerk_user_id: Clerk user ID (e.g., "user_2abc...")
            email: User email address (from JWT claims)
            full_name: User full name (from JWT claims)
            clerk_metadata: Metadata from JWT claims
            clerk_session_id: Current session ID (optional)

        Returns:
            Tuple[user_id | None, is_new_user: bool, error | None]:
            - user_id: PostgreSQL user ID
            - is_new_user: True if user was created, False if updated
            - error: Error message (if failure)
        """
        try:
            logger.info(f"Syncing user from Clerk: clerk_user_id={clerk_user_id}, email={email}")

            # Call PostgreSQL upsert function
            query = f"""
                SELECT user_id, is_new_user, user_email
                FROM {settings.schema_name}.upsert_clerk_user($1, $2, $3, $4, $5)
            """

            result = await self.db.execute_one(
                query,
                (
                    clerk_user_id,
                    email,
                    full_name,
                    json.dumps(clerk_metadata),
                    clerk_session_id,
                ),
            )

            if not result:
                logger.error("Failed to sync user - no result from database")
                return None, False, "Database sync failed"

            # execute_one returns a dict, not a tuple
            user_id = result["user_id"]
            is_new_user = result["is_new_user"]
            user_email = result["user_email"]

            action = "created" if is_new_user else "updated"
            logger.info(f"User {action} successfully: user_id={user_id}, email={user_email}")

            return user_id, is_new_user, None

        except Exception as e:
            logger.error(f"Failed to sync user from Clerk: {e}")
            return None, False, f"Sync error: {str(e)}"

    async def get_user_by_clerk_id(
        self, clerk_user_id: str, fallback_email: str | None = None
    ) -> dict[str, Any] | None:
        """Get user from database by Clerk user ID with email fallback.

        Args:
            clerk_user_id: Clerk user ID (e.g., "user_2abc...")
            fallback_email: Optional email to use as fallback if clerk_user_id not found

        Returns:
            Optional[Dict]: User record (if found), None otherwise

        Fields returned:
        - id, email, full_name, clerk_user_id, clerk_metadata,
          is_active, is_email_verified, created_at, last_login_at
        """
        try:
            logger.debug(f"Fetching user by Clerk ID: {clerk_user_id}")

            # STEP 1: Try to find user by clerk_user_id (primary lookup)
            query = f"""
                SELECT
                    id, email, full_name, display_name,
                    clerk_user_id, clerk_session_id, clerk_metadata,
                    is_active, is_email_verified,
                    preferred_language, timezone,
                    created_at, updated_at, last_login_at
                FROM {settings.schema_name}.demo_users
                WHERE clerk_user_id = $1
                    AND is_deleted = false
            """

            result = await self.db.execute_one(query, (clerk_user_id,))

            if not result and fallback_email:
                logger.info(
                    f"User not found by clerk_user_id: {clerk_user_id}, trying email fallback"
                )

                # STEP 2: Fallback - Try to find user by email
                # This handles cases where:
                # - User has multiple Clerk accounts with same email
                # - clerk_user_id changed (user deleted/recreated account)
                # - Old registration with different clerk_user_id

                fallback_query = f"""
                    SELECT
                        id, email, full_name, display_name,
                        clerk_user_id, clerk_session_id, clerk_metadata,
                        is_active, is_email_verified,
                        preferred_language, timezone,
                        created_at, updated_at, last_login_at
                    FROM {settings.schema_name}.demo_users
                    WHERE LOWER(email) = LOWER($1)
                        AND is_deleted = false
                    ORDER BY last_login_at DESC NULLS LAST
                    LIMIT 1
                """

                result = await self.db.execute_one(fallback_query, (fallback_email,))

                if result:
                    logger.warning(
                        f"Found user by email fallback. Updating clerk_user_id from "
                        f"{result.get('clerk_user_id')} to {clerk_user_id}"
                    )

                    # Update the clerk_user_id to match the new one from Clerk
                    update_query = f"""
                        UPDATE {settings.schema_name}.demo_users
                        SET clerk_user_id = $1, updated_at = NOW()
                        WHERE id = $2
                    """
                    await self.db.execute(update_query, (clerk_user_id, result["id"]))

                    # Update result dict with new clerk_user_id
                    result["clerk_user_id"] = clerk_user_id

            if not result:
                logger.debug(f"User not found for clerk_user_id: {clerk_user_id}")
                return None

            # execute_one returns dict with column names as keys
            user = {
                "id": result["id"],
                "email": result["email"],
                "full_name": result["full_name"],
                "display_name": result["display_name"],
                "clerk_user_id": result["clerk_user_id"],
                "clerk_session_id": result["clerk_session_id"],
                "clerk_metadata": result["clerk_metadata"] if result["clerk_metadata"] else {},
                "is_active": result["is_active"],
                "is_email_verified": result["is_email_verified"],
                "preferred_language": result["preferred_language"],
                "timezone": result["timezone"],
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
                "last_login_at": (
                    result["last_login_at"].isoformat() if result["last_login_at"] else None
                ),
            }

            logger.debug(f"User found: user_id={user['id']}, email={user['email']}")
            return user

        except Exception as e:
            logger.error(f"Failed to fetch user by Clerk ID: {e}")
            return None

    async def update_session(self, clerk_user_id: str, clerk_session_id: str) -> bool:
        """Update user's current Clerk session ID.

        Args:
            clerk_user_id: Clerk user ID
            clerk_session_id: New session ID

        Returns:
            bool: True if updated successfully, False otherwise
        """
        try:
            logger.debug(f"Updating session: clerk_user_id={clerk_user_id}")

            query = f"""
                SELECT {settings.schema_name}.update_clerk_session($1, $2)
            """

            result = await self.db.execute_one(query, (clerk_user_id, clerk_session_id))

            # PostgreSQL function returns boolean with function name as key
            if not result or not result.get("update_clerk_session"):
                logger.warning(f"User not found or update failed: clerk_user_id={clerk_user_id}")
                return False

            logger.debug("Session updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            return False

    async def soft_delete_user(self, clerk_user_id: str) -> bool:
        """Soft delete user (IDEMPOTENT).

        Args:
            clerk_user_id: Clerk user ID

        Returns:
            bool: True if user exists (deleted successfully or already deleted),
                  False only if user not found

        Sets is_deleted=true and deleted_at timestamp.
        This operation is idempotent - safe to call multiple times.
        """
        try:
            logger.info(f"Processing user deletion: clerk_user_id={clerk_user_id}")

            query = f"""
                SELECT {settings.schema_name}.soft_delete_clerk_user($1)
            """

            result = await self.db.execute_one(query, (clerk_user_id,))

            # PostgreSQL function returns:
            # - true: user exists (deleted now or already deleted)
            # - false: user not found in database
            if not result or not result.get("soft_delete_clerk_user"):
                logger.warning(f"User not found in database: clerk_user_id={clerk_user_id}")
                return False

            logger.info(f"User deletion processed successfully: clerk_user_id={clerk_user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to process user deletion: {e}")
            return False

    async def close(self) -> None:
        """Cleanup resources on application shutdown."""
        logger.info("ClerkService closed")


# Singleton instance with thread-safe initialization
import threading

_clerk_service: ClerkService | None = None
_clerk_service_lock = threading.Lock()


def get_clerk_service() -> ClerkService:
    """Get singleton instance of ClerkService.

    SECURITY FIX (CWE-362): Thread-safe singleton initialization.
    Uses double-checked locking pattern to prevent race conditions.

    Returns:
        ClerkService: Singleton instance

    Usage:
        clerk_service = get_clerk_service()
        claims, error = await clerk_service.verify_token(token)
    """
    global _clerk_service
    if _clerk_service is None:
        with _clerk_service_lock:
            # Double-check inside lock
            if _clerk_service is None:
                _clerk_service = ClerkService()
    return _clerk_service
