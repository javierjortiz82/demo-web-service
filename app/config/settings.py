"""Application configuration using Pydantic v2 Settings.

Manages demo limits, rate-limiting, security settings, and database connection
loaded from environment variables.

Author: Odiseo Team
Version: 2.0.0
"""

from pathlib import Path
from typing import Any

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
        default="",  # SECURITY: No default credentials - must be set via environment
        alias="DATABASE_URL",
        description="PostgreSQL connection URL (required)",
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
    # Estimated tokens per request for quota pre-check
    demo_tokens_per_request: int = Field(
        default=100,
        gt=0,
        le=1000,
        alias="DEMO_TOKENS_PER_REQUEST",
        description="Estimated tokens per request for quota pre-check",
    )
    # Abuse score threshold for blocking (0.0-1.0)
    abuse_score_block_threshold: float = Field(
        default=0.9,
        ge=0.5,
        le=1.0,
        alias="ABUSE_SCORE_BLOCK_THRESHOLD",
        description="Abuse score above which requests are blocked",
    )

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
    # IP suspicion thresholds
    ip_suspicious_req_per_min: int = Field(
        default=5,
        gt=0,
        alias="IP_SUSPICIOUS_REQ_PER_MIN",
        description="Requests per minute threshold for suspicious IP detection",
    )
    ip_suspicious_unique_users: int = Field(
        default=10,
        gt=0,
        alias="IP_SUSPICIOUS_UNIQUE_USERS",
        description="Unique users threshold for suspicious IP detection",
    )

    # ========================================================================
    # Concurrency Configuration
    # ========================================================================
    # Number of Uvicorn workers (processes). Each worker handles requests independently.
    # Recommended: 2-4 for most deployments, up to CPU cores for high load.
    uvicorn_workers: int = Field(
        default=4,
        ge=1,
        le=32,
        alias="UVICORN_WORKERS",
        description="Number of Uvicorn worker processes",
    )

    # Maximum concurrent Gemini API calls per worker.
    # This limits the ThreadPoolExecutor size for non-blocking API calls.
    # Total concurrent = UVICORN_WORKERS × MAX_CONCURRENT_REQUESTS
    # Example: 4 workers × 10 = 40 max concurrent Gemini API calls
    max_concurrent_requests: int = Field(
        default=10,
        ge=1,
        le=100,
        alias="MAX_CONCURRENT_REQUESTS",
        description="Max concurrent Gemini API calls per worker (ThreadPool size)",
    )

    # ========================================================================
    # Database Pool Configuration
    # ========================================================================
    # Minimum number of connections to keep in the pool per worker.
    # These connections are pre-established and ready for immediate use.
    db_pool_min_size: int = Field(
        default=5,
        ge=1,
        le=50,
        alias="DB_POOL_MIN_SIZE",
        description="Minimum database connections per worker",
    )

    # Maximum number of connections allowed in the pool per worker.
    # Total DB connections = UVICORN_WORKERS × DB_POOL_MAX_SIZE
    # Ensure PostgreSQL max_connections >= total connections + overhead
    db_pool_max_size: int = Field(
        default=20,
        ge=1,
        le=100,
        alias="DB_POOL_MAX_SIZE",
        description="Maximum database connections per worker",
    )

    # Connection timeout in seconds for database queries.
    db_command_timeout: int = Field(
        default=60,
        ge=5,
        le=300,
        alias="DB_COMMAND_TIMEOUT",
        description="Database query timeout in seconds",
    )
    # Maximum time (seconds) an idle connection can stay in pool before being closed.
    # Helps prevent stale connections and reduces memory usage.
    db_pool_max_inactive_lifetime: float = Field(
        default=300.0,
        ge=60.0,
        le=3600.0,
        alias="DB_POOL_MAX_INACTIVE_LIFETIME",
        description="Max seconds idle connection stays in pool",
    )

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

    @field_validator("db_pool_max_size", mode="after")
    @classmethod
    def validate_pool_sizes(cls, v: int, info: Any) -> int:
        """Validate db_pool_max_size >= db_pool_min_size."""
        # Access other field values through info.data
        min_size = info.data.get("db_pool_min_size", 5)
        if v < min_size:
            raise ValueError(f"db_pool_max_size ({v}) must be >= db_pool_min_size ({min_size})")
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database_url is provided."""
        if not v or not v.strip():
            raise ValueError("DATABASE_URL is required. Set it in your .env file or environment.")
        return v

    @field_validator("schema_name", mode="after")
    @classmethod
    def validate_schema_name(cls, v: str) -> str:
        """Validate schema_name to prevent SQL injection.

        SECURITY (CWE-89): Schema name is used in SQL queries via f-string
        formatting. We must ensure it only contains safe characters.

        Allowed: lowercase letters, numbers, underscores (PostgreSQL identifiers)
        """
        import re

        if not v:
            return "public"  # Safe default

        # PostgreSQL identifier rules: start with letter/underscore, alphanumeric/underscore
        if not re.match(r"^[a-z_][a-z0-9_]*$", v.lower()):
            raise ValueError(
                f"Invalid schema_name '{v}'. Must be a valid PostgreSQL identifier "
                "(lowercase letters, numbers, underscores only, start with letter/underscore)."
            )

        # Additional safety: limit length and block known dangerous patterns
        if len(v) > 63:  # PostgreSQL max identifier length
            raise ValueError("schema_name must be 63 characters or less")

        # Block SQL keywords that could be used for injection
        dangerous_keywords = {"select", "insert", "update", "delete", "drop", "union", "exec"}
        if v.lower() in dangerous_keywords:
            raise ValueError(f"schema_name cannot be a SQL keyword: {v}")

        return v.lower()


# Singleton instance
settings = Settings()
