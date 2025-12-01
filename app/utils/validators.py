"""Security-hardened validators for user input.

Provides validators that are immune to ReDoS (Regular Expression Denial of Service)
and other input-based attacks.

Author: Odiseo Team
Created: 2025-11-07
Version: 1.1.0 (Optimized)
"""

import uuid


def validate_session_id(session_id: str) -> tuple[bool, str | None]:
    """Validate session ID is a properly formatted UUID.

    SECURITY (CWE-384 mitigation): Prevents session fixation by ensuring
    session IDs are valid UUIDs (not arbitrary user-controlled strings).

    Args:
        session_id: Session identifier to validate.

    Returns:
        Tuple of (is_valid, error_message).

    Examples:
        >>> validate_session_id("550e8400-e29b-41d4-a716-446655440000")
        (True, None)

        >>> validate_session_id("not-a-uuid")
        (False, "Invalid session ID format")
    """
    if not session_id or not isinstance(session_id, str):
        return False, "Session ID is required"

    # Length check (UUID is 36 chars with hyphens)
    if len(session_id) != 36:
        return False, "Invalid session ID length"

    # Try parsing as UUID
    try:
        uuid_obj = uuid.UUID(session_id)

        # Verify it's version 4 (random UUID)
        # Version 4 UUIDs are cryptographically random and safe
        if uuid_obj.version != 4:
            return False, "Session ID must be UUID version 4"

        return True, None
    except ValueError:
        return False, "Invalid session ID format"
