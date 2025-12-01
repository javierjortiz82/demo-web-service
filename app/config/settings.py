"""Application configuration using Pydantic v2 Settings.

Manages demo limits, rate-limiting, security settings, and database connection
loaded from environment variables.

Author: Odiseo Team
Version: 2.0.0
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ========================================================================
    # Database Configuration
    # ========================================================================
    database_url: str = Field(
        default="postgresql://mcp_user:mcp_password@localhost:5434/mcpdb",
        alias="DATABASE_URL",
    )
    schema_name: str = Field(default="test", alias="SCHEMA_NAME")

    # ========================================================================
    # Google Cloud / Vertex AI Configuration
    # ========================================================================
    gcp_project_id: str = Field(default="", alias="GCP_PROJECT_ID")
    gcp_location: str = Field(default="us-central1", alias="GCP_LOCATION")
    google_application_credentials: str = Field(
        default="",
        alias="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to Google Cloud service account JSON file",
    )
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    model: str = Field(default="gemini-2.5-flash", alias="MODEL")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, alias="TEMPERATURE")
    max_output_tokens: int = Field(default=2048, gt=0, alias="MAX_OUTPUT_TOKENS")

    # ========================================================================
    # Demo Limits Configuration
    # ========================================================================
    demo_max_tokens: int = Field(default=5000, gt=0, alias="DEMO_MAX_TOKENS")
    demo_cooldown_hours: int = Field(default=24, ge=1, le=168, alias="DEMO_COOLDOWN_HOURS")
    demo_warning_threshold: int = Field(default=85, ge=1, le=100, alias="DEMO_WARNING_THRESHOLD")

    # ========================================================================
    # Server Configuration
    # ========================================================================
    host: str = Field(default="0.0.0.0", alias="DEMO_AGENT_HOST")
    port: int = Field(default=8082, ge=1, le=65535, alias="DEMO_AGENT_PORT")

    # ========================================================================
    # Security Configuration
    # ========================================================================
    enable_fingerprint: bool = Field(default=True, alias="ENABLE_FINGERPRINT")
    fingerprint_score_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, alias="FINGERPRINT_SCORE_THRESHOLD"
    )

    # ========================================================================
    # Clerk Authentication Configuration
    # Note: Only CLERK_FRONTEND_API and CLERK_PUBLISHABLE_KEY are required
    #       for JWT validation. Secret keys are NOT needed.
    # ========================================================================
    clerk_publishable_key: str = Field(
        default="",
        alias="CLERK_PUBLISHABLE_KEY",
        description="Optional: Used for audience validation in JWT",
    )
    clerk_frontend_api: str = Field(
        default="clerk.accounts.dev",
        alias="CLERK_FRONTEND_API",
        description="Required: Clerk instance domain for JWKS endpoint",
    )
    enable_clerk_auth: bool = Field(default=True, alias="ENABLE_CLERK_AUTH")

    # ========================================================================
    # CORS Configuration
    # ========================================================================
    cors_allow_origins: str = Field(
        default="http://localhost:8080,http://localhost:3000",
        alias="CORS_ALLOW_ORIGINS",
    )
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")
    cors_allow_methods: str = Field(default="*", alias="CORS_ALLOW_METHODS")
    cors_allow_headers: str = Field(default="*", alias="CORS_ALLOW_HEADERS")

    # ========================================================================
    # Rate Limiting Configuration
    # ========================================================================
    ip_rate_limit_requests: int = Field(default=100, gt=0, alias="IP_RATE_LIMIT_REQUESTS")
    ip_rate_limit_window_sec: int = Field(default=60, gt=0, alias="IP_RATE_LIMIT_WINDOW_SEC")

    # ========================================================================
    # Proxy & IP Extraction Configuration
    # ========================================================================
    trusted_proxies: str = Field(default="", alias="TRUSTED_PROXIES")
    enable_proxy_headers: bool = Field(default=True, alias="ENABLE_PROXY_HEADERS")
    proxy_depth: int = Field(default=1, ge=0, alias="PROXY_DEPTH")
    use_cloudflare: bool = Field(default=False, alias="USE_CLOUDFLARE")

    # ========================================================================
    # Logging Configuration
    # ========================================================================
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_to_file: bool = Field(default=True, alias="LOG_TO_FILE")
    log_dir: Path = Field(default=Path("logs"), alias="LOG_DIR")
    log_console_enabled: bool = Field(default=True, alias="LOG_CONSOLE_ENABLED")
    log_json_format: bool = Field(default=True, alias="LOG_JSON_FORMAT")
    log_file_max_mb: int = Field(default=10, ge=1, le=100, alias="LOG_FILE_MAX_MB")
    log_file_backup_count: int = Field(default=5, ge=1, le=20, alias="LOG_FILE_BACKUP_COUNT")

    # ========================================================================
    # Validators
    # ========================================================================

    @property
    def is_debug(self) -> bool:
        """Check if debug mode is enabled (LOG_LEVEL == DEBUG)."""
        return self.log_level == "DEBUG"

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = v.upper().strip()
        if normalized not in valid_levels:
            return "INFO"
        return normalized

    @field_validator("log_dir", mode="before")
    @classmethod
    def ensure_log_dir_path(cls, v: str | Path) -> Path:
        """Ensure log_dir is a Path object."""
        return Path(v) if isinstance(v, str) else v

    @field_validator("google_api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate Google API key format (optional when using Vertex AI)."""
        if v and not v.startswith("AIza"):
            return ""  # Invalid key, treat as empty
        return v

    @field_validator("clerk_publishable_key", mode="before")
    @classmethod
    def validate_clerk_publishable_key(cls, v: str) -> str:
        """Validate Clerk publishable key format (optional)."""
        if v and not (v.startswith("pk_test_") or v.startswith("pk_live_")):
            return ""
        return v


# Singleton instance
settings = Settings()
