"""Structured JSON logging configuration using structlog with rotation.

Combines structlog for structured logging with security-hardened
sensitive data sanitization (CWE-532 mitigation).

Author: Odiseo Team
Version: 3.0.0
"""

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

from app.config.settings import settings

# ============================================================================
# SENSITIVE DATA SANITIZATION (CWE-532 mitigation)
# ============================================================================

SENSITIVE_PATTERNS: dict[str, tuple[str, str]] = {
    "jwt": (r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "[JWT_REDACTED]"),
    "bearer_token": (r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [TOKEN_REDACTED]"),
    "api_key_generic": (
        r'\b(?:api[_-]?key|apikey)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-]{20,})',
        r"api_key=[API_KEY_REDACTED]",
    ),
    "google_api_key": (r"\bAIza[A-Za-z0-9_\-]{35}", "[GOOGLE_API_KEY_REDACTED]"),
    "clerk_secret": (r"\bsk_(?:test|live)_[A-Za-z0-9]{40,}", "[CLERK_SECRET_REDACTED]"),
    "webhook_secret": (r"\bwhsec_[A-Za-z0-9]{40,}", "[WEBHOOK_SECRET_REDACTED]"),
    "email": (r"\b([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", r"\1***@\2"),
    "ipv4": (r"\b(\d{1,3}\.\d{1,3}\.)\d{1,3}\.\d{1,3}\b", r"\1***.***"),
    "password": (
        r'(?i)(?:password|passwd|pwd)["\']?\s*[:=]\s*["\']?([^\s"\']+)',
        r"password=[PASSWORD_REDACTED]",
    ),
    "db_connection": (r"postgresql://([^:]+):([^@]+)@", r"postgresql://[USER]:[PASSWORD]@"),
}


def sanitize_for_logging(message: Any) -> str:
    """Sanitize sensitive data from log messages."""
    if isinstance(message, dict):
        sanitized = {}
        for key, value in message.items():
            safe_key = sanitize_for_logging(str(key))
            if isinstance(value, dict | list):
                sanitized[safe_key] = sanitize_for_logging(value)
            else:
                sanitized[safe_key] = sanitize_for_logging(str(value))
        message = str(sanitized)
    elif isinstance(message, list):
        message = str([sanitize_for_logging(item) for item in message])
    else:
        message = str(message)

    for _pattern_name, (regex, replacement) in SENSITIVE_PATTERNS.items():
        message = re.sub(regex, replacement, message, flags=re.IGNORECASE)

    return str(message)


def sanitize_event_dict(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor to sanitize sensitive data from event dictionaries."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = sanitize_for_logging(value)
        elif isinstance(value, dict | list):
            event_dict[key] = sanitize_for_logging(value)
    return event_dict


# ============================================================================
# STARTUP BANNER
# ============================================================================

_BANNER_FLAG_FILE = "/tmp/.demo_agent_banner_printed"
_BANNER_FLAG_PATH = Path(_BANNER_FLAG_FILE)
_banner_printed_by_this_process = False

BYTES_PER_MB = 1024 * 1024

COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "g_blue": "\033[94m",
    "g_red": "\033[91m",
    "g_yellow": "\033[93m",
    "g_green": "\033[92m",
}

_B = COLORS["bold"]
_R = COLORS["reset"]
_GB = COLORS["g_blue"]
_GR = COLORS["g_red"]
_GY = COLORS["g_yellow"]
_GG = COLORS["g_green"]

# fmt: off
BANNER = f"""
{_B}{_GB} ____  {_GR} _____ {_GY} __  __ {_GB}  ___  {_R}        {_GR}    _    {_GY}  ____ {_GB} _____ {_GG} _   _ {_GB} _____
{_GB}|  _ \\ {_GR}| ____|{_GY}|  \\/  |{_GB} / _ \\ {_R}  ___  {_GR}   / \\   {_GY} / ___|{_GB}| ____|{_GG}| \\ | |{_GB}|_   _|
{_GB}| | | |{_GR}|  _|  {_GY}| |\\/| |{_GB}| | | |{_R} |___| {_GR}  / _ \\  {_GY}| |  _ {_GB}|  _|  {_GG}|  \\| |{_GB}  | |
{_GB}| |_| |{_GR}| |___ {_GY}| |  | |{_GB}| |_| |{_R}       {_GR} / ___ \\ {_GY}| |_| |{_GB}| |___ {_GG}| |\\  |{_GB}  | |
{_GB}|____/ {_GR}|_____|{_GY}|_|  |_|{_GB} \\___/ {_R}       {_GR}/_/   \\_\\{_GY} \\____|{_GB}|_____|{_GG}|_| \\_|{_GB}  |_|
{_R}"""  # noqa: E501
# fmt: on


def _try_acquire_banner_lock() -> bool:
    """Try to acquire banner lock atomically for multi-worker scenarios."""
    if not settings.log_console_enabled:
        return False
    try:
        fd = os.open(_BANNER_FLAG_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def print_banner() -> None:
    """Print the service startup banner."""
    global _banner_printed_by_this_process  # noqa: PLW0603
    if not _try_acquire_banner_lock():
        return

    _banner_printed_by_this_process = True
    print(BANNER)
    print(f"{COLORS['dim']}{'─' * 80}{COLORS['reset']}")
    print(
        f"{COLORS['cyan']}{COLORS['bold']}  "
        f"Demo Agent API - Gemini 2.5 with Clerk Auth{COLORS['reset']}"
    )
    print(f"{COLORS['dim']}{'─' * 80}{COLORS['reset']}\n")


def print_config_summary() -> None:
    """Print a formatted configuration summary."""
    if not _banner_printed_by_this_process:
        return

    c = COLORS

    def _line(label: str, value: str, color: str = "cyan") -> None:
        print(f"  {c['dim']}│{c['reset']} {label:<28} {c[color]}{value}{c['reset']}")

    print(f"\n  {c['green']}▶ Server Configuration{c['reset']}")
    print(f"  {c['dim']}├{'─' * 55}{c['reset']}")
    _line("Host", settings.host, "cyan")
    _line("Port", str(settings.port), "cyan")

    print(f"\n  {c['blue']}▶ Google Cloud / Vertex AI{c['reset']}")
    print(f"  {c['dim']}├{'─' * 55}{c['reset']}")
    _line("Project ID", settings.gcp_project_id or "(not set)", "yellow")
    _line("Location", settings.gcp_location)
    _line("Model", settings.model)

    print(f"\n  {c['magenta']}▶ Demo Limits{c['reset']}")
    print(f"  {c['dim']}├{'─' * 55}{c['reset']}")
    _line("Max Tokens/Day", f"{settings.demo_max_tokens:,}")
    _line("Cooldown Hours", str(settings.demo_cooldown_hours))
    _line("Warning Threshold", f"{settings.demo_warning_threshold}%")

    print(f"\n  {c['yellow']}▶ Security{c['reset']}")
    print(f"  {c['dim']}├{'─' * 55}{c['reset']}")
    _line("Clerk Auth", "enabled" if settings.enable_clerk_auth else "disabled", "green")
    _line("Fingerprint", "enabled" if settings.enable_fingerprint else "disabled")

    print(f"\n  {c['g_blue']}▶ Concurrency{c['reset']}")
    print(f"  {c['dim']}├{'─' * 55}{c['reset']}")
    _line("Uvicorn Workers", str(settings.uvicorn_workers))
    _line("Max Concurrent Requests", str(settings.max_concurrent_requests))
    total_capacity = settings.uvicorn_workers * settings.max_concurrent_requests
    _line("Total Capacity", f"{total_capacity} concurrent Gemini calls", "green")

    print(f"\n  {c['g_green']}▶ Database Pool{c['reset']}")
    print(f"  {c['dim']}├{'─' * 55}{c['reset']}")
    _line("Pool Min Size", str(settings.db_pool_min_size))
    _line("Pool Max Size", str(settings.db_pool_max_size))
    _line("Command Timeout", f"{settings.db_command_timeout}s")
    total_db_conn = settings.uvicorn_workers * settings.db_pool_max_size
    _line("Max DB Connections", f"{total_db_conn} (workers × pool_max)", "yellow")

    print(f"\n  {c['cyan']}▶ Logging{c['reset']}")
    print(f"  {c['dim']}├{'─' * 55}{c['reset']}")
    _line("Level", settings.log_level, "green")
    _line("Directory", str(settings.log_dir))
    _line("File Logging", "enabled" if settings.log_to_file else "disabled")
    _line("JSON Format", str(settings.log_json_format).lower())

    print(f"\n{c['dim']}{'─' * 80}{c['reset']}")
    print(
        f"  {c['green']}{c['bold']}✓ Service ready{c['reset']} "
        f"{c['dim']}│{c['reset']} "
        f"Docs: {c['cyan']}http://localhost:{settings.port}/docs{c['reset']}"
    )
    print(f"{c['dim']}{'─' * 80}{c['reset']}\n")


# ============================================================================
# LOGGING SETUP
# ============================================================================

_logging_configured = False


def setup_logging() -> None:
    """Configure structured logging with rotation and sensitive data sanitization."""
    global _logging_configured  # noqa: PLW0603
    if _logging_configured:
        return
    _logging_configured = True

    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "demo-agent.log"

    log_level = getattr(logging, settings.log_level, logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        sanitize_event_dict,  # type: ignore[list-item]
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=True),
        foreign_pre_chain=shared_processors,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    if settings.log_console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)

    if settings.log_to_file:
        max_bytes = settings.log_file_max_mb * BYTES_PER_MB
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=settings.log_file_backup_count,
            encoding="utf-8",
        )
        file_formatter = json_formatter if settings.log_json_format else console_formatter
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)

    print_banner()
    print_config_summary()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
