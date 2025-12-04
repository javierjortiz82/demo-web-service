"""Demo agent response models.

Pydantic v2 models for HTTP response validation and documentation.

Author: Odiseo Team
Created: 2025-10-31
Version: 1.0.0
"""

from pydantic import BaseModel, ConfigDict, Field


class TokenWarning(BaseModel):
    """Token limit warning information.

    Attributes:
        is_warning: Whether a warning should be displayed
        message: Warning message (None if no warning)
        percentage_used: Percentage of quota used (0-100)
    """

    is_warning: bool = Field(default=False, description="Whether warning should be displayed")
    message: str | None = Field(default=None, description="Warning message text")
    percentage_used: int = Field(default=0, ge=0, le=100, description="Percentage of quota used")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "is_warning": False,
                "message": None,
                "percentage_used": 5,
            }
        }
    )


class DemoResponse(BaseModel):
    """Successful demo agent HTTP response.

    Attributes:
        success: Always true for successful responses
        response: Generated response text from demo agent
        tokens_used: Tokens consumed by this request
        tokens_remaining: Tokens remaining in user's quota
        warning: Token limit warning information
        session_id: Session ID (for tracking)
        created_at: Timestamp when response was generated
    """

    success: bool = Field(default=True, description="Always true for successful responses")
    response: str = Field(..., description="Generated response text")
    tokens_used: int = Field(ge=0, description="Tokens used in this request")
    tokens_remaining: int = Field(ge=0, description="Tokens remaining in quota")
    warning: TokenWarning = Field(
        default_factory=lambda: TokenWarning(),
        description="Token limit warning information",
    )
    session_id: str = Field(..., description="Session ID for tracking")
    created_at: str = Field(..., description="ISO 8601 timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "response": "Los laptops varían entre $500 y $3000...",
                "tokens_used": 250,
                "tokens_remaining": 4750,
                "warning": {
                    "is_warning": False,
                    "message": None,
                    "percentage_used": 5,
                },
                "session_id": "sess_abc",
                "created_at": "2025-10-31T12:30:45Z",
            }
        }
    )


class ErrorResponse(BaseModel):
    """Standard error response for all API endpoints.

    Provides consistent error format across the entire API.

    Attributes:
        success: Always false for error responses
        error: Error code (snake_case identifier)
        message: Human-readable error message
        hint: Optional hint for resolving the error
        retry_after_seconds: Seconds to wait before retry (if applicable)
    """

    success: bool = Field(default=False, description="Always false for errors")
    error: str = Field(..., description="Error code (e.g., 'authentication_required')")
    message: str = Field(..., description="Human-readable error message")
    hint: str | None = Field(None, description="Optional hint for resolving the error")
    retry_after_seconds: int | None = Field(None, ge=0, description="Seconds to wait before retry")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "error": "authentication_required",
                "message": "Please log in to use this endpoint.",
                "hint": "Ensure your session is active and try again.",
                "retry_after_seconds": None,
            }
        }
    )


class DemoErrorResponse(ErrorResponse):
    """Error response specific to demo endpoints.

    Extends ErrorResponse with demo-specific fields.

    Attributes:
        blocked_until: ISO 8601 timestamp when user will be unblocked (if applicable)
    """

    blocked_until: str | None = Field(
        None, description="ISO 8601 timestamp when unblocked (if applicable)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "error": "demo_quota_exceeded",
                "message": "Demo bloqueada. Límite de 5,000 tokens alcanzado. Reintenta en 18 horas.",
                "hint": "Wait for quota reset or contact support.",
                "retry_after_seconds": 64800,
                "blocked_until": "2025-11-01T12:30:45Z",
            }
        }
    )


