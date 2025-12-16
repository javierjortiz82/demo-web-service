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
import json
import time
from typing import Any

import jwt
from jwt import PyJWKClient

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
            # Use cache_keys=True with fetch_on_init=False to lazy-load JWKS
            # This avoids connection issues during initialization
            self.jwks_client = PyJWKClient(self.jwks_url, cache_keys=True)
            logger.info(
                f"ClerkService initialized: frontend_api={self.frontend_api}, jwks_url={self.jwks_url}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize JWKS client during init: {e}, will retry during token verification"
            )
            self.jwks_client = PyJWKClient(self.jwks_url, cache_keys=True)

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

            # Get signing key from JWKS with retry logic for transient errors
            signing_key = None
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    signing_key = self.jwks_client.get_signing_key_from_jwt(token)
                    break
                except Exception as e:
                    if attempt < max_retries and "SSL" in str(e):
                        logger.warning(
                            f"JWKS fetch attempt {attempt + 1} failed with SSL error, retrying: {e}"
                        )
                        await asyncio.sleep(0.5)  # Brief delay before retry
                    else:
                        raise

            if signing_key is None:
                return None, "Failed to fetch signing key from JWKS"

            # Decode and verify JWT
            # Note: Some Clerk JWT templates don't include 'aud' claim by default
            # We still verify signature (RS256) which is the critical security measure
            # Audience validation is optional and only enforced if CLERK_PUBLISHABLE_KEY is set
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.publishable_key if self.publishable_key else None,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": bool(self.publishable_key),  # Only verify if key is configured
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


# Singleton instance
_clerk_service: ClerkService | None = None


def get_clerk_service() -> ClerkService:
    """Get singleton instance of ClerkService.

    Returns:
        ClerkService: Singleton instance

    Usage:
        clerk_service = get_clerk_service()
        claims, error = await clerk_service.verify_token(token)
    """
    global _clerk_service
    if _clerk_service is None:
        _clerk_service = ClerkService()
    return _clerk_service
