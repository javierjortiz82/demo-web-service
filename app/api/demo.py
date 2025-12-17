"""Demo Agent Routes.

Demo query endpoints with token-bucket rate limiting and quota management.

Author: Odiseo Team
Created: 2025-11-10
Version: 1.0.0
"""

import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.models.requests import DemoRequest
from app.models.responses import DemoResponse
from app.security.clerk_middleware import get_current_user
from app.services.client_ip_service import extract_client_ip
from app.utils.logging import get_logger
from app.utils.sanitizers import (
    sanitize_error_message,
    sanitize_html,
    sanitize_user_input,
)
from app.utils.validators import validate_session_id

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/demo", tags=["Demo"])


def get_services(request: Request) -> tuple[Any, Any]:
    """Get service instances from app state.

    Args:
        request: FastAPI request object.

    Returns:
        tuple: (demo_agent, user_service)

    Raises:
        HTTPException: If services are not initialized.
    """
    demo_agent = request.app.state.demo_agent
    user_service = request.app.state.user_service

    if not demo_agent or not user_service:
        raise HTTPException(status_code=500, detail="Services not initialized")

    return demo_agent, user_service


@router.post("", response_model=DemoResponse)
async def demo_query(request_data: DemoRequest, request: Request) -> DemoResponse | JSONResponse:
    """Process a demo query with token-bucket rate limiting.

    Args:
        request_data: Demo query request data.
        request: FastAPI request object.

    Returns:
        DemoResponse: Query result with token usage information.

    Raises:
        HTTPException: 401 if not authenticated, 500 on server error.
    """
    try:
        demo_agent, user_service = get_services(request)

        # STEP 1: Get authenticated user
        user_id = None

        if settings.enable_clerk_auth:
            authenticated_user = get_current_user(request)

            if authenticated_user and authenticated_user.get("is_authenticated"):
                if authenticated_user.get("db_user_id"):
                    user_id = authenticated_user["db_user_id"]
                    logger.info(f"Clerk authenticated user: {user_id}")
                else:
                    logger.warning(
                        f"Clerk user authenticated but not in database: {authenticated_user.get('email')}"
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success": False,
                            "error": "user_not_registered",
                            "message": "Your account is not fully set up yet. Please complete registration or try again in a moment.",
                            "hint": "If this persists, contact support with your email address.",
                        },
                    )
            elif request_data.user_id:
                user_id = request_data.user_id
                logger.info(f"User attempting access with user_id: {user_id}")
            else:
                logger.error("Authentication required: No Clerk token or user_id provided")
                return JSONResponse(
                    status_code=401,
                    content={
                        "success": False,
                        "error": "authentication_required",
                        "message": "Please log in to use this endpoint.",
                    },
                )
        else:
            user_id = request_data.user_id
            if not user_id:
                logger.warning("Auth disabled and no user_id provided - allowing anonymous access")
                user_id = None

        # STEP 2: Validate user exists and is active
        user_result = None
        user_email = None

        if user_id:
            user_query = """
                SELECT id, email, is_active, is_email_verified, is_suspended, is_deleted
                FROM :SCHEMA_NAME.demo_users
                WHERE id = %s
            """
            user_result = await user_service.db.execute_one(user_query, (user_id,))

            if not user_result:
                logger.warning(f"User ID {user_id} not found")
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "user_not_found",
                        "message": "User account not found. Please register first.",
                    },
                )

            if not user_result.get("is_active"):
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "account_not_active",
                        "message": "Your account is not active. Please verify your email address first.",
                    },
                )

            if not user_result.get("is_email_verified"):
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "email_not_verified",
                        "message": "Please verify your email address first.",
                    },
                )

            if user_result.get("is_suspended"):
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "account_suspended",
                        "message": "Your account has been suspended.",
                    },
                )

            if user_result.get("is_deleted"):
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "account_deleted",
                        "message": "Your account has been deleted.",
                    },
                )

            user_email = user_result.get("email")

        # STEP 3: Use user_id as user_key for token tracking
        # SECURITY FIX: Use 'is not None' to handle user_id=0 correctly (0 is falsy but valid)
        user_key = str(user_id) if user_id is not None else request_data.session_id or str(uuid4())

        # SECURITY: Validate or generate session_id
        if request_data.session_id:
            is_valid, error_msg = validate_session_id(request_data.session_id)
            if not is_valid:
                logger.warning(f"Invalid session_id format from user {user_id}: {error_msg}")
                session_id = str(uuid4())
            else:
                session_id = request_data.session_id
        else:
            session_id = str(uuid4())

        logger.info(f"Demo query from active user: {user_email} (ID: {user_id})")

        # SECURITY: Extract client IP
        client_ip = extract_client_ip(request)

        # Extract metadata
        user_agent = request_data.metadata.user_agent if request_data.metadata else None
        fingerprint = request_data.metadata.fingerprint if request_data.metadata else None
        user_timezone = request_data.metadata.timezone if request_data.metadata else None

        # SECURITY: Sanitize user input
        sanitized_input = sanitize_user_input(request_data.input, max_length=10000)

        if not sanitized_input:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_input",
                    "message": "Please provide a valid question.",
                },
            )

        # Process query
        start_time = time.time()

        response_text, tokens_used, warning, error_msg = await demo_agent.process_query(
            user_input=sanitized_input,
            user_key=user_key,
            language=request_data.language or "es",
            ip_address=client_ip,
            user_agent=user_agent,
            client_fingerprint=fingerprint,
            user_timezone=user_timezone,
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        if error_msg:
            status_code = 429 if "quota" in error_msg else 403
            try:
                user_status = await demo_agent.get_user_status(user_key)
                request.state.rate_limit_remaining = user_status.get("tokens_remaining", 0)
                request.state.rate_limit_used = user_status.get("tokens_used", 0)
                request.state.rate_limit_reset = user_status.get("next_reset")
            except Exception as e:
                logger.warning(f"Failed to get rate limit info for error response: {e}")

            return JSONResponse(
                status_code=status_code,
                content={
                    "success": False,
                    "error": (
                        "demo_quota_exceeded"
                        if "quota" in error_msg
                        else "suspicious_behavior_detected"
                    ),
                    "message": error_msg,
                    "retry_after_seconds": 86400 if "quota" in error_msg else 300,
                },
            )

        # SECURITY: Sanitize AI response
        sanitized_response = sanitize_html(response_text)

        # Get user status for rate limit headers
        user_status = await demo_agent.get_user_status(user_key)
        tokens_remaining_val = user_status.get("tokens_remaining", 0)
        tokens_used_val = user_status.get("tokens_used", 0)
        next_reset = user_status.get("next_reset")

        request.state.rate_limit_remaining = tokens_remaining_val
        request.state.rate_limit_used = tokens_used_val
        request.state.rate_limit_reset = next_reset

        # Store conversation history
        try:
            session_upsert_query = """
                INSERT INTO :SCHEMA_NAME.conversation_sessions
                    (id, customer_email, session_id, last_activity_at, metadata, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), %s, %s, NOW(), %s, NOW(), NOW())
                ON CONFLICT (session_id)
                DO UPDATE SET
                    last_activity_at = NOW(),
                    updated_at = NOW(),
                    customer_email = COALESCE(EXCLUDED.customer_email, conversation_sessions.customer_email),
                    metadata = COALESCE(EXCLUDED.metadata, conversation_sessions.metadata)
                RETURNING id
            """
            session_metadata = {
                "language": request_data.language or "es",
                "user_id": user_id,
            }
            session_result = await user_service.db.execute_one(
                session_upsert_query,
                (user_email, session_id, json.dumps(session_metadata)),
            )

            if session_result:
                session_uuid = session_result["id"]

                user_msg_query = """
                    INSERT INTO :SCHEMA_NAME.conversation_messages
                        (session_id, user_id, role, message_text, token_count, created_at)
                    VALUES
                        (%s, %s, 'user', %s, 0, NOW())
                """
                await user_service.db.execute(
                    user_msg_query, (session_uuid, user_id, sanitized_input)
                )

                ai_msg_query = """
                    INSERT INTO :SCHEMA_NAME.conversation_messages
                        (session_id, user_id, role, agent_name, message_text, token_count, response_time_ms, created_at)
                    VALUES
                        (%s, %s, 'model', %s, %s, %s, %s, NOW())
                """
                await user_service.db.execute(
                    ai_msg_query,
                    (
                        session_uuid,
                        user_id,
                        "demo",
                        sanitized_response,
                        tokens_used,
                        response_time_ms,
                    ),
                )

        except Exception as history_error:
            logger.error(f"Failed to store conversation history (non-critical): {history_error}")

        return DemoResponse(
            success=True,
            response=sanitized_response,
            tokens_used=tokens_used,
            tokens_remaining=tokens_remaining_val,
            warning=warning,
            session_id=session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in demo_query: {e}")
        safe_message = sanitize_error_message(e, include_details=False)
        raise HTTPException(status_code=500, detail=safe_message) from e


@router.get("/status", response_model=None)
async def demo_status(
    request: Request,
    user_id: int | None = Query(
        None, description="User ID (required for OTP users, optional for Clerk OAuth users)"
    ),
) -> dict[str, Any] | JSONResponse:
    """Get authenticated user's current quota status.

    Args:
        request: FastAPI request object.
        user_id: Optional user ID for OTP users.

    Returns:
        dict: Quota status information.
    """
    try:
        demo_agent, _ = get_services(request)

        final_user_id = None
        authenticated_user = get_current_user(request)

        # DEBUG: Log what we received
        has_state_user = hasattr(request.state, "user")
        is_auth = getattr(request.state, "is_authenticated", "not_set")
        logger.warning(
            f"DEBUG demo_status: has_state_user={has_state_user}, "
            f"is_authenticated={is_auth}, authenticated_user={authenticated_user}"
        )

        if authenticated_user and authenticated_user.get("db_user_id"):
            final_user_id = authenticated_user["db_user_id"]
        elif user_id:
            final_user_id = user_id
        else:
            # DEBUG: Include state info in response
            debug_info = {
                "has_state_user": has_state_user,
                "is_authenticated": str(is_auth),
                "db_user_id": authenticated_user.get("db_user_id") if authenticated_user else None,
                "clerk_user_id": authenticated_user.get("clerk_user_id") if authenticated_user else None,
                "email": authenticated_user.get("email") if authenticated_user else None,
            }
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "authentication_required",
                    "message": "Please log in to view quota status.",
                    "debug": debug_info,
                },
            )

        user_key = str(final_user_id)
        status: dict[str, Any] = await demo_agent.get_user_status(user_key)
        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in demo_status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/history", response_model=None)
