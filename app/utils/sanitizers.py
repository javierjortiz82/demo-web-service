"""Input/Output Sanitization Utilities.

Provides sanitization functions to prevent XSS, injection attacks, and
information disclosure vulnerabilities.

SECURITY: All user-controlled data should pass through these sanitizers
before being stored, displayed, or included in responses.

Author: Odiseo Team
Created: 2025-11-07
Version: 1.1.0 (Optimized)
"""

import html
import re

# Maximum lengths for various fields (DoS prevention)
MAX_INPUT_LENGTH = 10000  # User queries


def sanitize_html(text: str) -> str:
    """Sanitize HTML to prevent XSS attacks.

    SECURITY (CWE-79 fix): Escapes HTML special characters to prevent
    script injection in web contexts.

    Args:
        text: Input text that may contain HTML.

    Returns:
        HTML-escaped text safe for display.

    Examples:
        >>> sanitize_html("<script>alert('XSS')</script>")
        "&lt;script&gt;alert('XSS')&lt;/script&gt;"

        >>> sanitize_html("Hello <b>World</b>")
        "Hello &lt;b&gt;World&lt;/b&gt;"
    """
    if not text or not isinstance(text, str):
        return ""

    # HTML escape: < > & " '
    return html.escape(text, quote=True)


def sanitize_user_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """Sanitize user input for safe processing and storage.

    SECURITY: Removes dangerous characters, normalizes whitespace,
    enforces length limits.

    Args:
        text: User input text.
        max_length: Maximum allowed length (DoS prevention).

    Returns:
        Sanitized text.

    Examples:
        >>> sanitize_user_input("  Hello\\n\\nWorld  ")
        "Hello World"

        >>> sanitize_user_input("Test\\x00null\\rbyte")
        "Testnullbyte"
    """
    if not text or not isinstance(text, str):
        return ""

    # Remove null bytes (string termination attacks)
    text = text.replace("\x00", "")

    # Remove other control characters except newline and tab
    text = "".join(char for char in text if ord(char) >= 0x20 or char in "\n\t")

    # Normalize whitespace (collapse multiple spaces/newlines)
    text = re.sub(r"\s+", " ", text)

    # Trim
    text = text.strip()

    # Enforce length limit
    if len(text) > max_length:
        text = text[:max_length]

    return text


def sanitize_error_message(error: Exception, include_details: bool = False) -> str:
    """Sanitize exception messages to prevent information disclosure.

    SECURITY (CWE-209 fix): Prevents leaking sensitive information
    (database errors, file paths, stack traces) to users.

    Args:
        error: Exception object.
        include_details: Whether to include detailed error info (dev mode only).

    Returns:
        Safe error message for user display.

    Examples:
        >>> sanitize_error_message(ValueError("Database password: secret123"))
        "An error occurred. Please try again."

        >>> sanitize_error_message(FileNotFoundError("/etc/passwd not found"))
        "An error occurred. Please try again."
    """
    if not include_details:
        # Production: Generic message only
        return "An error occurred. Please try again."

    # Development: Sanitized error details
    error_str = str(error)

    # Remove potential sensitive patterns
    patterns_to_redact = [
        (r"password[=:]\s*\S+", "password=[REDACTED]"),
        (r"token[=:]\s*\S+", "token=[REDACTED]"),
        (r"key[=:]\s*\S+", "key=[REDACTED]"),
        (r"secret[=:]\s*\S+", "secret=[REDACTED]"),
        (r"/home/\w+", "/home/[USER]"),
        (r"/root/\w+", "/root/[REDACTED]"),
        (r"C:\\Users\\\w+", "C:\\Users\\[USER]"),
        (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP]"),
    ]

    for pattern, replacement in patterns_to_redact:
        error_str = re.sub(pattern, replacement, error_str, flags=re.IGNORECASE)

    # Limit length
    if len(error_str) > 200:
        error_str = error_str[:200] + "..."

    return sanitize_html(error_str)
