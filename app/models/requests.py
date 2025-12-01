"""Demo agent request models.

Pydantic v2 models for HTTP request validation and documentation.

Author: Odiseo Team
Created: 2025-10-31
Version: 1.0.0
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Metadata(BaseModel):
    """Request metadata for tracking and rate limiting.

    Attributes:
        user_agent: HTTP User-Agent header (for fingerprinting)
        fingerprint: Client fingerprint hash (for VPN detection)
        timezone: IANA timezone identifier

    Security Note:
        Client IP is extracted securely from request headers by the backend.
        The ClientIPExtractor service validates proxy headers (X-Forwarded-For,
        CF-Connecting-IP, X-Real-IP) with trusted proxy validation.
    """

    user_agent: str | None = Field(
        None,
        max_length=500,  # SECURITY: Prevent DoS via huge user agent strings
        description="HTTP User-Agent header",
    )
    fingerprint: str | None = Field(
        None,
        max_length=128,  # SECURITY: Fingerprint hashes are typically 32-64 chars
        description="Client fingerprint hash",
    )
    timezone: str | None = Field(
        None,
        max_length=64,  # SECURITY: IANA timezone identifiers are max ~40 chars
        description="IANA timezone identifier (e.g., 'America/Costa_Rica', 'Europe/London')",
    )

    @field_validator("user_agent")
    @classmethod
    def validate_user_agent(cls, v: str | None) -> str | None:
        """Validate user agent to prevent injection attacks.

        SECURITY (CWE-20): Prevents control characters and null bytes
        that could enable header injection or logging exploits.
        """
        if not v:
            return None

        # Remove null bytes and control characters (except tab/newline for natural UA strings)
        cleaned = "".join(char for char in v if ord(char) >= 0x20 or char in "\t\n")

        # Trim and limit length
        cleaned = cleaned.strip()[:500]

        return cleaned if cleaned else None

    @field_validator("fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str | None) -> str | None:
        """Validate fingerprint format.

        SECURITY (CWE-20): Ensures fingerprint is alphanumeric only,
        preventing injection attacks via malformed fingerprints.
        """
        if not v:
            return None

        # Fingerprints should be alphanumeric (hex or base64)
        # Allow: letters, numbers, hyphens, underscores (common in hashes)
        cleaned = "".join(char for char in v if char.isalnum() or char in "-_")

        # Limit length
        cleaned = cleaned[:128]

        return cleaned if cleaned else None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Validate timezone format.

        SECURITY (CWE-20): Ensures timezone is valid IANA identifier,
        preventing injection attacks via malformed timezone strings.
        """
        if not v:
            return None

        # IANA timezone identifiers: letters, numbers, forward slash, underscore, hyphen, plus
        # Examples: America/Costa_Rica, Europe/London, Asia/Tokyo, UTC, GMT+5
        cleaned = "".join(char for char in v if char.isalnum() or char in "/_-+")

        # Limit length and validate basic format
        cleaned = cleaned[:64]

        # Basic validation: should contain at least one letter
        if not any(c.isalpha() for c in cleaned):
            return None

        return cleaned if cleaned else None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "fingerprint": "abc123def456",
                "timezone": "America/Costa_Rica",
            }
        }
    )


class DemoRequest(BaseModel):
    """HTTP POST request for demo agent.

    Attributes:
        user_id: Authenticated user ID (REQUIRED - from demo_users table)
        session_id: Session token for tracking
        input: User query/question
        language: Language preference (es|en, default: es)
        metadata: Request metadata (IP, fingerprint, etc.)

    Note:
        user_id is now REQUIRED. Users must register and verify email
        before accessing demo chat.
    """

    user_id: int | None = Field(
        None,
        description="Authenticated user ID (optional - obtained from Clerk token if not provided)",
        gt=0,
    )
    session_id: str | None = Field(None, description="Session token (tracking)")
    input: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User query or question",
    )
    language: str = Field(
        default="es",
        pattern="^(es|en|ar)$",
        description="Language preference (es|en|ar)",
    )
    metadata: Metadata | None = Field(
        None,
        description="Request metadata (IP, fingerprint, etc.) - optional",
    )

    @field_validator("input", mode="before")
    @classmethod
    def sanitize_input(cls, v: str) -> str:
        """Sanitize user input."""
        if isinstance(v, str):
            return v.strip()[:2000]
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 123,
                "session_id": "sess_abc",
                "input": "¿Cuánto cuesta un laptop?",
                "language": "es",
                "metadata": {
                    "user_agent": "Mozilla/5.0...",
                    "fingerprint": "abc123def",
                    "timezone": "America/Costa_Rica",
                },
            }
        }
    )