async def get_demo_history(
    request: Request,
    limit: int = Query(100, description="Maximum number of messages to return"),
    user_id: int | None = Query(
        None, description="User ID (required for OTP users, optional for Clerk OAuth users)"
    ),
) -> dict[str, Any] | JSONResponse:
    """Retrieve user's complete conversation history.

    Args:
        request: FastAPI request object.
        limit: Maximum number of messages to return.
        user_id: Optional user ID for OTP users.

    Returns:
        dict: Chat history with messages.
    """
    try:
        _, user_service = get_services(request)

        final_user_id = None
        authenticated_user = get_current_user(request)

        if authenticated_user and authenticated_user.get("db_user_id"):
            final_user_id = authenticated_user["db_user_id"]
        elif user_id:
            final_user_id = user_id
        else:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "authentication_required",
                    "message": "Please log in to access chat history.",
                },
            )

        limit = min(max(1, limit), 500)

        messages_query = """
            SELECT
                cm.id,
                cm.role,
                cm.message_text,
                cm.token_count,
                cm.created_at
            FROM :SCHEMA_NAME.conversation_messages cm
            WHERE cm.user_id = %s
            ORDER BY cm.created_at ASC
            LIMIT %s
        """
        messages = await user_service.db.execute_all(messages_query, (final_user_id, limit))

        for msg in messages:
            if msg.get("created_at"):
                msg["created_at"] = msg["created_at"].isoformat()

        return {
            "success": True,
            "messages": messages,
            "total_messages": len(messages),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chat history") from e
