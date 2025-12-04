"""User Service for Demo Agent.

Provides database access for user-related operations.

Author: Odiseo Team
Created: 2025-11-10
Version: 1.0.0
"""

from app.db.connection import get_db
from app.utils.logging import get_logger

logger = get_logger(__name__)


class UserService:
    """Service wrapper for user-related database operations.

    Provides access to the database connection for routes that need
    to query user data directly.
    """

    def __init__(self) -> None:
        """Initialize user service with database connection."""
        self.db = get_db()
        logger.info("UserService initialized")


# Singleton instance
_user_service: UserService | None = None


def get_user_service() -> UserService:
    """Get singleton instance of UserService.

    Returns:
        UserService: Singleton instance.
    """
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
